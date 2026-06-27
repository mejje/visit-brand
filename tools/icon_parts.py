"""Convert icon references into a parametric part spec, reconstruct SVGs, and score against references.

Subcommands:
  bootstrap   Create exact part spec from reference JSON + source SVGs (Stage 1-2)
  render      Reconstruct SVGs and overlays from a part spec (Stage 3 + 5)
  score       Compute Shapely metrics comparing a part spec against references (Stage 4)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from shapely import wkb
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
import numpy as np
from svgelements import SVG

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icon_reference as iref  # noqa: E402

PART_SCHEMA = "visit.icon-parts.v1"
GENERATOR = "tools/icon_parts.py"


def load_references(
    ref_dir: Path, icons: Sequence[str] | None = None
) -> list[tuple[str, Path, dict, object]]:
    """Return list of (icon_id, reference_path, reference_dict, geometry)."""
    results = []
    for path in sorted(ref_dir.glob("*.reference.json"), key=lambda p: p.name.lower()):
        ref, geom = iref.load_reference(path)
        icon_id = ref["icon_id"]
        if icons and icon_id not in icons:
            continue
        results.append((icon_id, path, ref, geom))
    if icons:
        found = {r[0] for r in results}
        missing = sorted(set(icons) - found)
        if missing:
            raise SystemExit(f"Icons not found in references: {', '.join(missing)}")
    return results


def extract_primitive_geometries(
    source_path: Path, tolerance: float, expected_count: int
) -> list[object]:
    """Extract individual Shapely geometry for each filled primitive from an SVG."""
    svg = SVG.parse(str(source_path))
    geometries = []
    for element in iref.iter_filled_shapes(svg):
        geom = iref.shape_to_geometry(element, tolerance)
        if geom is not None:
            geometries.append(geom)
    if len(geometries) != expected_count:
        print(
            f"  Warning: {source_path.stem} has {len(geometries)} primitive geometries "
            f"but {expected_count} primitive hints"
        )
    return geometries


def is_axis_aligned_rect(geom) -> bool:
    """Check if a Polygon represents an axis-aligned rectangle with 4 vertices."""
    if geom.geom_type != "Polygon":
        return False
    if geom.is_empty:
        return False
    coords = list(geom.exterior.coords)
    if len(coords) != 5:
        return False
    if coords[0] != coords[4]:
        return False
    xs = sorted({c[0] for c in coords[:4]})
    ys = sorted({c[1] for c in coords[:4]})
    if len(xs) != 2 or len(ys) != 2:
        return False
    x_coords = [c[0] for c in coords[:4]]
    y_coords = [c[1] for c in coords[:4]]
    if len(set(x_coords)) != 2 or len(set(y_coords)) != 2:
        return False
    return True


def polygon_signature(geom) -> str:
    """Compute a canonical hash signature for a polygon, normalized to origin."""
    normalized = iref.canonical_geometry(geom)
    min_x, min_y, max_x, max_y = normalized.bounds
    translated = iref.canonical_geometry(
        Polygon(
            [(x - min_x, y - min_y) for x, y in normalized.exterior.coords],
            [
                [(x - min_x, y - min_y) for x, y in interior.coords]
                for interior in normalized.interiors
            ],
        )
    )
    return hashlib.sha256(translated.wkb).hexdigest()[:16]


def classify_primitive(hint: dict, geom) -> str:
    """Determine the canonical part kind from a primitive hint and its geometry."""
    kind = hint["kind"]
    if kind == "Rect":
        if hint["has_transform"]:
            return "bar"
        return "rect"
    if kind == "Polygon" and is_axis_aligned_rect(geom):
        return "rect"
    if kind == "Path":
        return "custom_polygon"
    return "polygon"


def primitive_signature(part_kind: str, bounds: list[float], geom) -> str:
    """Compute a canonical signature string for a primitive."""
    min_x, min_y, max_x, max_y = bounds
    if part_kind == "rect":
        w = round(max_x - min_x, 6)
        h = round(max_y - min_y, 6)
        return f"rect_{w}x{h}"
    if part_kind == "bar":
        w = round(max_x - min_x, 6)
        h = round(max_y - min_y, 6)
        return f"bar_{w}x{h}_{polygon_signature(geom)}"
    if part_kind == "polygon":
        return f"poly_{polygon_signature(geom)}"
    return f"custom_{polygon_signature(geom)}"


def normalised_part_geometry(part_kind: str, bounds: list[float], geom) -> object:
    """Return the part geometry translated to origin (anchor at 0,0)."""
    min_x, min_y, max_x, max_y = bounds
    dx, dy = -min_x, -min_y
    coords = [(x + dx, y + dy) for x, y in geom.exterior.coords]
    interiors = [
        [(x + dx, y + dy) for x, y in interior.coords] for interior in geom.interiors
    ]
    return iref.canonical_geometry(Polygon(coords, interiors))


def compute_min_feature(geom, precision: float = 0.01) -> float:
    """Estimate smallest feature dimension of a geometry."""
    if geom.geom_type != "Polygon" or geom.is_empty:
        return 0.0
    coords = list(geom.exterior.coords)
    if len(coords) < 4:
        bounds = geom.bounds
        return min(bounds[2] - bounds[0], bounds[3] - bounds[1])
    distances = []
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        distances.append((dx * dx + dy * dy) ** 0.5)
    min_edge = min(distances) if distances else 0.0
    return max(iref.round_float(min_edge, precision), 0.0)


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


def bootstrap_command(args: argparse.Namespace) -> int:
    ref_dir = Path(args.references)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    refs = load_references(ref_dir, args.icons)
    if not refs:
        raise SystemExit(f"No reference files found in {ref_dir}")

    tolerance = args.curve_tolerance
    precision = args.coordinate_precision

    all_primitives: list[dict[str, Any]] = []
    signature_to_part: dict[str, str] = {}
    parts: dict[str, dict] = {}
    icons: dict[str, dict] = {}

    part_counter = 0

    for icon_id, ref_path, ref, ref_geom in refs:
        source_rel = ref["source"]["path"]
        source_path = Path(source_rel)
        if not source_path.is_absolute():
            source_path = Path.cwd() / source_rel

        hints = ref.get("primitive_hints", [])
        geoms = extract_primitive_geometries(source_path, tolerance, len(hints))

        icon_instances: list[dict] = []

        for hint, geom in zip(hints, geoms):
            part_kind = classify_primitive(hint, geom)
            bounds = hint["bounds"]
            sig = primitive_signature(part_kind, bounds, geom)

            if sig not in signature_to_part:
                canonical_geom = normalised_part_geometry(part_kind, bounds, geom)
                part_id = f"part_{part_counter:04d}"
                part_counter += 1
                signature_to_part[sig] = part_id

                part_def: dict[str, Any] = {
                    "kind": part_kind,
                    "bounds": [iref.round_float(v, precision) for v in bounds],
                    "source_primitives": [
                        {"icon": icon_id, "index": hint["index"]}
                    ],
                }
                if part_kind == "rect":
                    w = iref.round_float(bounds[2] - bounds[0], precision)
                    h = iref.round_float(bounds[3] - bounds[1], precision)
                    part_def["width"] = w
                    part_def["height"] = h
                else:
                    part_def["geometry"] = {
                        "format": "wkb_hex",
                        "value": canonical_geom.wkb_hex,
                    }
                min_feat = compute_min_feature(canonical_geom, 0.01)
                part_def["print"] = {
                    "min_feature": iref.round_float(min_feat, 0.01),
                }
                parts[part_id] = part_def
            else:
                part_id = signature_to_part[sig]
                parts[part_id]["source_primitives"].append(
                    {"icon": icon_id, "index": hint["index"]}
                )

            at_x = iref.round_float(bounds[0], precision)
            at_y = iref.round_float(bounds[1], precision)
            icon_instances.append({
                "part": part_id,
                "at": [at_x, at_y],
                "source_index": hint["index"],
            })

        icons[icon_id] = {"instances": icon_instances}

    part_spec = {
        "schema": PART_SCHEMA,
        "generator": f"{GENERATOR} bootstrap",
        "units": "svg_user_units",
        "coordinate_system": "svg_y_down",
        "allowed_transforms": {
            "translate": True,
            "rotate": False,
            "mirror": False,
            "scale": False,
        },
        "settings": {
            "curve_flatten_tolerance": tolerance,
            "coordinate_precision": precision,
        },
        "parts": parts,
        "icons": icons,
    }

    out_path = out_dir / "part-spec.exact.v1.json"
    part_spec_str = json.dumps(part_spec, indent=2, sort_keys=True) + "\n"
    out_path.write_text(part_spec_str, encoding="utf-8")

    total_unique = len(parts)
    total_instances = sum(len(ic["instances"]) for ic in icons.values())
    print(f"bootstrap: {total_unique} unique parts, {total_instances} instances across {len(icons)} icons")
    print(f"  wrote {out_path}")

    for icon_id in sorted(icons):
        instances = icons[icon_id]["instances"]
        unique_in_icon = len({i["part"] for i in instances})
        print(f"  {icon_id}: {len(instances)} instances ({unique_in_icon} unique parts)")

    return 0


# ---------------------------------------------------------------------------
# shared scoring
# ---------------------------------------------------------------------------


def score_spec(spec: dict, refs: dict[str, tuple]) -> dict:
    """Score a part spec in memory against loaded references. Returns summary dict."""
    precision = spec["settings"]["coordinate_precision"]
    parts = spec["parts"]

    results: list[dict] = []
    total_area_error = 0.0
    total_ref_area = 0.0
    max_hausdorff = 0.0

    for icon_id, icon_spec in sorted(spec["icons"].items()):
        ref_info = refs.get(icon_id)
        if ref_info is None:
            continue
        _, _, ref, ref_geom = ref_info

        recon_geom, _details = reconstruct_icon(icon_spec, parts, precision)

        sym_diff = ref_geom.symmetric_difference(recon_geom)
        area_error = sym_diff.area
        ref_area = ref_geom.area
        area_ratio = area_error / ref_area if ref_area > 0 else 0.0

        hausdorff = ref_geom.hausdorff_distance(recon_geom)

        ref_bounds = ref_geom.bounds
        recon_bounds = recon_geom.bounds
        bounds_delta = max(abs(ref_bounds[i] - recon_bounds[i]) for i in range(4))

        ref_components = iref.extract_polygons(ref_geom)
        recon_components = iref.extract_polygons(recon_geom)

        results.append({
            "icon_id": icon_id,
            "area_error_ratio": area_ratio,
            "hausdorff_distance": hausdorff,
            "bounds_delta": bounds_delta,
            "component_delta": len(recon_components) - len(ref_components),
            "ref_components": len(ref_components),
        })
        total_area_error += area_error
        total_ref_area += ref_area
        if hausdorff > max_hausdorff:
            max_hausdorff = hausdorff

    unique_parts = len(parts)
    total_instances = sum(len(ic["instances"]) for ic in spec["icons"].values())
    overall_ratio = total_area_error / total_ref_area if total_ref_area > 0 else 0.0

    return {
        "unique_parts": unique_parts,
        "total_instances": total_instances,
        "overall_area_error_ratio": overall_ratio,
        "total_area_error": total_area_error,
        "worst_hausdorff": max_hausdorff,
        "per_icon": results,
    }


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def part_to_geometry(part_def: dict, anchor: str = "min_corner") -> object:
    """Convert a part definition to Shapely geometry at origin.

    anchor="min_corner" (default): top-left corner at (0,0).
    anchor="centroid": part centroid at (0,0), for rotation support.
    """
    from shapely import affinity

    kind = part_def["kind"]
    if kind == "rect":
        w = part_def["width"]
        h = part_def["height"]
        geom = Polygon([
            (0, 0), (w, 0), (w, h), (0, h), (0, 0)
        ])
    else:
        geom_info = part_def["geometry"]
        if geom_info["format"] != "wkb_hex":
            raise ValueError(f"Unsupported geometry format: {geom_info['format']}")
        geom = wkb.loads(geom_info["value"], hex=True)

    if anchor == "centroid":
        cx, cy = geom.centroid.x, geom.centroid.y
        geom = affinity.translate(geom, xoff=-cx, yoff=-cy)
    return geom


def translate_geometry(geom, dx: float, dy: float) -> object:
    """Translate a Shapely geometry by (dx, dy)."""
    from shapely import affinity
    return affinity.translate(geom, xoff=dx, yoff=dy)


def place_part(geom, at_x: float, at_y: float, rotate: float = 0.0) -> object:
    """Place part geometry: rotate around origin, then translate to (at_x, at_y)."""
    from shapely import affinity
    if rotate != 0.0:
        geom = affinity.rotate(geom, rotate, origin=(0, 0))
    return affinity.translate(geom, xoff=at_x, yoff=at_y)


def reconstruct_icon(
    icon_spec: dict, parts: dict, precision: float
) -> tuple[object, list[dict]]:
    """Reconstruct icon geometry from instances. Returns (unioned_geometry, instance_details).

    Supports both min_corner anchor (no rotate field) and centroid anchor (rotate present, even 0.0).
    """
    instance_geoms = []
    details = []
    for inst in icon_spec["instances"]:
        part_id = inst["part"]
        part_def = parts[part_id]
        rotate = inst.get("rotate", None)
        anchor = "centroid" if rotate is not None else "min_corner"
        base_geom = part_to_geometry(part_def, anchor=anchor)
        at_x, at_y = inst["at"]
        placed = place_part(base_geom, at_x, at_y, rotate=rotate or 0.0)
        instance_geoms.append(placed)
        details.append({"part": part_id, "at": [at_x, at_y], "geom": placed, "rotate": rotate})
    if not instance_geoms:
        return MultiPolygon([]), []
    return iref.canonical_geometry(unary_union(instance_geoms)), details


def render_overlay_svg(
    reference: dict,
    ref_geom,
    recon_geom,
    precision: float,
    icon_id: str,
) -> str:
    """Generate an overlay SVG showing reference (black) + reconstruction (red)."""
    viewbox = reference["source"]["viewBox"]
    viewbox_text = " ".join(iref.format_float(v, precision) for v in viewbox)

    ref_data = iref.geometry_to_path_data(ref_geom, precision)
    recon_data = iref.geometry_to_path_data(recon_geom, precision)

    ref_path = f'<path fill="none" stroke="#000000" stroke-width="0.3" fill-rule="evenodd" d="{ref_data}"/>'
    recon_path = (
        f'<path fill="none" stroke="#E53E3E" stroke-width="0.2" '
        f'stroke-dasharray="1 1" fill-rule="evenodd" d="{recon_data}"/>'
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg id="Overlay" xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox_text}">\n'
        f"  {ref_path}\n"
        f"  {recon_path}\n"
        "</svg>\n"
    )


def render_command(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        raise SystemExit(f"Part spec not found: {spec_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    precision = spec["settings"]["coordinate_precision"]
    parts = spec["parts"]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_dir = out_dir / "svgs"
    svg_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir = out_dir / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    ref_dir = Path(args.references)
    refs = {r[0]: r for r in load_references(ref_dir)}

    for icon_id, icon_spec in sorted(spec["icons"].items()):
        ref_info = refs.get(icon_id)
        if ref_info is None:
            print(f"  Warning: no reference found for {icon_id}, skipping")
            continue
        _, _, ref, ref_geom = ref_info

        recon_geom, _details = reconstruct_icon(icon_spec, parts, precision)

        recon_svg = iref.canonical_svg(ref, recon_geom)
        recon_svg = recon_svg.replace('id="CanonicalReference"', f'id="Reconstructed_{icon_id}"')
        (svg_dir / f"{icon_id}.reconstructed.svg").write_text(recon_svg, encoding="utf-8")

        overlay = render_overlay_svg(ref, ref_geom, recon_geom, precision, icon_id)
        (overlay_dir / f"{icon_id}.overlay.svg").write_text(overlay, encoding="utf-8")

        print(f"  rendered {icon_id}")

    print(f"render: wrote SVGs to {svg_dir}, overlays to {overlay_dir}")
    return 0


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def score_command(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        raise SystemExit(f"Part spec not found: {spec_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    precision = spec["settings"]["coordinate_precision"]

    ref_dir = Path(args.references)
    refs = {r[0]: r for r in load_references(ref_dir)}

    summary = score_spec(spec, refs)

    if args.verbose:
        for r in summary["per_icon"]:
            print(
                f"  {r['icon_id']}: area_err={r['area_error_ratio']:.6g}, "
                f"hausdorff={r['hausdorff_distance']:.4f}, "
                f"bounds_delta={r['bounds_delta']:.4f}, "
                f"comp_delta={r['component_delta']}"
            )

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            f"score: {len(summary['per_icon'])} icons, "
            f"{summary['unique_parts']} unique parts, "
            f"{summary['total_instances']} instances"
        )
        print(f"  overall area error ratio: {summary['overall_area_error_ratio']:.6g}")
        for r in summary["per_icon"]:
            print(
                f"  {r['icon_id']:30s}  area_err={r['area_error_ratio']:.6g}  "
                f"hausdorff={r['hausdorff_distance']:.4f}"
            )

    if args.out:
        out_path = Path(args.out)
        data = {"summary": summary}
        data["summary"]["per_icon"] = [
            {
                k: iref.round_float(v, precision) if isinstance(v, float) else v
                for k, v in r.items()
            }
            for r in summary["per_icon"]
        ]
        out_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"  wrote metrics to {out_path}")

    return 0


# ---------------------------------------------------------------------------
# simplify
# ---------------------------------------------------------------------------


def deep_copy_spec(spec: dict) -> dict:
    """Deep copy a part spec so mutations don't leak."""
    return json.loads(json.dumps(spec))


