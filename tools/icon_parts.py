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
# render
# ---------------------------------------------------------------------------


def part_to_geometry(part_def: dict) -> object:
    """Convert a part definition to Shapely geometry at origin."""
    kind = part_def["kind"]
    if kind == "rect":
        w = part_def["width"]
        h = part_def["height"]
        return Polygon([
            (0, 0), (w, 0), (w, h), (0, h), (0, 0)
        ])
    geom_info = part_def["geometry"]
    if geom_info["format"] != "wkb_hex":
        raise ValueError(f"Unsupported geometry format: {geom_info['format']}")
    return wkb.loads(geom_info["value"], hex=True)


def translate_geometry(geom, dx: float, dy: float) -> object:
    """Translate a Shapely geometry by (dx, dy)."""
    from shapely import affinity
    return affinity.translate(geom, xoff=dx, yoff=dy)


def reconstruct_icon(
    icon_spec: dict, parts: dict, precision: float
) -> tuple[object, list[dict]]:
    """Reconstruct icon geometry from instances. Returns (unioned_geometry, instance_details)."""
    instance_geoms = []
    details = []
    for inst in icon_spec["instances"]:
        part_id = inst["part"]
        part_def = parts[part_id]
        base_geom = part_to_geometry(part_def)
        at_x, at_y = inst["at"]
        placed = translate_geometry(base_geom, at_x, at_y)
        instance_geoms.append(placed)
        details.append({"part": part_id, "at": [at_x, at_y], "geom": placed})
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
    parts = spec["parts"]

    ref_dir = Path(args.references)
    refs = {r[0]: r for r in load_references(ref_dir)}

    results: list[dict] = []
    total_area_error = 0.0
    total_ref_area = 0.0

    for icon_id, icon_spec in sorted(spec["icons"].items()):
        ref_info = refs.get(icon_id)
        if ref_info is None:
            print(f"  Warning: no reference found for {icon_id}, skipping")
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
        bounds_delta = max(
            abs(ref_bounds[i] - recon_bounds[i]) for i in range(4)
        )

        ref_components = iref.extract_polygons(ref_geom)
        recon_components = iref.extract_polygons(recon_geom)
        component_delta = len(recon_components) - len(ref_components)

        ref_metrics = ref.get("metrics", {})
        icon_result = {
            "icon_id": icon_id,
            "area_error": iref.round_float(area_error, precision),
            "area_error_ratio": iref.round_float(area_ratio, 1e-12),
            "hausdorff_distance": iref.round_float(hausdorff, precision),
            "bounds_delta": iref.round_float(bounds_delta, precision),
            "component_delta": component_delta,
            "ref_components": len(ref_components),
            "recon_components": len(recon_components),
            "ref_area": iref.round_float(ref_area, precision),
            "recon_area": iref.round_float(recon_geom.area, precision),
        }
        results.append(icon_result)
        total_area_error += area_error
        total_ref_area += ref_area

        if args.verbose:
            print(
                f"  {icon_id}: area_err={area_ratio:.6g}, "
                f"hausdorff={hausdorff:.4f}, "
                f"bounds_delta={bounds_delta:.4f}, "
                f"comp_delta={component_delta}"
            )

    unique_parts = len(parts)
    total_instances = sum(len(ic["instances"]) for ic in spec["icons"].values())
    overall_area_ratio = total_area_error / total_ref_area if total_ref_area > 0 else 0.0

    summary = {
        "unique_parts": unique_parts,
        "total_instances": total_instances,
        "icons_scored": len(results),
        "overall_area_error_ratio": iref.round_float(overall_area_ratio, 1e-12),
        "total_area_error": iref.round_float(total_area_error, precision),
        "per_icon": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"score: {len(results)} icons, {unique_parts} unique parts, {total_instances} instances")
        print(f"  overall area error ratio: {overall_area_ratio:.6g}")
        for r in results:
            print(
                f"  {r['icon_id']:30s}  area_err={r['area_error_ratio']:.6g}  "
                f"hausdorff={r['hausdorff_distance']:.4f}"
            )

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps({"summary": summary}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"  wrote metrics to {out_path}")

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())