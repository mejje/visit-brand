"""Export STEP geometry from generated icon references and part specs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from shapely import affinity, wkb
from shapely.geometry import MultiPolygon, Point, Polygon


FIXED_STEP_TIMESTAMP = "2026-06-27T00:00:00"
KIT_SCHEMA = "visit.icon-kit.v1"
SNAP_COUPON_SCHEMA = "visit.snapfit-coupon.v1"
SOCKET_BACKPLATE_SCHEMA = "visit.socket-backplate.v1"
DEFAULT_KIT_SPEC = "analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icon_parts as ip  # noqa: E402


def require_build123d():
    try:
        import build123d as b
    except ImportError as exc:
        raise SystemExit(
            "build123d is required for STEP export. Install it with: "
            "python -m pip install -r requirements-cad.txt"
        ) from exc
    return b


def load_reference(path: Path) -> tuple[dict, Polygon | MultiPolygon]:
    reference = json.loads(path.read_text(encoding="utf-8"))
    geometry_info = reference["geometry"]
    if geometry_info["format"] != "wkb_hex":
        raise ValueError(f"{path} uses unsupported geometry format {geometry_info['format']!r}")
    return reference, wkb.loads(geometry_info["value"], hex=True)


def polygons(geometry: Polygon | MultiPolygon) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    return list(geometry.geoms)


def load_part_spec(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Part spec not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def format_scope(scope: str) -> str:
    if scope == "universal":
        return "universal_single_icon"
    if scope == "all-icons":
        return "all_icons"
    return "single_icon"


def part_source_count(part_def: dict) -> int:
    return len(part_def.get("source_primitives", [])) + len(part_def.get("source_parts", []))


def icon_part_counts(spec: dict) -> dict[str, Counter]:
    counts = {}
    for icon_id, icon_spec in sorted(spec["icons"].items()):
        counts[icon_id] = Counter(inst["part"] for inst in icon_spec["instances"])
    return counts


def kit_quantities(
    counts_by_icon: dict[str, Counter],
    scope: str,
    icon_id: str | None = None,
) -> Counter:
    if scope == "icon":
        if not icon_id:
            raise SystemExit("--icon is required when --scope icon is used")
        if icon_id not in counts_by_icon:
            raise SystemExit(f"Icon not found in part spec: {icon_id}")
        return Counter(counts_by_icon[icon_id])

    quantities: Counter = Counter()
    for counts in counts_by_icon.values():
        for part_id, count in counts.items():
            if scope == "all-icons":
                quantities[part_id] += count
            else:
                quantities[part_id] = max(quantities[part_id], count)
    return quantities


def svg_to_mm_geometry(geometry, scale: float):
    return affinity.scale(geometry, xfact=scale, yfact=-scale, origin=(0, 0))


def geometry_size(geometry) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = geometry.bounds
    return max_x - min_x, max_y - min_y


def snap_enabled(args: argparse.Namespace) -> bool:
    return getattr(args, "snap_style", "none") != "none"


def snap_peg_positions(
    geometry,
    radius_mm: float,
    edge_clearance_mm: float,
    max_pegs: int,
) -> tuple[list[dict], str | None]:
    if max_pegs <= 0:
        return [], "snap_max_pegs_is_zero"
    if radius_mm <= 0:
        return [], "snap_peg_radius_not_positive"
    if edge_clearance_mm < 0:
        return [], "snap_edge_clearance_negative"

    inset = geometry.buffer(-(radius_mm + edge_clearance_mm))
    if inset.is_empty:
        return [], "footprint_too_small_for_snap_peg"

    min_x, min_y, max_x, max_y = inset.bounds
    fractions = (0.2, 0.35, 0.5, 0.65, 0.8)
    candidates: list[tuple[float, float]] = []
    for fx in fractions:
        for fy in fractions:
            point = Point(min_x + (max_x - min_x) * fx, min_y + (max_y - min_y) * fy)
            if inset.covers(point):
                candidates.append((float(point.x), float(point.y)))

    rep = inset.representative_point()
    candidates.append((float(rep.x), float(rep.y)))

    unique_candidates = []
    seen = set()
    for x, y in candidates:
        key = (round(x, 6), round(y, 6))
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append((x, y))

    if not unique_candidates:
        return [], "no_valid_interior_snap_point"

    selected = [unique_candidates[0]]
    while len(selected) < max_pegs and len(selected) < len(unique_candidates):
        best = None
        best_distance = -1.0
        for candidate in unique_candidates:
            if candidate in selected:
                continue
            distance = min(
                ((candidate[0] - chosen[0]) ** 2 + (candidate[1] - chosen[1]) ** 2) ** 0.5
                for chosen in selected
            )
            if distance > best_distance:
                best = candidate
                best_distance = distance
        if best is None:
            break
        selected.append(best)

    selected.sort()
    return [
        {
            "x_mm": round(x, 6),
            "y_mm": round(y, 6),
            "radius_mm": round(radius_mm, 6),
        }
        for x, y in selected
    ], None


def local_snap_peg_positions_svg(
    local_geometry,
    scale: float,
    radius_mm: float,
    edge_clearance_mm: float,
    max_pegs: int,
) -> tuple[list[dict], str | None]:
    geometry_mm = svg_to_mm_geometry(local_geometry, scale)
    pegs_mm, reason = snap_peg_positions(
        geometry_mm,
        radius_mm=radius_mm,
        edge_clearance_mm=edge_clearance_mm,
        max_pegs=max_pegs,
    )
    if not pegs_mm:
        return [], reason
    return [
        {
            "x_svg": peg["x_mm"] / scale,
            "y_svg": -peg["y_mm"] / scale,
            "radius_mm": peg["radius_mm"],
        }
        for peg in pegs_mm
    ], None


def place_svg_point(x_svg: float, y_svg: float, at_x: float, at_y: float, rotate: float = 0.0) -> tuple[float, float]:
    placed = ip.place_part(Point(x_svg, y_svg), at_x, at_y, rotate=rotate)
    return float(placed.x), float(placed.y)


def svg_point_to_plate_mm(
    x_svg: float,
    y_svg: float,
    source_size_svg: float,
    icon_size_mm: float,
    margin_mm: float,
) -> tuple[float, float]:
    scale = icon_size_mm / source_size_svg
    return margin_mm + x_svg * scale, margin_mm + (source_size_svg - y_svg) * scale


def part_usage_by_icon(counts_by_icon: dict[str, Counter], part_id: str) -> dict[str, int]:
    return {
        icon_id: int(counts[part_id])
        for icon_id, counts in counts_by_icon.items()
        if counts[part_id]
    }


def build_kit_pieces(
    spec: dict,
    quantities: Counter,
    scale: float,
    args: argparse.Namespace,
) -> tuple[list[dict], dict[str, dict]]:
    pieces = []
    part_details = {}
    for part_id in sorted(quantities):
        part_def = spec["parts"][part_id]
        geometry = svg_to_mm_geometry(ip.part_to_geometry(part_def), scale)
        width, height = geometry_size(geometry)
        min_x, min_y, max_x, max_y = geometry.bounds
        snap_pegs: list[dict] = []
        snap_status = "disabled"
        if snap_enabled(args):
            snap_pegs, reason = snap_peg_positions(
                geometry,
                radius_mm=args.snap_peg_radius_mm,
                edge_clearance_mm=args.snap_edge_clearance_mm,
                max_pegs=args.snap_max_pegs,
            )
            snap_status = "ok" if snap_pegs else f"skipped:{reason}"
        part_details[part_id] = {
            "kind": part_def["kind"],
            "quantity": int(quantities[part_id]),
            "source_count": part_source_count(part_def),
            "source_bounds_svg": part_def.get("bounds"),
            "footprint_mm": {
                "width": round(width, 6),
                "height": round(height, 6),
            },
            "cad_bounds_mm": [
                round(min_x, 6),
                round(min_y, 6),
                round(max_x, 6),
                round(max_y, 6),
            ],
            "min_feature_mm": round(float(part_def.get("print", {}).get("min_feature", 0.0)) * scale, 6),
            "snap_status": snap_status,
            "snap_pegs": snap_pegs,
        }
        for copy_index in range(1, int(quantities[part_id]) + 1):
            pieces.append({
                "piece_id": f"{part_id}__{copy_index:02d}",
                "part": part_id,
                "copy_index": copy_index,
                "geometry": geometry,
                "width": width,
                "height": height,
                "bounds": geometry.bounds,
                "snap_pegs": snap_pegs,
            })
    return pieces, part_details


def layout_pieces(
    pieces: list[dict],
    bed_width_mm: float,
    bed_depth_mm: float,
    spacing_mm: float,
) -> list[dict]:
    if bed_width_mm <= 0 or bed_depth_mm <= 0:
        raise SystemExit("Bed width and depth must be positive")
    if spacing_mm < 0:
        raise SystemExit("Spacing must be zero or positive")

    sorted_pieces = sorted(
        pieces,
        key=lambda piece: (-piece["height"], -piece["width"], piece["part"], piece["copy_index"]),
    )

    placements = []
    plate = 1
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0

    for piece in sorted_pieces:
        width = piece["width"]
        height = piece["height"]
        if width > bed_width_mm:
            raise SystemExit(
                f"{piece['part']} is {width:.2f}mm wide and does not fit bed width {bed_width_mm:.2f}mm"
            )
        if height > bed_depth_mm:
            raise SystemExit(
                f"{piece['part']} is {height:.2f}mm tall and does not fit bed depth {bed_depth_mm:.2f}mm"
            )

        if cursor_x > 0 and cursor_x + width > bed_width_mm:
            cursor_x = 0.0
            cursor_y += row_height + spacing_mm
            row_height = 0.0

        if cursor_y > 0 and cursor_y + height > bed_depth_mm:
            plate += 1
            cursor_x = 0.0
            cursor_y = 0.0
            row_height = 0.0

        min_x, min_y, _max_x, _max_y = piece["bounds"]
        placements.append({
            "piece_id": piece["piece_id"],
            "part": piece["part"],
            "copy_index": piece["copy_index"],
            "plate": plate,
            "x_mm": round(cursor_x, 6),
            "y_mm": round(cursor_y, 6),
            "geometry_xoff": cursor_x - min_x,
            "geometry_yoff": cursor_y - min_y,
            "width_mm": round(width, 6),
            "height_mm": round(height, 6),
            "snap_pegs_mm": [
                {
                    "x_mm": round(peg["x_mm"] + cursor_x - min_x, 6),
                    "y_mm": round(peg["y_mm"] + cursor_y - min_y, 6),
                    "radius_mm": peg["radius_mm"],
                }
                for peg in piece.get("snap_pegs", [])
            ],
        })

        cursor_x += width + spacing_mm
        row_height = max(row_height, height)

    return placements


def build_kit_plan(args: argparse.Namespace) -> tuple[dict, list[dict], dict[str, dict]]:
    spec_path = Path(args.spec)
    spec = load_part_spec(spec_path)
    if args.icon_size_mm <= 0:
        raise SystemExit("Icon size must be positive")
    if args.source_size_svg <= 0:
        raise SystemExit("Source SVG size must be positive")
    if args.front_depth_mm <= 0:
        raise SystemExit("Front depth must be positive")
    if snap_enabled(args):
        if args.snap_peg_radius_mm <= 0:
            raise SystemExit("Snap peg radius must be positive")
        if args.snap_peg_tip_radius_mm <= 0:
            raise SystemExit("Snap peg tip radius must be positive")
        if args.snap_peg_tip_radius_mm > args.snap_peg_radius_mm:
            raise SystemExit("Snap peg tip radius must be less than or equal to the peg radius")
        if args.snap_peg_height_mm <= 0:
            raise SystemExit("Snap peg height must be positive")
        if args.snap_max_pegs < 0:
            raise SystemExit("Snap max pegs must be zero or positive")

    counts_by_icon = icon_part_counts(spec)
    quantities = kit_quantities(counts_by_icon, args.scope, args.icon)
    scale = args.icon_size_mm / args.source_size_svg

    pieces, part_details = build_kit_pieces(spec, quantities, scale, args)
    placements = layout_pieces(
        pieces,
        bed_width_mm=args.bed_width_mm,
        bed_depth_mm=args.bed_depth_mm,
        spacing_mm=args.spacing_mm,
    )

    usage_by_icon = {
        icon_id: {
            "total_pieces": int(sum(counts.values())),
            "parts": {part_id: int(count) for part_id, count in sorted(counts.items())},
        }
        for icon_id, counts in counts_by_icon.items()
    }
    for part_id, detail in part_details.items():
        detail["used_by_icons"] = part_usage_by_icon(counts_by_icon, part_id)

    plate_count = max((placement["plate"] for placement in placements), default=0)
    layout_records = [
        {
            key: value
            for key, value in placement.items()
            if key not in {"geometry_xoff", "geometry_yoff"}
        }
        for placement in placements
    ]
    manifest = {
        "schema": KIT_SCHEMA,
        "generator": "tools/export_step.py kit-manifest",
        "source_spec": spec_path.as_posix(),
        "source_spec_hash": file_sha256(spec_path),
        "scope": format_scope(args.scope),
        "icon": args.icon if args.scope == "icon" else None,
        "icon_size_mm": args.icon_size_mm,
        "source_size_svg": args.source_size_svg,
        "scale_svg_to_mm": scale,
        "front_depth_mm": args.front_depth_mm,
        "total_unique_part_designs": len(quantities),
        "total_printed_pieces": int(sum(quantities.values())),
        "layout": {
            "strategy": "shelf_height_desc",
            "bed_width_mm": args.bed_width_mm,
            "bed_depth_mm": args.bed_depth_mm,
            "spacing_mm": args.spacing_mm,
            "plate_count": plate_count,
            "pieces": layout_records,
        },
        "snap_fit": {
            "style": args.snap_style,
            "peg_radius_mm": args.snap_peg_radius_mm if snap_enabled(args) else None,
            "peg_tip_radius_mm": args.snap_peg_tip_radius_mm if snap_enabled(args) else None,
            "peg_height_mm": args.snap_peg_height_mm if snap_enabled(args) else None,
            "edge_clearance_mm": args.snap_edge_clearance_mm if snap_enabled(args) else None,
            "max_pegs_per_piece": args.snap_max_pegs if snap_enabled(args) else None,
        },
        "icons": usage_by_icon,
        "parts": part_details,
    }

    pieces_by_id = {piece["piece_id"]: piece for piece in pieces}
    for placement in placements:
        placement["geometry"] = pieces_by_id[placement["piece_id"]]["geometry"]
    return manifest, placements, spec


def svg_to_cad_transform(viewbox: Sequence[float], icon_size_mm: float):
    min_x, min_y, width, height = viewbox
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid viewBox {viewbox}")
    scale = icon_size_mm / max(width, height)
    center_x = min_x + width / 2
    center_y = min_y + height / 2

    def transform(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return ((x - center_x) * scale, (center_y - y) * scale)

    return transform


def ring_points(coords: Iterable[tuple[float, float]], transform) -> list[tuple[float, float]]:
    points = list(coords)
    if points and points[0] == points[-1]:
        points = points[:-1]
    return [transform((float(x), float(y))) for x, y in points]


def reference_to_front_part(
    reference: dict,
    geometry: Polygon | MultiPolygon,
    icon_size_mm: float,
    front_depth_mm: float,
):
    b = require_build123d()
    transform = svg_to_cad_transform(reference["source"]["viewBox"], icon_size_mm)

    with b.BuildPart() as part_builder:
        with b.BuildSketch(b.Plane.XY):
            for polygon in polygons(geometry):
                b.Polygon(*ring_points(polygon.exterior.coords, transform), mode=b.Mode.ADD)
                for interior in polygon.interiors:
                    b.Polygon(*ring_points(interior.coords, transform), mode=b.Mode.SUBTRACT)
        b.extrude(amount=front_depth_mm)

    return part_builder.part


def export_front_command(args: argparse.Namespace) -> int:
    b = require_build123d()
    reference_path = Path(args.reference)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reference, geometry = load_reference(reference_path)
    part = reference_to_front_part(
        reference,
        geometry,
        icon_size_mm=args.icon_size_mm,
        front_depth_mm=args.front_depth_mm,
    )

    exported = b.export_step(part, output_path, timestamp=FIXED_STEP_TIMESTAMP)
    if not exported:
        raise SystemExit(f"Failed to export STEP: {output_path}")

    if args.verify_import:
        imported = b.import_step(output_path)
        imported_volume = float(getattr(imported, "volume", 0))
        source_volume = float(getattr(part, "volume", 0))
        volume_delta = abs(imported_volume - source_volume)
        if volume_delta > args.volume_tolerance:
            raise SystemExit(
                "STEP re-import volume mismatch: "
                f"source={source_volume:.6f}, imported={imported_volume:.6f}, "
                f"delta={volume_delta:.6f}"
            )
        print(
            f"exported {output_path.as_posix()} "
            f"volume={source_volume:.6f}mm^3 reimport_delta={volume_delta:.6f}"
        )
    else:
        print(f"exported {output_path.as_posix()}")
    return 0


def cad_geometry_to_part(
    b,
    geometry,
    front_depth_mm: float,
    snap_pegs: list[dict] | None = None,
    snap_peg_height_mm: float = 0.0,
    snap_peg_tip_radius_mm: float = 0.0,
):
    with b.BuildPart() as part_builder:
        with b.BuildSketch(b.Plane.XY):
            for polygon in polygons(geometry):
                b.Polygon(
                    *ring_points(polygon.exterior.coords, lambda point: point),
                    mode=b.Mode.ADD,
                )
                for interior in polygon.interiors:
                    b.Polygon(
                        *ring_points(interior.coords, lambda point: point),
                        mode=b.Mode.SUBTRACT,
                    )
        b.extrude(amount=front_depth_mm)
        for peg in snap_pegs or []:
            with b.Locations((peg["x_mm"], peg["y_mm"], front_depth_mm)):
                b.Cone(
                    bottom_radius=peg["radius_mm"],
                    top_radius=snap_peg_tip_radius_mm,
                    height=snap_peg_height_mm,
                    align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN),
                    mode=b.Mode.ADD,
                )
    return part_builder.part


def kit_compound(
    b,
    placements: list[dict],
    front_depth_mm: float,
    bed_depth_mm: float,
    plate_gap_mm: float,
    snap_peg_height_mm: float = 0.0,
    snap_peg_tip_radius_mm: float = 0.0,
    plate: int | None = None,
):
    children = []
    for placement in placements:
        if plate is not None and placement["plate"] != plate:
            continue
        plate_offset_y = 0.0
        if plate is None:
            plate_offset_y = (placement["plate"] - 1) * (bed_depth_mm + plate_gap_mm)
        geometry = affinity.translate(
            placement["geometry"],
            xoff=placement["geometry_xoff"],
            yoff=placement["geometry_yoff"] + plate_offset_y,
        )
        snap_pegs = [
            {**peg, "y_mm": peg["y_mm"] + plate_offset_y}
            for peg in placement.get("snap_pegs_mm", [])
        ]
        part = cad_geometry_to_part(
            b,
            geometry,
            front_depth_mm,
            snap_pegs=snap_pegs,
            snap_peg_height_mm=snap_peg_height_mm,
            snap_peg_tip_radius_mm=snap_peg_tip_radius_mm,
        )
        part.label = placement["piece_id"]
        children.append(part)
    if not children:
        raise SystemExit("No kit pieces to export")
    return b.Compound(children=children, label="visit_icon_kit")


def export_shape_step(
    b,
    shape,
    output_path: Path,
    verify_import: bool,
    volume_tolerance: float,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exported = b.export_step(shape, output_path, timestamp=FIXED_STEP_TIMESTAMP)
    if not exported:
        raise SystemExit(f"Failed to export STEP: {output_path}")

    source_volume = float(getattr(shape, "volume", 0))
    result = {
        "path": output_path.as_posix(),
        "volume_mm3": round(source_volume, 6),
    }
    if verify_import:
        imported = b.import_step(output_path)
        imported_volume = float(getattr(imported, "volume", 0))
        volume_delta = abs(imported_volume - source_volume)
        if volume_delta > volume_tolerance:
            raise SystemExit(
                "STEP re-import volume mismatch: "
                f"source={source_volume:.6f}, imported={imported_volume:.6f}, "
                f"delta={volume_delta:.6f}"
            )
        result["reimport_volume_mm3"] = round(imported_volume, 6)
        result["reimport_delta_mm3"] = round(volume_delta, 9)
    return result


def write_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_clearances(value: str) -> list[float]:
    clearances = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        clearances.append(float(item))
    if not clearances:
        raise SystemExit("At least one clearance value is required")
    if any(clearance < 0 for clearance in clearances):
        raise SystemExit("Snap clearances must be zero or positive")
    return clearances


def snap_coupon_shape(b, args: argparse.Namespace, clearances: list[float]):
    if args.snap_peg_radius_mm <= 0:
        raise SystemExit("Snap peg radius must be positive")
    if args.snap_peg_tip_radius_mm <= 0:
        raise SystemExit("Snap peg tip radius must be positive")
    if args.snap_peg_tip_radius_mm > args.snap_peg_radius_mm:
        raise SystemExit("Snap peg tip radius must be less than or equal to the peg radius")
    if args.snap_peg_height_mm <= 0:
        raise SystemExit("Snap peg height must be positive")
    if args.coupon_socket_depth_mm <= 0:
        raise SystemExit("Coupon socket depth must be positive")
    if args.coupon_socket_block_thickness_mm <= args.coupon_socket_depth_mm:
        raise SystemExit("Coupon socket block thickness must be greater than socket depth")

    count = len(clearances)
    length = args.coupon_edge_margin_mm * 2 + args.coupon_pitch_mm * (count - 1)
    width = args.coupon_width_mm
    peg_y = width / 2

    peg_positions = [
        (args.coupon_edge_margin_mm + index * args.coupon_pitch_mm, peg_y)
        for index in range(count)
    ]

    with b.BuildPart() as male_builder:
        b.Box(
            length,
            width,
            args.coupon_base_thickness_mm,
            align=(b.Align.MIN, b.Align.MIN, b.Align.MIN),
        )
        for x, y in peg_positions:
            with b.Locations((x, y, args.coupon_base_thickness_mm)):
                b.Cone(
                    bottom_radius=args.snap_peg_radius_mm,
                    top_radius=args.snap_peg_tip_radius_mm,
                    height=args.snap_peg_height_mm,
                    align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN),
                    mode=b.Mode.ADD,
                )
    male = male_builder.part
    male.label = "snap_coupon_male_pegs"

    with b.BuildPart() as socket_builder:
        b.Box(
            length,
            width,
            args.coupon_socket_block_thickness_mm,
            align=(b.Align.MIN, b.Align.MIN, b.Align.MIN),
        )
        socket_z = args.coupon_socket_block_thickness_mm - args.coupon_socket_depth_mm
        for (x, y), clearance in zip(peg_positions, clearances):
            with b.Locations((x, y, socket_z)):
                b.Cylinder(
                    args.snap_peg_radius_mm + clearance,
                    args.coupon_socket_depth_mm,
                    align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN),
                    mode=b.Mode.SUBTRACT,
                )
    socket = socket_builder.part
    socket = socket.moved(b.Location((0, width + args.coupon_gap_mm, 0)))
    socket.label = "snap_coupon_socket_block"

    manifest = {
        "schema": SNAP_COUPON_SCHEMA,
        "generator": "tools/export_step.py snap-coupon",
        "snap_fit": {
            "style": "friction_peg",
            "peg_radius_mm": args.snap_peg_radius_mm,
            "peg_tip_radius_mm": args.snap_peg_tip_radius_mm,
            "peg_height_mm": args.snap_peg_height_mm,
            "socket_depth_mm": args.coupon_socket_depth_mm,
            "socket_block_thickness_mm": args.coupon_socket_block_thickness_mm,
        },
        "coupon": {
            "male_base_thickness_mm": args.coupon_base_thickness_mm,
            "width_mm": width,
            "length_mm": length,
            "pitch_mm": args.coupon_pitch_mm,
            "gap_mm": args.coupon_gap_mm,
            "tests": [
                {
                    "index": index + 1,
                    "clearance_mm": clearance,
                    "socket_radius_mm": round(args.snap_peg_radius_mm + clearance, 6),
                    "x_mm": round(x, 6),
                    "male_y_mm": round(y, 6),
                    "socket_y_mm": round(y + width + args.coupon_gap_mm, 6),
                }
                for index, ((x, y), clearance) in enumerate(zip(peg_positions, clearances))
            ],
        },
    }
    return b.Compound(children=[male, socket], label="snapfit_coupon"), manifest


def socket_backplate_plan(args: argparse.Namespace) -> tuple[dict, list[dict]]:
    spec_path = Path(args.spec)
    spec = load_part_spec(spec_path)
    if args.icon not in spec["icons"]:
        raise SystemExit(f"Icon not found in part spec: {args.icon}")
    if args.icon_size_mm <= 0:
        raise SystemExit("Icon size must be positive")
    if args.source_size_svg <= 0:
        raise SystemExit("Source SVG size must be positive")
    if args.backplate_margin_mm < 0:
        raise SystemExit("Backplate margin must be zero or positive")
    if args.backplate_thickness_mm <= 0:
        raise SystemExit("Backplate thickness must be positive")
    if args.socket_depth_mm <= 0:
        raise SystemExit("Socket depth must be positive")
    if args.socket_depth_mm >= args.backplate_thickness_mm:
        raise SystemExit("Socket depth must be less than backplate thickness")
    if args.socket_clearance_mm < 0:
        raise SystemExit("Socket clearance must be zero or positive")
    if args.pin_hole_diameter_mm <= 0:
        raise SystemExit("Pin hole diameter must be positive")
    if args.pin_hole_side_inset_mm <= args.pin_hole_diameter_mm / 2:
        raise SystemExit("Pin hole side inset must leave room for the hole radius")
    if args.pin_hole_top_inset_mm <= args.pin_hole_diameter_mm / 2:
        raise SystemExit("Pin hole top inset must leave room for the hole radius")
    if args.snap_peg_radius_mm <= 0:
        raise SystemExit("Snap peg radius must be positive")
    if args.snap_edge_clearance_mm < 0:
        raise SystemExit("Snap edge clearance must be zero or positive")
    if args.snap_max_pegs <= 0:
        raise SystemExit("Snap max pegs must be positive")

    scale = args.icon_size_mm / args.source_size_svg
    sockets = []
    skipped = []
    for instance_index, inst in enumerate(spec["icons"][args.icon]["instances"]):
        part_id = inst["part"]
        part_def = spec["parts"][part_id]
        rotate = inst.get("rotate", None)
        anchor = "centroid" if rotate is not None else "min_corner"
        local_geometry = ip.part_to_geometry(part_def, anchor=anchor)
        local_pegs, reason = local_snap_peg_positions_svg(
            local_geometry,
            scale=scale,
            radius_mm=args.snap_peg_radius_mm,
            edge_clearance_mm=args.snap_edge_clearance_mm,
            max_pegs=args.snap_max_pegs,
        )
        if not local_pegs:
            skipped.append({
                "instance_index": instance_index,
                "part": part_id,
                "reason": reason,
            })
            continue

        at_x, at_y = inst["at"]
        rotation = rotate or 0.0
        for peg_index, peg in enumerate(local_pegs, start=1):
            icon_x, icon_y = place_svg_point(
                peg["x_svg"],
                peg["y_svg"],
                at_x,
                at_y,
                rotate=rotation,
            )
            plate_x, plate_y = svg_point_to_plate_mm(
                icon_x,
                icon_y,
                source_size_svg=args.source_size_svg,
                icon_size_mm=args.icon_size_mm,
                margin_mm=args.backplate_margin_mm,
            )
            sockets.append({
                "socket_id": f"socket_{instance_index + 1:02d}_{peg_index:02d}",
                "instance_index": instance_index,
                "source_index": inst.get("source_index"),
                "part": part_id,
                "peg_index": peg_index,
                "rotate": rotate,
                "icon_svg": [round(icon_x, 9), round(icon_y, 9)],
                "x_mm": round(plate_x, 6),
                "y_mm": round(plate_y, 6),
                "peg_radius_mm": round(args.snap_peg_radius_mm, 6),
                "socket_radius_mm": round(args.snap_peg_radius_mm + args.socket_clearance_mm, 6),
            })

    width = args.icon_size_mm + args.backplate_margin_mm * 2
    height = args.icon_size_mm + args.backplate_margin_mm * 2
    if args.pin_hole_side_inset_mm >= width / 2:
        raise SystemExit("Pin hole side inset is too large for the backplate width")
    if args.pin_hole_top_inset_mm >= height:
        raise SystemExit("Pin hole top inset is too large for the backplate height")

    pin_holes = [
        {
            "hole_id": "pin_left",
            "x_mm": round(args.pin_hole_side_inset_mm, 6),
            "y_mm": round(height - args.pin_hole_top_inset_mm, 6),
            "diameter_mm": round(args.pin_hole_diameter_mm, 6),
        },
        {
            "hole_id": "pin_right",
            "x_mm": round(width - args.pin_hole_side_inset_mm, 6),
            "y_mm": round(height - args.pin_hole_top_inset_mm, 6),
            "diameter_mm": round(args.pin_hole_diameter_mm, 6),
        },
    ]

    socket_radius = args.snap_peg_radius_mm + args.socket_clearance_mm
    collisions = []
    for i, a in enumerate(sockets):
        for b_socket in sockets[i + 1:]:
            distance = ((a["x_mm"] - b_socket["x_mm"]) ** 2 + (a["y_mm"] - b_socket["y_mm"]) ** 2) ** 0.5
            if distance < socket_radius * 2:
                collisions.append({
                    "a": a["socket_id"],
                    "b": b_socket["socket_id"],
                    "distance_mm": round(distance, 6),
                })
    if collisions:
        raise SystemExit(f"Socket collisions detected: {collisions}")
    hole_collisions = []
    for socket in sockets:
        for hole in pin_holes:
            distance = ((socket["x_mm"] - hole["x_mm"]) ** 2 + (socket["y_mm"] - hole["y_mm"]) ** 2) ** 0.5
            if distance < socket["socket_radius_mm"] + hole["diameter_mm"] / 2:
                hole_collisions.append({
                    "socket": socket["socket_id"],
                    "pin_hole": hole["hole_id"],
                    "distance_mm": round(distance, 6),
                })
    if hole_collisions:
        raise SystemExit(f"Pin holes overlap snap sockets: {hole_collisions}")

    manifest = {
        "schema": SOCKET_BACKPLATE_SCHEMA,
        "generator": "tools/export_step.py socket-backplate",
        "source_spec": spec_path.as_posix(),
        "source_spec_hash": file_sha256(spec_path),
        "icon": args.icon,
        "icon_size_mm": args.icon_size_mm,
        "source_size_svg": args.source_size_svg,
        "scale_svg_to_mm": scale,
        "backplate": {
            "width_mm": round(width, 6),
            "height_mm": round(height, 6),
            "thickness_mm": args.backplate_thickness_mm,
            "margin_mm": args.backplate_margin_mm,
            "pin_holes": pin_holes,
        },
        "snap_fit": {
            "style": "friction_peg_socket",
            "provisional": args.provisional,
            "peg_radius_mm": args.snap_peg_radius_mm,
            "socket_clearance_mm": args.socket_clearance_mm,
            "socket_radius_mm": round(socket_radius, 6),
            "socket_depth_mm": args.socket_depth_mm,
            "snap_edge_clearance_mm": args.snap_edge_clearance_mm,
            "max_pegs_per_piece": args.snap_max_pegs,
        },
        "sockets": sockets,
        "skipped_instances": skipped,
    }
    return manifest, sockets


def socket_backplate_shape(b, manifest: dict, args: argparse.Namespace):
    backplate = manifest["backplate"]
    socket_z = args.backplate_thickness_mm - args.socket_depth_mm
    with b.BuildPart() as backplate_builder:
        b.Box(
            backplate["width_mm"],
            backplate["height_mm"],
            args.backplate_thickness_mm,
            align=(b.Align.MIN, b.Align.MIN, b.Align.MIN),
        )
        for socket in manifest["sockets"]:
            with b.Locations((socket["x_mm"], socket["y_mm"], socket_z)):
                b.Cylinder(
                    socket["socket_radius_mm"],
                    args.socket_depth_mm,
                    align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN),
                    mode=b.Mode.SUBTRACT,
                )
        pin_cut_height = args.backplate_thickness_mm + 0.2
        for hole in backplate["pin_holes"]:
            with b.Locations((hole["x_mm"], hole["y_mm"], -0.1)):
                b.Cylinder(
                    hole["diameter_mm"] / 2,
                    pin_cut_height,
                    align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN),
                    mode=b.Mode.SUBTRACT,
                )
    part = backplate_builder.part
    part.label = f"{args.icon}_socket_backplate"
    return part


def socket_backplate_command(args: argparse.Namespace) -> int:
    b = require_build123d()
    manifest, _sockets = socket_backplate_plan(args)
    shape = socket_backplate_shape(b, manifest, args)
    output_path = Path(args.out)
    manifest["output"] = export_shape_step(
        b,
        shape,
        output_path,
        verify_import=args.verify_import,
        volume_tolerance=args.volume_tolerance,
    )
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    write_manifest(manifest_path, manifest)
    print(
        f"socket backplate: {args.icon}, {len(manifest['sockets'])} sockets -> {output_path.as_posix()}"
    )
    print(f"socket backplate manifest: {manifest_path.as_posix()}")
    return 0


def snap_coupon_command(args: argparse.Namespace) -> int:
    b = require_build123d()
    clearances = parse_clearances(args.clearances)
    shape, manifest = snap_coupon_shape(b, args, clearances)
    output_path = Path(args.out)
    manifest["output"] = export_shape_step(
        b,
        shape,
        output_path,
        verify_import=args.verify_import,
        volume_tolerance=args.volume_tolerance,
    )
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    write_manifest(manifest_path, manifest)
    print(
        f"snap coupon: {len(clearances)} clearances -> {output_path.as_posix()}"
    )
    print(f"snap coupon manifest: {manifest_path.as_posix()}")
    return 0


def kit_manifest_command(args: argparse.Namespace) -> int:
    manifest, _placements, _spec = build_kit_plan(args)
    out_path = Path(args.out)
    write_manifest(out_path, manifest)
    print(
        f"kit manifest: {manifest['total_unique_part_designs']} designs, "
        f"{manifest['total_printed_pieces']} pieces, "
        f"{manifest['layout']['plate_count']} plates -> {out_path.as_posix()}"
    )
    return 0


def export_kit_command(args: argparse.Namespace) -> int:
    b = require_build123d()
    manifest, placements, _spec = build_kit_plan(args)
    output_path = Path(args.out)

    compound = kit_compound(
        b,
        placements,
        front_depth_mm=args.front_depth_mm,
        bed_depth_mm=args.bed_depth_mm,
        plate_gap_mm=args.plate_gap_mm,
        snap_peg_height_mm=args.snap_peg_height_mm if snap_enabled(args) else 0.0,
        snap_peg_tip_radius_mm=args.snap_peg_tip_radius_mm if snap_enabled(args) else 0.0,
    )
    outputs = {
        "combined_step": export_shape_step(
            b,
            compound,
            output_path,
            verify_import=args.verify_import,
            volume_tolerance=args.volume_tolerance,
        )
    }

    if args.split_plates:
        plate_outputs = []
        plate_count = manifest["layout"]["plate_count"]
        for plate in range(1, plate_count + 1):
            plate_path = output_path.with_name(
                f"{output_path.stem}.plate_{plate:02d}{output_path.suffix}"
            )
            plate_shape = kit_compound(
                b,
                placements,
                front_depth_mm=args.front_depth_mm,
                bed_depth_mm=args.bed_depth_mm,
                plate_gap_mm=args.plate_gap_mm,
                snap_peg_height_mm=args.snap_peg_height_mm if snap_enabled(args) else 0.0,
                snap_peg_tip_radius_mm=args.snap_peg_tip_radius_mm if snap_enabled(args) else 0.0,
                plate=plate,
            )
            plate_outputs.append(
                export_shape_step(
                    b,
                    plate_shape,
                    plate_path,
                    verify_import=args.verify_import,
                    volume_tolerance=args.volume_tolerance,
                )
            )
        outputs["plate_steps"] = plate_outputs

    manifest["generator"] = "tools/export_step.py kit"
    manifest["outputs"] = outputs
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    write_manifest(manifest_path, manifest)
    print(
        f"kit STEP: {manifest['total_unique_part_designs']} designs, "
        f"{manifest['total_printed_pieces']} pieces, "
        f"{manifest['layout']['plate_count']} plates -> {output_path.as_posix()}"
    )
    print(f"kit manifest: {manifest_path.as_posix()}")
    return 0


def add_kit_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default=DEFAULT_KIT_SPEC, help="Input part spec JSON")
    parser.add_argument(
        "--scope",
        choices=["universal", "icon", "all-icons"],
        default="universal",
        help="Kit quantity scope: universal single-icon max, one icon, or all icons",
    )
    parser.add_argument("--icon", help="Icon id when --scope icon is used")
    parser.add_argument("--icon-size-mm", type=float, default=120.0)
    parser.add_argument("--source-size-svg", type=float, default=48.0)
    parser.add_argument("--front-depth-mm", type=float, default=8.0)
    parser.add_argument("--bed-width-mm", type=float, default=180.0)
    parser.add_argument("--bed-depth-mm", type=float, default=180.0)
    parser.add_argument("--spacing-mm", type=float, default=4.0)
    parser.add_argument(
        "--snap-style",
        choices=["none", "friction-peg"],
        default="none",
        help="Optional back-side snap feature for front pieces",
    )
    parser.add_argument("--snap-peg-radius-mm", type=float, default=1.8)
    parser.add_argument("--snap-peg-tip-radius-mm", type=float, default=1.55)
    parser.add_argument("--snap-peg-height-mm", type=float, default=3.0)
    parser.add_argument("--snap-edge-clearance-mm", type=float, default=1.0)
    parser.add_argument("--snap-max-pegs", type=int, default=2)


def add_snap_coupon_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", required=True, help="Output snap-fit coupon STEP file")
    parser.add_argument("--manifest", help="Optional output manifest JSON path")
    parser.add_argument("--clearances", default="0.1,0.2,0.3,0.4")
    parser.add_argument("--snap-peg-radius-mm", type=float, default=1.8)
    parser.add_argument("--snap-peg-tip-radius-mm", type=float, default=1.55)
    parser.add_argument("--snap-peg-height-mm", type=float, default=3.0)
    parser.add_argument("--coupon-socket-depth-mm", type=float, default=3.2)
    parser.add_argument("--coupon-socket-block-thickness-mm", type=float, default=4.0)
    parser.add_argument("--coupon-base-thickness-mm", type=float, default=2.0)
    parser.add_argument("--coupon-width-mm", type=float, default=16.0)
    parser.add_argument("--coupon-pitch-mm", type=float, default=14.0)
    parser.add_argument("--coupon-edge-margin-mm", type=float, default=8.0)
    parser.add_argument("--coupon-gap-mm", type=float, default=8.0)
    parser.add_argument("--verify-import", action="store_true", help="Re-import exported STEP and compare volume")
    parser.add_argument("--volume-tolerance", type=float, default=1e-6)


def add_socket_backplate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default=DEFAULT_KIT_SPEC, help="Input part spec JSON")
    parser.add_argument("--icon", required=True, help="Icon id to generate a socket backplate for")
    parser.add_argument("--out", required=True, help="Output socket backplate STEP file")
    parser.add_argument("--manifest", help="Optional output manifest JSON path")
    parser.add_argument("--icon-size-mm", type=float, default=120.0)
    parser.add_argument("--source-size-svg", type=float, default=48.0)
    parser.add_argument("--backplate-margin-mm", type=float, default=6.0)
    parser.add_argument("--backplate-thickness-mm", type=float, default=4.0)
    parser.add_argument("--pin-hole-diameter-mm", type=float, default=2.0)
    parser.add_argument("--pin-hole-side-inset-mm", type=float, default=12.0)
    parser.add_argument("--pin-hole-top-inset-mm", type=float, default=6.0)
    parser.add_argument("--socket-clearance-mm", type=float, default=0.3)
    parser.add_argument("--socket-depth-mm", type=float, default=3.2)
    parser.add_argument("--snap-peg-radius-mm", type=float, default=1.8)
    parser.add_argument("--snap-edge-clearance-mm", type=float, default=1.0)
    parser.add_argument("--snap-max-pegs", type=int, default=2)
    parser.add_argument(
        "--provisional",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Mark socket clearance as provisional until coupon print validation",
    )
    parser.add_argument("--verify-import", action="store_true", help="Re-import exported STEP and compare volume")
    parser.add_argument("--volume-tolerance", type=float, default=1e-6)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    front = subparsers.add_parser("front", help="Export a raised front icon STEP from reference geometry")
    front.add_argument("--reference", required=True, help="Input *.reference.json file")
    front.add_argument("--out", required=True, help="Output STEP file")
    front.add_argument("--icon-size-mm", type=float, default=120.0)
    front.add_argument("--front-depth-mm", type=float, default=8.0)
    front.add_argument("--verify-import", action="store_true", help="Re-import the STEP and compare volume")
    front.add_argument("--volume-tolerance", type=float, default=1e-6)
    front.set_defaults(func=export_front_command)

    manifest = subparsers.add_parser("kit-manifest", help="Write a printable kit BOM and layout manifest")
    add_kit_arguments(manifest)
    manifest.add_argument("--out", required=True, help="Output kit manifest JSON")
    manifest.set_defaults(func=kit_manifest_command)

    kit = subparsers.add_parser("kit", help="Export laid-out kit pieces from a part spec to STEP")
    add_kit_arguments(kit)
    kit.add_argument("--out", required=True, help="Output combined STEP file")
    kit.add_argument("--manifest", help="Optional output manifest JSON path")
    kit.add_argument("--split-plates", action="store_true", help="Also write one STEP file per plate")
    kit.add_argument("--plate-gap-mm", type=float, default=20.0)
    kit.add_argument("--verify-import", action="store_true", help="Re-import exported STEP files and compare volume")
    kit.add_argument("--volume-tolerance", type=float, default=1e-6)
    kit.set_defaults(func=export_kit_command)

    coupon = subparsers.add_parser("snap-coupon", help="Export a friction-peg snap-fit clearance coupon")
    add_snap_coupon_arguments(coupon)
    coupon.set_defaults(func=snap_coupon_command)

    backplate = subparsers.add_parser(
        "socket-backplate",
        help="Export a socket backplate matching snap-enabled icon front pieces",
    )
    add_socket_backplate_arguments(backplate)
    backplate.set_defaults(func=socket_backplate_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