def cluster_rects_by_size(parts: dict, tolerance: float) -> list[list[str]]:
    """Group rect parts within `tolerance` of each cluster's reference size (non-chaining).

    Uses a leader-based approach: each rect starts as its own cluster leader.
    A rect joins an existing cluster only if both dimensions are within `tolerance`
    of the cluster leader. No chaining — avoids merging distant rects through intermediates.
    """
    rect_ids = sorted(
        [pid for pid, pdef in parts.items() if pdef.get("kind") == "rect"],
        key=lambda pid: (parts[pid]["width"], parts[pid]["height"]),
    )
    if not rect_ids:
        return []

    clusters: list[tuple[float, float, set[str]]] = []
    for pid in rect_ids:
        w = parts[pid]["width"]
        h = parts[pid]["height"]
        found = False
        for cw, ch, cids in clusters:
            if abs(w - cw) <= tolerance and abs(h - ch) <= tolerance:
                cids.add(pid)
                found = True
                break
        if not found:
            clusters.append((w, h, {pid}))

    return [sorted(c) for _, _, c in clusters if len(c) > 1]


def merge_rect_clusters(spec: dict, clusters: list[list[str]]) -> dict:
    """Create a new spec where each rect cluster is replaced by its largest member."""
    spec = deep_copy_spec(spec)
    parts = spec["parts"]

    for cluster in clusters:
        max_w = max(parts[pid]["width"] for pid in cluster)
        max_h = max(parts[pid]["height"] for pid in cluster)
        keeper = cluster[0]

        parts[keeper]["width"] = max_w
        parts[keeper]["height"] = max_h
        parts[keeper]["print"]["min_feature"] = min(max_w, max_h)
        parts[keeper]["bounds"] = [
            parts[keeper]["bounds"][0],
            parts[keeper]["bounds"][1],
            parts[keeper]["bounds"][0] + max_w,
            parts[keeper]["bounds"][1] + max_h,
        ]
        for pid in cluster[1:]:
            if "source_primitives" in parts[pid]:
                parts[keeper].setdefault("source_primitives", []).extend(
                    parts[pid]["source_primitives"]
                )
            del parts[pid]

        for icon_spec in spec["icons"].values():
            for inst in icon_spec["instances"]:
                if inst["part"] in cluster:
                    inst["part"] = keeper

    return spec


# ---- polygon decomposition strategies ----


def part_geometry(part_def: dict, anchor: str = "min_corner") -> object:
    """Load a part's Shapely geometry at origin. Delegates to shared part_to_geometry."""
    return part_to_geometry(part_def, anchor=anchor)


# ---- polygon grid-split decomposition ----


def decompose_grid_split(
    spec: dict, cols: int = 2, rows: int = 2, min_cell_area: float = 1.0
) -> dict:
    """Split polygon/bar/custom parts into axis-aligned rect sub-parts via grid overlay."""
    from shapely.geometry import box as shapely_box

    spec = deep_copy_spec(spec)
    parts = spec["parts"]
    new_parts: dict[str, dict] = {}
    part_remap: dict[str, list[str]] = {}
    next_pid = max(int(p.replace("part_", "")) for p in parts) + 1

    for pid, pdef in list(parts.items()):
        if pdef["kind"] == "rect":
            continue
        geom = part_geometry(pdef, anchor="min_corner")
        if geom.is_empty or geom.area == 0:
            continue
        min_x, min_y, max_x, max_y = geom.bounds
        if max_x - min_x <= 0 or max_y - min_y <= 0:
            continue
        w = (max_x - min_x) / cols
        h = (max_y - min_y) / rows
        if w < min_cell_area or h < min_cell_area:
            continue

        sub_pids = []
        for r in range(rows):
            for c in range(cols):
                cell = shapely_box(
                    min_x + c * w, min_y + r * h,
                    min_x + (c + 1) * w, min_y + (r + 1) * h,
                )
                if geom.intersects(cell):
                    cell_pid = f"part_{next_pid:04d}"
                    next_pid += 1
                    sub_pids.append(cell_pid)
                    new_parts[cell_pid] = {
                        "kind": "rect",
                        "width": round(w, 6),
                        "height": round(h, 6),
                        "bounds": [
                            round(min_x + c * w, 9),
                            round(min_y + r * h, 9),
                            round(min_x + (c + 1) * w, 9),
                            round(min_y + (r + 1) * h, 9),
                        ],
                        "print": {"min_feature": round(min(w, h), 6)},
                        "source_primitives": list(pdef.get("source_primitives", [])),
                    }
        if len(sub_pids) >= 2:
            part_remap[pid] = sub_pids

    for pid, sub_pids in part_remap.items():
        del parts[pid]
    parts.update(new_parts)

    for icon_spec in spec["icons"].values():
        new_instances = []
        for inst in icon_spec["instances"]:
            pid = inst["part"]
            if pid in part_remap:
                for sub_pid in part_remap[pid]:
                    new_instances.append({
                        "part": sub_pid,
                        "at": inst["at"],
                    })
            else:
                new_instances.append(inst)
        icon_spec["instances"] = new_instances

    return spec


# ---- largest inscribed rectangle decomposition ----


def _largest_inscribed_rect(geom, step: float = 1.0, size_classes: list[float] | None = None):
    """Find the largest axis-aligned rectangle fully contained in the polygon.

    Grid-samples possible positions and size classes. Returns a Shapely box or None.
    """
    from shapely.geometry import box as shapely_box

    if size_classes is None:
        size_classes = [2, 4, 6, 8, 12, 16, 20, 24, 32, 40]

    min_x, min_y, max_x, max_y = geom.bounds
    best_rect = None
    best_area = 0.0

    x_positions = list(float(x) for x in np.arange(min_x, max_x - 1, step)) + [min_x]
    y_positions = list(float(y) for y in np.arange(min_y, max_y - 1, step)) + [min_y]

    for x in x_positions:
        for y in y_positions:
            for w in size_classes:
                if x + w > max_x:
                    break
                for h in size_classes:
                    if y + h > max_y:
                        break
                    candidate = shapely_box(x, y, x + w, y + h)
                    if geom.contains(candidate):
                        area = w * h
                        if area > best_area:
                            best_area = area
                            best_rect = candidate
    return best_rect


def decompose_inscribed_rect(
    spec: dict, coverage_threshold: float = 0.4, step: float = 1.0
) -> dict:
    """Extract the largest inscribed axis-aligned rectangle from each polygon.

    If the rectangle covers >= coverage_threshold of the polygon's area:
    - Extract it as a rect part
    - Keep the remainder polygon (polygon minus rect) as a separate part

    This turns 1 polygon into at most 2 parts, and the rect can be shared.
    """
    from shapely.geometry import box as shapely_box

    spec = deep_copy_spec(spec)
    parts = spec["parts"]
    new_parts: dict[str, dict] = {}
    part_remap: dict[str, str] = {}
    part_add: dict[str, str] = {}  # pid -> new remainder part pid
    next_pid = max(int(p.replace("part_", "")) for p in parts) + 1

    for pid, pdef in list(parts.items()):
        if pdef["kind"] == "rect":
            continue
        geom = part_geometry(pdef, anchor="min_corner")
        if geom.is_empty or geom.area < 4:
            continue

        best_rect = _largest_inscribed_rect(geom, step=step)
        if best_rect is None:
            continue
        rect_area = best_rect.area
        coverage = rect_area / geom.area
        if coverage < coverage_threshold:
            continue

        # Extract rectangle
        rx, ry, rw, rh = best_rect.bounds
        rect_w = rw - rx
        rect_h = rh - ry

        rect_pid = f"part_{next_pid:04d}"
        next_pid += 1
        new_parts[rect_pid] = {
            "kind": "rect",
            "width": round(rect_w, 6),
            "height": round(rect_h, 6),
            "bounds": [round(rx, 9), round(ry, 9), round(rw, 9), round(rh, 9)],
            "print": {"min_feature": round(min(rect_w, rect_h), 6)},
            "source_primitives": list(pdef.get("source_primitives", [])),
        }
        part_remap[pid] = rect_pid

        # Remainder polygon
        remainder = geom.difference(best_rect)
        if not remainder.is_empty and remainder.area > 1:
            remainder = iref.canonical_geometry(remainder)
            rem_pid = f"part_{next_pid:04d}"
            next_pid += 1
            new_parts[rem_pid] = {
                "kind": "polygon",
                "bounds": [round(v, 9) for v in remainder.bounds],
                "geometry": {"format": "wkb_hex", "value": remainder.wkb_hex},
                "print": {"min_feature": max(0.01, round(min(remainder.bounds[2] - remainder.bounds[0], remainder.bounds[3] - remainder.bounds[1]), 6) or 0.01)},
                "source_primitives": list(pdef.get("source_primitives", [])),
            }
            part_add[pid] = rem_pid

    for pid, rect_pid in part_remap.items():
        del parts[pid]
    parts.update(new_parts)

    for icon_spec in spec["icons"].values():
        new_instances = []
        for inst in icon_spec["instances"]:
            pid = inst["part"]
            if pid in part_remap:
                new_instances.append({"part": part_remap[pid], "at": inst["at"]})
                if pid in part_add:
                    new_instances.append({"part": part_add[pid], "at": inst["at"]})
            else:
                new_instances.append(inst)
        icon_spec["instances"] = new_instances

    return spec


def decompose_polygons_to_bbox_rects(spec: dict) -> dict:
    """Replace every polygon/bar/custom_polygon part with its bounding-box rect.

    This is a radical decomposition: all non-rect shapes become axis-aligned rects.
    Returns a new spec with significantly fewer unique parts (all rects of the same
    size deduplicate), at the cost of potentially large visual error.
    """
    spec = deep_copy_spec(spec)
    parts = spec["parts"]

    bbox_map: dict[str, tuple[float, float, str]] = {}
    # pid -> (w, h, keeper_pid)

    for pid, pdef in list(parts.items()):
        if pdef["kind"] == "rect":
            continue
        geom = part_geometry(pdef)
        min_x, min_y, max_x, max_y = geom.bounds
        w = max_x - min_x
        h = max_y - min_y
        if w <= 0 or h <= 0:
            continue
        sig = (round(w, 6), round(h, 6))
        if sig in bbox_map:
            keeper = bbox_map[sig][2]
            if "source_primitives" in parts[pid]:
                parts[keeper].setdefault("source_primitives", []).extend(
                    parts[pid]["source_primitives"]
                )
            del parts[pid]
        else:
            pdef["kind"] = "rect"
            pdef["width"] = w
            pdef["height"] = h
            pdef["print"]["min_feature"] = min(w, h)
            pdef.pop("geometry", None)
            bbox_map[sig] = (w, h, pid)

    for icon_spec in spec["icons"].values():
        for inst in icon_spec["instances"]:
            pid = inst["part"]
            if pid in parts and parts[pid]["kind"] == "rect":
                continue
            if pid not in parts:
                for (w, h, keeper) in bbox_map.values():
                    old_geom = None
                    # Remap: the old pid was in the bbox_map
                continue
            # Should not happen after remap
    return spec


def decompose_polygons_to_bbox_rects_fixed(spec: dict) -> dict:
    """Replace polygon/bar/custom_polygon parts with bounding-box rects.

    Track the old→new mapping and remap all icon instances.
    Rect parts are left unchanged.
    """
    spec = deep_copy_spec(spec)
    parts = spec["parts"]

    pid_remap: dict[str, str] = {}
    bbox_sig_to_keeper: dict[tuple[float, float], str] = {}

    for pid, pdef in sorted(parts.items()):
        if pdef["kind"] == "rect":
            continue
        geom = part_geometry(pdef)
        min_x, min_y, max_x, max_y = geom.bounds
        w = round(max_x - min_x, 6)
        h = round(max_y - min_y, 6)
        if w <= 0 or h <= 0:
            pdef["kind"] = "rect"
            pdef["width"] = w
            pdef["height"] = h
            pdef["print"]["min_feature"] = 0.0
            pdef.pop("geometry", None)
            continue

        sig = (w, h)
        if sig in bbox_sig_to_keeper:
            keeper = bbox_sig_to_keeper[sig]
            if "source_primitives" in pdef:
                parts[keeper].setdefault("source_primitives", []).extend(
                    pdef["source_primitives"]
                )
            pid_remap[pid] = keeper
        else:
            pdef["kind"] = "rect"
            pdef["width"] = w
            pdef["height"] = h
            pdef["print"]["min_feature"] = min(w, h)
            pdef.pop("geometry", None)
            bbox_sig_to_keeper[sig] = pid

    for pid in pid_remap:
        if pid in parts:
            del parts[pid]

    for icon_spec in spec["icons"].values():
        for inst in icon_spec["instances"]:
            if inst["part"] in pid_remap:
                inst["part"] = pid_remap[inst["part"]]

    return spec


def _try_rotated_hausdorff(geom_a, geom_b, angles=(0, 90, 180, 270)) -> tuple[float, float]:
    """Return (min_hausdorff, best_angle) for geom_b rotated against geom_a.

    Prefers rotation=0 when its Hausdorff is within 5% of the best rotated match,
    preventing false-positive rotations for already-aligned parts.
    """
    from shapely import affinity

    best_hd = float("inf")
    best_angle = 0.0
    hd_at_zero: float | None = None
    for angle in angles:
        rotated = affinity.rotate(geom_b, angle, origin=(0, 0))
        try:
            hd = geom_a.hausdorff_distance(rotated)
        except Exception:
            continue
        if angle == 0:
            hd_at_zero = hd
        if hd < best_hd:
            best_hd = hd
            best_angle = angle
    if best_hd == float("inf"):
        try:
            best_hd = geom_a.hausdorff_distance(geom_b)
        except Exception:
            pass
    # Prefer 0-degree rotation if within 5% of best
    if hd_at_zero is not None and best_angle != 0:
        if hd_at_zero <= best_hd * 1.05:
            return hd_at_zero, 0.0
    return best_hd, best_angle


def cluster_polygons_by_hausdorff(
    parts: dict, tolerance: float, allow_rotation: bool = False
) -> tuple[list[list[str]], dict[str, float] | None]:
    """Group polygon/bar/custom parts by Hausdorff distance.

    If allow_rotation, tries rotating each candidate at 0/90/180/270 degrees
    and records the best angle per member. Returns (clusters, rotations) where
    rotations maps part_id -> best_rotation_angle. Returns None for rotations if
    not using rotation.

    Uses leader-based non-chaining clustering.
    """
    angles = (0, 90, 180, 270) if allow_rotation else (0,)

    poly_ids = sorted(
        [
            pid
            for pid, pdef in parts.items()
            if pdef.get("kind") in {"polygon", "bar", "custom_polygon"}
        ],
        key=lambda pid: parts[pid].get("bounds", [0, 0, 0, 0]),
    )
    if len(poly_ids) < 2:
        return [], {} if allow_rotation else None

    anchor = "centroid" if allow_rotation else "min_corner"
    polys: dict[str, object] = {}
    for pid in poly_ids:
        try:
            polys[pid] = part_geometry(parts[pid], anchor=anchor)
        except Exception:
            continue

    sorted_ids = sorted(
        polys,
        key=lambda pid: (
            len(list(polys[pid].exterior.coords)) if polys[pid].geom_type == "Polygon" else 99,
            polys[pid].area,
        ),
    )

    clusters: list[tuple[object, set[str]]] = []
    member_rotation: dict[str, float] = {}

    for pid in sorted_ids:
        geom = polys[pid]
        found = False
        for leader_geom, cids in clusters:
            hd, angle = _try_rotated_hausdorff(leader_geom, geom, angles=angles)
            if hd <= tolerance:
                cids.add(pid)
                member_rotation[pid] = angle
                found = True
                break
        if not found:
            clusters.append((geom, {pid}))
            member_rotation[pid] = 0.0

    result_clusters = [sorted(c) for _, c in clusters if len(c) > 1]
    if not result_clusters:
        return [], {} if allow_rotation else None
    return result_clusters, member_rotation if allow_rotation else None


def _convert_to_centroid_anchor(spec: dict, part_ids: set[str] | None = None) -> dict:
    """Convert specified polygon/bar/custom parts to centroid-anchored geometry.

    If part_ids is None, converts ALL non-rect parts.
    Updates part geometry to be centroid-centered and recalculates all instance
    'at' positions from min-corner to centroid coordinates.
    """
    spec = deep_copy_spec(spec)
    parts = spec["parts"]

    centroid_offsets: dict[str, tuple[float, float]] = {}
    for pid, pdef in parts.items():
        if pdef["kind"] == "rect":
            continue
        if part_ids is not None and pid not in part_ids:
            continue
        geom = part_geometry(pdef, anchor="min_corner")
        cx, cy = geom.centroid.x, geom.centroid.y
        centroid_offsets[pid] = (cx, cy)
        centered = part_to_geometry(pdef, anchor="centroid")
        pdef["geometry"] = {"format": "wkb_hex", "value": centered.wkb_hex}

    for icon_spec in spec["icons"].values():
        for inst in icon_spec["instances"]:
            pid = inst["part"]
            if pid not in centroid_offsets:
                continue
            ox, oy = centroid_offsets[pid]
            inst["at"] = [
                round(inst["at"][0] + ox, 9),
                round(inst["at"][1] + oy, 9),
            ]

    if part_ids is None:
        spec["allowed_transforms"]["rotate"] = True
    return spec


def merge_polygon_clusters(
    spec: dict, clusters: list[list[str]], rotations: dict[str, float] | None = None
) -> dict:
    """Create a spec where polygon clusters are merged to the most-used part.

    If rotations is provided, parts are centroid-anchored and instances record
    rotation offsets. The spec is converted to centroid anchor before merging.
    Rotation angles are recomputed relative to the keeper part.
    """
    use_rotation = rotations is not None

    if use_rotation:
        all_clustered = {pid for cluster in clusters for pid in cluster}
        spec = _convert_to_centroid_anchor(spec, part_ids=all_clustered)

    spec = deep_copy_spec(spec)
    parts = spec["parts"]

    for cluster in clusters:
        best = max(
            cluster,
            key=lambda pid: len(parts[pid].get("source_primitives", [])),
        )

        if use_rotation:
            keeper_geom = part_geometry(parts[best], anchor="centroid")
            # Recompute rotation of each member relative to keeper
            keeper_rots: dict[str, float] = {}
            for pid in cluster:
                if pid == best:
                    keeper_rots[pid] = 0.0
                    continue
                member_geom = part_geometry(parts[pid], anchor="centroid")
                # Find rotation of keeper that best matches member
                _hd, angle = _try_rotated_hausdorff(
                    member_geom, keeper_geom, angles=(0, 90, 180, 270)
                )
                keeper_rots[pid] = angle

        for pid in cluster:
            if pid == best:
                continue
            if "source_primitives" in parts[pid]:
                parts[best].setdefault("source_primitives", []).extend(
                    parts[pid]["source_primitives"]
                )
            del parts[pid]

        for icon_spec in spec["icons"].values():
            for inst in icon_spec["instances"]:
                if inst["part"] not in cluster or inst["part"] == best:
                    continue
                old_pid = inst["part"]
                inst["part"] = best
                if use_rotation:
                    angle = keeper_rots.get(old_pid, 0.0)
                    inst["rotate"] = round(angle, 3)

    return spec


def simplify_command(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        raise SystemExit(f"Part spec not found: {spec_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    ref_dir = Path(args.references)
    refs = {r[0]: r for r in load_references(ref_dir)}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline = score_spec(spec, refs)
    pareto_rows: list[dict] = [
        {
            "label": "exact_baseline",
            "unique_parts": baseline["unique_parts"],
            "total_instances": baseline["total_instances"],
            "area_error_ratio": baseline["overall_area_error_ratio"],
            "total_area_error": baseline["total_area_error"],
        }
    ]

    def _log_candidate(
        merged_spec: dict, label: str, extra: dict | None = None
    ) -> None:
        result = score_spec(merged_spec, refs)
        merged_path = out_dir / f"part-spec.{label}.v1.json"
        merged_path.write_text(
            json.dumps(merged_spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        worst_icon = max(
            (r["area_error_ratio"] for r in result["per_icon"]), default=0
        )
        row: dict = {
            "label": label,
            "unique_parts": result["unique_parts"],
            "total_instances": result["total_instances"],
            "area_error_ratio": result["overall_area_error_ratio"],
            "total_area_error": round(result["total_area_error"], 6),
            "worst_icon_error": worst_icon,
            "worst_hausdorff": result["worst_hausdorff"],
        }
        if extra:
            row.update(extra)
        pareto_rows.append(row)
        print(
            f"  {label}: {result['unique_parts']} parts "
            f"(area_err={result['overall_area_error_ratio']:.6g})"
        )

    # ---- rect size merges ----
    rect_tolerances = args.rect_tolerances or [0.5, 1.0, 2.0, 4.0]
    for tol in rect_tolerances:
        clusters = cluster_rects_by_size(spec["parts"], tol)
        if not clusters:
            print(f"  rect_tol={tol}: no mergeable clusters")
            continue
        merged = merge_rect_clusters(spec, clusters)
        _log_candidate(merged, f"rect_tol_{tol}", {"clusters_merged": len(clusters)})

    # ---- polygon Hausdorff merges (no rotation) ----
    poly_tolerances = args.polygon_tolerances or [0.5, 1.0, 2.0]
    for tol in poly_tolerances:
        clusters, _rot = cluster_polygons_by_hausdorff(spec["parts"], tol, allow_rotation=False)
        if not clusters:
            print(f"  poly_hd={tol}: no mergeable clusters")
            continue
        merged = merge_polygon_clusters(spec, clusters)
        _log_candidate(merged, f"poly_hausdorff_{tol}", {"clusters_merged": len(clusters)})

    # ---- polygon Hausdorff merges (with rotation) ----
    if not args.no_rotation:
        for tol in poly_tolerances:
            clusters, rotations = cluster_polygons_by_hausdorff(
                spec["parts"], tol, allow_rotation=True
            )
            if not clusters:
                print(f"  poly_rot_hd={tol}: no mergeable clusters")
                continue
            merged = merge_polygon_clusters(spec, clusters, rotations=rotations)
            _log_candidate(
                merged, f"poly_rot_hausdorff_{tol}", {"clusters_merged": len(clusters)}
            )

    # ---- combined: rect merging + polygon Hausdorff (with rotation) ----
    for rtol in rect_tolerances:
        for ptol in poly_tolerances:
            rect_clusters = cluster_rects_by_size(spec["parts"], rtol)
            poly_clusters, poly_rot = cluster_polygons_by_hausdorff(
                spec["parts"], ptol, allow_rotation=not args.no_rotation
            )
            if not rect_clusters and not poly_clusters:
                continue
            merged = spec
            if rect_clusters:
                merged = merge_rect_clusters(merged, rect_clusters)
            if poly_clusters:
                merged = merge_polygon_clusters(
                    merged, poly_clusters, rotations=poly_rot if not args.no_rotation else None
                )
            rot_tag = "_rot" if not args.no_rotation else ""
            _log_candidate(
                merged,
                f"combined_rtol{rtol}_phd{ptol}{rot_tag}",
                {"rect_clusters": len(rect_clusters), "poly_clusters": len(poly_clusters)},
            )

    # ---- bounding-box decomposition (radical) ----
    if not args.no_bbox_decompose:
        bbox_spec = decompose_polygons_to_bbox_rects_fixed(spec)
        _log_candidate(bbox_spec, "bbox_decompose")

    # ---- Pareto summary ----
    pareto_path = out_dir / "pareto.jsonl"
    with pareto_path.open("w", encoding="utf-8") as f:
        for row in pareto_rows:
            f.write(json.dumps(row) + "\n")

    print(f"\nsimplify: {len(pareto_rows)} candidates logged to {pareto_path}")
    print(f"\n{'label':<22s} {'parts':>6s} {'inst':>6s} {'area_err':>12s}  {'hausdorff':>10s}")
    print("-" * 64)
    for row in pareto_rows:
        h = row.get("worst_hausdorff", 0)
        print(
            f"{row['label']:<22s} {row['unique_parts']:>6d} {row['total_instances']:>6d} "
            f"{row['area_error_ratio']:>12.6g}  {h:>10.4f}"
        )

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    boot = subparsers.add_parser("bootstrap", help="Create exact part spec from references")
    boot.add_argument("--references", default="analysis/references", help="Reference JSON directory")
    boot.add_argument("--out", default="analysis/runs/exact", help="Output directory for part spec")
    boot.add_argument("--icons", nargs="*", help="Optional list of icon IDs to include")
    boot.add_argument("--curve-tolerance", type=float, default=iref.DEFAULT_CURVE_TOLERANCE)
    boot.add_argument("--coordinate-precision", type=float, default=iref.DEFAULT_COORDINATE_PRECISION)
    boot.set_defaults(func=bootstrap_command)

    rend = subparsers.add_parser("render", help="Reconstruct SVGs and overlays from part spec")
    rend.add_argument("--spec", default="analysis/runs/exact/part-spec.exact.v1.json", help="Part spec JSON")
    rend.add_argument("--references", default="analysis/references", help="Reference JSON directory")
    rend.add_argument("--out", default="analysis/runs/exact", help="Output directory for SVGs and overlays")
    rend.set_defaults(func=render_command)

    scor = subparsers.add_parser("score", help="Score part spec against references")
    scor.add_argument("--spec", default="analysis/runs/exact/part-spec.exact.v1.json", help="Part spec JSON")
    scor.add_argument("--references", default="analysis/references", help="Reference JSON directory")
    scor.add_argument("--out", help="Optional output path for metrics JSON")
    scor.add_argument("--verbose", action="store_true")
    scor.add_argument("--json", action="store_true", help="Print metrics as JSON")
    scor.set_defaults(func=score_command)

    simp = subparsers.add_parser("simplify", help="Greedy simplification: merge similar parts and score trades")
    simp.add_argument("--spec", default="analysis/runs/exact/part-spec.exact.v1.json", help="Part spec JSON")
    simp.add_argument("--references", default="analysis/references", help="Reference JSON directory")
    simp.add_argument("--out", default="analysis/runs/simplify", help="Output directory for merged specs and Pareto log")
    simp.add_argument("--rect-tolerances", nargs="*", type=float, help="Size tolerance steps for rect merging")
    simp.add_argument("--polygon-tolerances", nargs="*", type=float, help="Hausdorff tolerance steps for polygon merging")
    simp.add_argument("--no-bbox-decompose", action="store_true", help="Skip bounding-box decomposition")
    simp.add_argument("--no-rotation", action="store_true", help="Skip rotated polygon comparison")
    simp.set_defaults(func=simplify_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())