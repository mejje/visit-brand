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
PART_FIXTURE_KIT_SCHEMA = "visit.part-fixture-kit.v1"
FIT_COUPON_KIT_SCHEMA = "visit.fit-coupon-kit.v1"
DEFAULT_KIT_SPEC = "analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json"
DEFAULT_PHYSICAL_MARK_FONT = "Arial"
DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM = 4.0
DEFAULT_PHYSICAL_MARK_DEPTH_MM = 0.25
DEFAULT_FIT_COUPON_CLEARANCES = (0.15, 0.25, 0.35)

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


def mark_font_size_mm(mark: str, geometry, requested_size_mm: float) -> float:
    """Pick a conservative font size that fits inside narrow icon parts."""
    width, height = geometry_size(geometry)
    char_count = max(len(mark), 1)
    by_height = max(min(width, height) * 0.55, 1.2)
    by_width = max((width * 0.75) / (char_count * 0.58), 1.2)
    return max(min(requested_size_mm, by_height, by_width), 1.2)


def mark_point(geometry) -> tuple[float, float]:
    point = geometry.representative_point()
    return float(point.x), float(point.y)


def physical_marks_enabled(args: argparse.Namespace) -> bool:
    return not getattr(args, "no_physical_marks", False)


def validate_physical_mark_args(
    args: argparse.Namespace,
    max_depths_mm: dict[str, float],
) -> None:
    if not physical_marks_enabled(args):
        return
    if args.physical_mark_font_size_mm <= 0:
        raise SystemExit("Physical mark font size must be positive")
    if args.physical_mark_depth_mm <= 0:
        raise SystemExit("Physical mark depth must be positive")
    for label, max_depth in max_depths_mm.items():
        if args.physical_mark_depth_mm >= max_depth:
            raise SystemExit(
                f"Physical mark depth must be less than {label} thickness ({max_depth:.3f}mm)"
            )


def physical_marking_manifest(args: argparse.Namespace, **locations: str) -> dict:
    enabled = physical_marks_enabled(args)
    return {
        "cad_text_geometry": enabled,
        "style": "engraved" if enabled else "none",
        "font": args.physical_mark_font,
        "max_font_size_mm": args.physical_mark_font_size_mm,
        "depth_mm": args.physical_mark_depth_mm if enabled else 0.0,
        **locations,
    }


def inset_geometry(geometry, inset_mm: float, label: str):
    if inset_mm < 0:
        raise SystemExit(f"{label} inset must be zero or positive")
    if inset_mm == 0:
        return geometry
    inset = geometry.buffer(-inset_mm, join_style=2)
    if inset.is_empty:
        raise SystemExit(f"{label} inset of {inset_mm:.3f}mm removes the part footprint")
    return inset


def mounting_hole_positions(
    geometry,
    hole_radius_mm: float,
    edge_clearance_mm: float,
    min_spacing_mm: float,
) -> tuple[list[dict], str | None]:
    if hole_radius_mm <= 0:
        return [], "hole_radius_not_positive"
    if edge_clearance_mm < 0:
        return [], "hole_edge_clearance_negative"
    if min_spacing_mm < 0:
        return [], "hole_min_spacing_negative"

    usable = geometry.buffer(-(hole_radius_mm + edge_clearance_mm), join_style=2)
    if usable.is_empty:
        return [], "backplate_too_small_for_mounting_holes"

    min_x, min_y, max_x, max_y = usable.bounds
    fractions = tuple(index / 20 for index in range(1, 20))
    candidates: list[tuple[float, float]] = []
    for fx in fractions:
        for fy in fractions:
            point = Point(min_x + (max_x - min_x) * fx, min_y + (max_y - min_y) * fy)
            if usable.covers(point):
                candidates.append((float(point.x), float(point.y)))

    rep = usable.representative_point()
    candidates.append((float(rep.x), float(rep.y)))
    for component in polygons(usable):
        component_rep = component.representative_point()
        candidates.append((float(component_rep.x), float(component_rep.y)))

    unique_candidates = []
    seen = set()
    for x, y in candidates:
        key = (round(x, 6), round(y, 6))
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append((x, y))

    if len(unique_candidates) < 2:
        return [], "not_enough_valid_mounting_hole_points"

    best_pair = None
    best_distance = -1.0
    for index, first in enumerate(unique_candidates):
        for second in unique_candidates[index + 1:]:
            distance = ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5
            if distance > best_distance:
                best_pair = (first, second)
                best_distance = distance

    if best_pair is None:
        return [], "no_mounting_hole_pair_found"
    if best_distance < min_spacing_mm:
        return [], f"mounting_hole_spacing_below_{min_spacing_mm:.3f}mm"

    return [
        {
            "hole_id": "mount_01",
            "x_mm": round(best_pair[0][0], 6),
            "y_mm": round(best_pair[0][1], 6),
            "diameter_mm": round(hole_radius_mm * 2, 6),
        },
        {
            "hole_id": "mount_02",
            "x_mm": round(best_pair[1][0], 6),
            "y_mm": round(best_pair[1][1], 6),
            "diameter_mm": round(hole_radius_mm * 2, 6),
        },
    ], None


def part_usage_by_icon(counts_by_icon: dict[str, Counter], part_id: str) -> dict[str, int]:
    return {
        icon_id: int(counts[part_id])
        for icon_id, counts in counts_by_icon.items()
        if counts[part_id]
    }


def part_number_map(part_ids: Iterable[str]) -> dict[str, int]:
    return {
        part_id: index
        for index, part_id in enumerate(sorted(part_ids), start=1)
    }


def part_number_mark(part_numbers: dict[str, int], part_id: str) -> str:
    return str(part_numbers[part_id])


def step_part_label(part_numbers: dict[str, int], part_id: str) -> str:
    return f"part_{part_numbers[part_id]:03d}"


def fixture_piece_ids(part_id: str, copy_index: int) -> tuple[str, str]:
    return (
        f"{part_id}__{copy_index:02d}__front_cap",
        f"{part_id}__{copy_index:02d}__backplate",
    )


def icon_ids_for_scope(spec: dict, scope: str, icon_id: str | None) -> list[str]:
    if scope == "icon":
        if not icon_id:
            raise SystemExit("--icon is required when --scope icon is used")
        if icon_id not in spec["icons"]:
            raise SystemExit(f"Icon not found in part spec: {icon_id}")
        return [icon_id]
    return sorted(spec["icons"])


def round_float_list(values: Iterable[float], digits: int = 6) -> list[float]:
    return [round(float(value), digits) for value in values]


def icon_assembly_map(
    spec: dict,
    quantities: Counter,
    scope: str,
    icon_id: str | None = None,
    part_numbers: dict[str, int] | None = None,
) -> dict:
    """Map global part numbers to icon placements and printed fixture IDs."""
    if part_numbers is None:
        part_numbers = part_number_map(quantities)
    assembly_icons = {}
    global_copy_counts: Counter = Counter()

    for current_icon_id in icon_ids_for_scope(spec, scope, icon_id):
        icon_spec = spec["icons"][current_icon_id]
        local_copy_counts: Counter = Counter()
        placements = []

        for placement_index, inst in enumerate(icon_spec["instances"], start=1):
            part_id = inst["part"]
            if scope == "all-icons":
                global_copy_counts[part_id] += 1
                copy_index = global_copy_counts[part_id]
            else:
                local_copy_counts[part_id] += 1
                copy_index = local_copy_counts[part_id]

            if copy_index > quantities.get(part_id, 0):
                raise SystemExit(
                    f"{current_icon_id} needs {part_id} copy {copy_index}, "
                    f"but the fixture kit only contains {quantities.get(part_id, 0)}"
                )

            rotate = inst.get("rotate")
            anchor = "centroid" if rotate is not None else "min_corner"
            base_geometry = ip.part_to_geometry(spec["parts"][part_id], anchor=anchor)
            at_x, at_y = inst["at"]
            placed_geometry = ip.place_part(
                base_geometry,
                float(at_x),
                float(at_y),
                rotate=float(rotate or 0.0),
            )
            label_point = placed_geometry.representative_point()
            front_piece_id, backplate_piece_id = fixture_piece_ids(part_id, copy_index)
            part_number = part_numbers[part_id]
            part_mark = part_number_mark(part_numbers, part_id)
            placements.append({
                "legend_label": part_mark,
                "part_number": part_number,
                "placement_index": placement_index,
                "part": part_id,
                "copy_index": copy_index,
                "front_piece_id": front_piece_id,
                "front_piece_mark": part_mark,
                "backplate_piece_id": backplate_piece_id,
                "backplate_piece_mark": part_mark,
                "anchor": anchor,
                "at_svg": round_float_list([at_x, at_y]),
                "rotate_deg": round(float(rotate or 0.0), 6),
                "source_index": inst.get("source_index", placement_index - 1),
                "bounds_svg": round_float_list(placed_geometry.bounds),
                "label_point_svg": round_float_list([label_point.x, label_point.y]),
            })

        assembly_icons[current_icon_id] = {
            "total_placements": len(placements),
            "placements": placements,
        }

    return {
        "scheme": "visit.fixture-assembly-map.v1",
        "quantity_scope": format_scope(scope),
        "icon_order": icon_ids_for_scope(spec, scope, icon_id),
        "part_numbers": {
            str(number): part_id
            for part_id, number in sorted(part_numbers.items(), key=lambda item: item[1])
        },
        "legend_label_format": "global part number",
        "physical_piece_mark_format": "global part number",
        "icons": assembly_icons,
    }


def attach_layout_to_assembly(assembly: dict, layout_records: list[dict]) -> None:
    records_by_id = {record["piece_id"]: record for record in layout_records}
    for icon in assembly["icons"].values():
        for placement in icon["placements"]:
            for role, piece_id_key in (
                ("front_cap", "front_piece_id"),
                ("backplate", "backplate_piece_id"),
            ):
                layout = records_by_id.get(placement[piece_id_key])
                if not layout:
                    continue
                placement[f"{role}_layout"] = {
                    "plate": layout["plate"],
                    "x_mm": layout["x_mm"],
                    "y_mm": layout["y_mm"],
                    "width_mm": layout["width_mm"],
                    "height_mm": layout["height_mm"],
                }


def build_kit_pieces(
    spec: dict,
    quantities: Counter,
    scale: float,
    part_numbers: dict[str, int] | None = None,
) -> tuple[list[dict], dict[str, dict]]:
    if part_numbers is None:
        part_numbers = part_number_map(quantities)
    pieces = []
    part_details = {}
    for part_id in sorted(quantities):
        part_def = spec["parts"][part_id]
        geometry = svg_to_mm_geometry(ip.part_to_geometry(part_def), scale)
        width, height = geometry_size(geometry)
        min_x, min_y, max_x, max_y = geometry.bounds
        part_number = part_numbers[part_id]
        part_mark = part_number_mark(part_numbers, part_id)
        part_details[part_id] = {
            "part_number": part_number,
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
        }
        for copy_index in range(1, int(quantities[part_id]) + 1):
            pieces.append({
                "piece_id": f"{part_id}__{copy_index:02d}",
                "part_number": part_number,
                "piece_mark": part_mark,
                "step_body_label": step_part_label(part_numbers, part_id),
                "part": part_id,
                "copy_index": copy_index,
                "geometry": geometry,
                "width": width,
                "height": height,
                "bounds": geometry.bounds,
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
        record = {
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
        }
        if "role" in piece:
            record["role"] = piece["role"]
        for key in ("part_number", "piece_mark", "step_body_label"):
            if key in piece:
                record[key] = piece[key]
        if "mount_holes" in piece:
            record["mount_holes_mm"] = [
                {
                    **hole,
                    "x_mm": round(hole["x_mm"] + cursor_x - min_x, 6),
                    "y_mm": round(hole["y_mm"] + cursor_y - min_y, 6),
                }
                for hole in piece["mount_holes"]
            ]
        placements.append(record)

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
    validate_physical_mark_args(args, {"front part": args.front_depth_mm})

    counts_by_icon = icon_part_counts(spec)
    quantities = kit_quantities(counts_by_icon, args.scope, args.icon)
    part_numbers = part_number_map(spec["parts"])
    scale = args.icon_size_mm / args.source_size_svg

    pieces, part_details = build_kit_pieces(spec, quantities, scale, part_numbers)
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
        "marking": {
            "scheme": "global-part-number-v1",
            "physical_piece_mark_format": "global part number",
            "legend_label_format": "global part number",
            "physical_marks": physical_marking_manifest(
                args,
                front_piece_location="engraved on top face",
            ),
        },
        "icons": usage_by_icon,
        "parts": part_details,
    }

    pieces_by_id = {piece["piece_id"]: piece for piece in pieces}
    for placement in placements:
        placement["geometry"] = pieces_by_id[placement["piece_id"]]["geometry"]
    return manifest, placements, spec


def build_part_fixture_pieces(
    spec: dict,
    quantities: Counter,
    scale: float,
    args: argparse.Namespace,
    part_numbers: dict[str, int] | None = None,
) -> tuple[list[dict], dict[str, dict]]:
    if part_numbers is None:
        part_numbers = part_number_map(quantities)
    pieces = []
    part_details = {}
    backplate_inset_mm = args.front_wall_thickness_mm + args.fit_clearance_mm
    for part_id in sorted(quantities):
        part_def = spec["parts"][part_id]
        outer_geometry = svg_to_mm_geometry(ip.part_to_geometry(part_def), scale)
        cavity_geometry = inset_geometry(
            outer_geometry,
            args.front_wall_thickness_mm,
            f"{part_id} front cavity",
        )
        backplate_geometry = inset_geometry(
            outer_geometry,
            backplate_inset_mm,
            f"{part_id} backplate",
        )
        holes, reason = mounting_hole_positions(
            backplate_geometry,
            hole_radius_mm=args.pin_hole_diameter_mm / 2,
            edge_clearance_mm=args.pin_hole_edge_clearance_mm,
            min_spacing_mm=args.pin_hole_min_spacing_mm,
        )
        if not holes:
            raise SystemExit(f"{part_id} cannot fit two mounting holes: {reason}")

        outer_width, outer_height = geometry_size(outer_geometry)
        cavity_width, cavity_height = geometry_size(cavity_geometry)
        backplate_width, backplate_height = geometry_size(backplate_geometry)
        part_number = part_numbers[part_id]
        part_mark = part_number_mark(part_numbers, part_id)
        part_details[part_id] = {
            "part_number": part_number,
            "kind": part_def["kind"],
            "quantity": int(quantities[part_id]),
            "source_count": part_source_count(part_def),
            "source_bounds_svg": part_def.get("bounds"),
            "front_cap": {
                "outer_footprint_mm": {
                    "width": round(outer_width, 6),
                    "height": round(outer_height, 6),
                },
                "cavity_footprint_mm": {
                    "width": round(cavity_width, 6),
                    "height": round(cavity_height, 6),
                },
            },
            "backplate": {
                "footprint_mm": {
                    "width": round(backplate_width, 6),
                    "height": round(backplate_height, 6),
                },
                "mount_holes": holes,
            },
            "min_feature_mm": round(float(part_def.get("print", {}).get("min_feature", 0.0)) * scale, 6),
        }

        for copy_index in range(1, int(quantities[part_id]) + 1):
            front_piece_id, backplate_piece_id = fixture_piece_ids(part_id, copy_index)
            pieces.append({
                "piece_id": front_piece_id,
                "role": "front_cap",
                "part": part_id,
                "copy_index": copy_index,
                "part_number": part_number,
                "piece_mark": part_mark,
                "step_body_label": step_part_label(part_numbers, part_id),
                "geometry": outer_geometry,
                "cavity_geometry": cavity_geometry,
                "width": outer_width,
                "height": outer_height,
                "bounds": outer_geometry.bounds,
            })
            pieces.append({
                "piece_id": backplate_piece_id,
                "role": "part_backplate",
                "part": part_id,
                "copy_index": copy_index,
                "part_number": part_number,
                "piece_mark": part_mark,
                "step_body_label": step_part_label(part_numbers, part_id),
                "geometry": backplate_geometry,
                "mount_holes": holes,
                "width": backplate_width,
                "height": backplate_height,
                "bounds": backplate_geometry.bounds,
            })
    return pieces, part_details


def build_part_fixture_kit_plan(args: argparse.Namespace) -> tuple[dict, list[dict], dict]:
    spec_path = Path(args.spec)
    spec = load_part_spec(spec_path)
    if args.icon_size_mm <= 0:
        raise SystemExit("Icon size must be positive")
    if args.source_size_svg <= 0:
        raise SystemExit("Source SVG size must be positive")
    if args.front_depth_mm <= 0:
        raise SystemExit("Front depth must be positive")
    if args.front_wall_thickness_mm <= 0:
        raise SystemExit("Front wall thickness must be positive")
    if args.front_face_thickness_mm <= 0:
        raise SystemExit("Front face thickness must be positive")
    if args.front_face_thickness_mm >= args.front_depth_mm:
        raise SystemExit("Front face thickness must be less than front depth")
    if args.fit_clearance_mm < 0:
        raise SystemExit("Fit clearance must be zero or positive")
    if args.backplate_thickness_mm <= 0:
        raise SystemExit("Backplate thickness must be positive")
    cavity_depth = args.front_depth_mm - args.front_face_thickness_mm
    if args.backplate_thickness_mm + args.z_clearance_mm > cavity_depth:
        raise SystemExit(
            "Backplate thickness plus z clearance must fit inside the hollow front cap cavity"
        )
    if args.pin_hole_diameter_mm <= 0:
        raise SystemExit("Pin hole diameter must be positive")
    if args.pin_hole_edge_clearance_mm < 0:
        raise SystemExit("Pin hole edge clearance must be zero or positive")
    if args.pin_hole_min_spacing_mm < args.pin_hole_diameter_mm:
        raise SystemExit("Pin hole minimum spacing should be at least the hole diameter")
    validate_physical_mark_args(
        args,
        {
            "front face": args.front_face_thickness_mm,
            "backplate": args.backplate_thickness_mm,
        },
    )

    counts_by_icon = icon_part_counts(spec)
    quantities = kit_quantities(counts_by_icon, args.scope, args.icon)
    part_numbers = part_number_map(spec["parts"])
    scale = args.icon_size_mm / args.source_size_svg
    pieces, part_details = build_part_fixture_pieces(spec, quantities, scale, args, part_numbers)
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
            if key not in {"geometry_xoff", "geometry_yoff", "geometry", "cavity_geometry", "mount_holes"}
        }
        for placement in placements
    ]
    assembly = icon_assembly_map(spec, quantities, args.scope, args.icon, part_numbers)
    attach_layout_to_assembly(assembly, layout_records)
    manifest = {
        "schema": PART_FIXTURE_KIT_SCHEMA,
        "generator": "tools/export_step.py part-fixture-kit-manifest",
        "source_spec": spec_path.as_posix(),
        "source_spec_hash": file_sha256(spec_path),
        "scope": format_scope(args.scope),
        "icon": args.icon if args.scope == "icon" else None,
        "icon_size_mm": args.icon_size_mm,
        "source_size_svg": args.source_size_svg,
        "scale_svg_to_mm": scale,
        "total_unique_part_designs": len(quantities),
        "total_front_caps": int(sum(quantities.values())),
        "total_part_backplates": int(sum(quantities.values())),
        "total_printed_pieces": len(pieces),
        "front_cap": {
            "depth_mm": args.front_depth_mm,
            "wall_thickness_mm": args.front_wall_thickness_mm,
            "face_thickness_mm": args.front_face_thickness_mm,
            "cavity_depth_mm": round(cavity_depth, 6),
            "fit_clearance_mm": args.fit_clearance_mm,
        },
        "backplate": {
            "thickness_mm": args.backplate_thickness_mm,
            "z_clearance_mm": args.z_clearance_mm,
            "pin_hole_diameter_mm": args.pin_hole_diameter_mm,
            "pin_hole_edge_clearance_mm": args.pin_hole_edge_clearance_mm,
            "pin_hole_min_spacing_mm": args.pin_hole_min_spacing_mm,
        },
        "layout": {
            "strategy": "shelf_height_desc",
            "bed_width_mm": args.bed_width_mm,
            "bed_depth_mm": args.bed_depth_mm,
            "spacing_mm": args.spacing_mm,
            "plate_count": plate_count,
            "pieces": layout_records,
        },
        "marking": {
            "scheme": "global-part-number-v1",
            "physical_piece_mark_format": "global part number",
            "legend_label_format": "global part number",
            "physical_marks": physical_marking_manifest(
                args,
                front_cap_location="engraved on inside face",
                backplate_location="engraved on cap-facing face",
            ),
            "notes": [
                "Use the same global part number for matching hollow front caps, backplates, and legend callouts.",
                "Repeated numbers indicate duplicate copies of the same part design; any matching copy can be used.",
            ],
        },
        "assembly": assembly,
        "icons": usage_by_icon,
        "parts": part_details,
    }

    pieces_by_id = {piece["piece_id"]: piece for piece in pieces}
    for placement in placements:
        source_piece = pieces_by_id[placement["piece_id"]]
        placement["geometry"] = source_piece["geometry"]
        if "cavity_geometry" in source_piece:
            placement["cavity_geometry"] = source_piece["cavity_geometry"]
        if "mount_holes" in source_piece:
            placement["mount_holes"] = source_piece["mount_holes"]
    return manifest, placements, spec


def coupon_code(clearance_mm: float) -> str:
    return f"{int(round(clearance_mm * 100)):02d}"


def build_fit_coupon_pieces(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    from shapely.geometry import box as shapely_box

    pieces: list[dict] = []
    variants: list[dict] = []
    for index, clearance in enumerate(args.clearances, start=1):
        inset_mm = args.front_wall_thickness_mm + clearance
        outer_geometry = shapely_box(0.0, 0.0, args.coupon_width_mm, args.coupon_height_mm)
        cavity_geometry = inset_geometry(
            outer_geometry, args.front_wall_thickness_mm, f"coupon {clearance:g} cavity"
        )
        backplate_geometry = inset_geometry(
            outer_geometry, inset_mm, f"coupon {clearance:g} backplate"
        )
        holes, reason = mounting_hole_positions(
            backplate_geometry,
            hole_radius_mm=args.pin_hole_diameter_mm / 2,
            edge_clearance_mm=args.pin_hole_edge_clearance_mm,
            min_spacing_mm=args.pin_hole_min_spacing_mm,
        )
        if not holes:
            raise SystemExit(f"Coupon clearance {clearance:g} cannot fit two mounting holes: {reason}")

        code = coupon_code(clearance)
        outer_width, outer_height = geometry_size(outer_geometry)
        backplate_width, backplate_height = geometry_size(backplate_geometry)
        cap_piece_id = f"coupon_{code}__front_cap"
        backplate_piece_id = f"coupon_{code}__backplate"
        variants.append({
            "index": index,
            "clearance_mm": clearance,
            "code": code,
            "front_cap_piece": cap_piece_id,
            "backplate_piece": backplate_piece_id,
        })
        pieces.append({
            "piece_id": cap_piece_id,
            "role": "front_cap",
            "part": f"coupon_{code}",
            "copy_index": index,
            "part_number": index,
            "piece_mark": code,
            "step_body_label": f"coupon_{code}_front_cap",
            "geometry": outer_geometry,
            "cavity_geometry": cavity_geometry,
            "width": outer_width,
            "height": outer_height,
            "bounds": outer_geometry.bounds,
        })
        pieces.append({
            "piece_id": backplate_piece_id,
            "role": "part_backplate",
            "part": f"coupon_{code}",
            "copy_index": index,
            "part_number": index,
            "piece_mark": code,
            "step_body_label": f"coupon_{code}_backplate",
            "geometry": backplate_geometry,
            "mount_holes": holes,
            "width": backplate_width,
            "height": backplate_height,
            "bounds": backplate_geometry.bounds,
        })
    return pieces, variants


def build_fit_coupon_plan(args: argparse.Namespace) -> tuple[dict, list[dict]]:
    if args.coupon_width_mm <= 0 or args.coupon_height_mm <= 0:
        raise SystemExit("Coupon width and height must be positive")
    if not args.clearances:
        raise SystemExit("At least one clearance value is required")
    for clearance in args.clearances:
        if clearance < 0:
            raise SystemExit("Clearance values must be zero or positive")
    if args.front_depth_mm <= 0:
        raise SystemExit("Front depth must be positive")
    if args.front_wall_thickness_mm <= 0:
        raise SystemExit("Front wall thickness must be positive")
    if args.front_face_thickness_mm <= 0:
        raise SystemExit("Front face thickness must be positive")
    if args.front_face_thickness_mm >= args.front_depth_mm:
        raise SystemExit("Front face thickness must be less than front depth")
    if args.backplate_thickness_mm <= 0:
        raise SystemExit("Backplate thickness must be positive")
    cavity_depth = args.front_depth_mm - args.front_face_thickness_mm
    if args.backplate_thickness_mm + args.z_clearance_mm > cavity_depth:
        raise SystemExit(
            "Backplate thickness plus z clearance must fit inside the hollow cap cavity"
        )
    if args.pin_hole_diameter_mm <= 0:
        raise SystemExit("Pin hole diameter must be positive")
    if args.pin_hole_min_spacing_mm < args.pin_hole_diameter_mm:
        raise SystemExit("Pin hole minimum spacing should be at least the hole diameter")
    validate_physical_mark_args(
        args,
        {
            "front face": args.front_face_thickness_mm,
            "backplate": args.backplate_thickness_mm,
        },
    )

    pieces, variants = build_fit_coupon_pieces(args)
    placements = layout_pieces(
        pieces,
        bed_width_mm=args.bed_width_mm,
        bed_depth_mm=args.bed_depth_mm,
        spacing_mm=args.spacing_mm,
    )
    plate_count = max((placement["plate"] for placement in placements), default=0)
    layout_records = [
        {
            key: value
            for key, value in placement.items()
            if key not in {"geometry_xoff", "geometry_yoff", "geometry", "cavity_geometry", "mount_holes"}
        }
        for placement in placements
    ]
    manifest = {
        "schema": FIT_COUPON_KIT_SCHEMA,
        "generator": "tools/export_step.py fit-coupon-kit",
        "coupon_footprint_mm": {
            "width": args.coupon_width_mm,
            "height": args.coupon_height_mm,
        },
        "front_cap": {
            "depth_mm": args.front_depth_mm,
            "wall_thickness_mm": args.front_wall_thickness_mm,
            "face_thickness_mm": args.front_face_thickness_mm,
            "cavity_depth_mm": round(cavity_depth, 6),
        },
        "backplate": {
            "thickness_mm": args.backplate_thickness_mm,
            "z_clearance_mm": args.z_clearance_mm,
            "pin_hole_diameter_mm": args.pin_hole_diameter_mm,
            "pin_hole_edge_clearance_mm": args.pin_hole_edge_clearance_mm,
            "pin_hole_min_spacing_mm": args.pin_hole_min_spacing_mm,
        },
        "clearances_mm": list(args.clearances),
        "variants": variants,
        "layout": {
            "strategy": "shelf_height_desc",
            "bed_width_mm": args.bed_width_mm,
            "bed_depth_mm": args.bed_depth_mm,
            "spacing_mm": args.spacing_mm,
            "plate_count": plate_count,
            "pieces": layout_records,
        },
        "marking": {
            "scheme": "clearance-code-v1",
            "physical_piece_mark_format": "two-digit clearance code in hundredths of a mm",
            "codes": {variant["code"]: variant["clearance_mm"] for variant in variants},
            "physical_marks": physical_marking_manifest(
                args,
                front_cap_location="engraved on inside face",
                backplate_location="engraved on cap-facing face",
            ),
            "notes": [
                "The two-digit code is the XY fit clearance in hundredths of a millimeter (25 means 0.25 mm).",
                "Cap and backplate with the same code form one fit pair.",
            ],
        },
        "instructions": [
            "Print this coupon plate with the same printer, material, nozzle, and profile planned for the icon kit.",
            "Snap each cap over the backplate with the matching code and compare how secure and removable the fit feels.",
            "Record the code that fits best, then regenerate the kit with --fit-clearance-mm set to that value.",
        ],
    }
    pieces_by_id = {piece["piece_id"]: piece for piece in pieces}
    for placement in placements:
        source_piece = pieces_by_id[placement["piece_id"]]
        placement["geometry"] = source_piece["geometry"]
        if "cavity_geometry" in source_piece:
            placement["cavity_geometry"] = source_piece["cavity_geometry"]
        if "mount_holes" in source_piece:
            placement["mount_holes"] = source_piece["mount_holes"]
    return manifest, placements


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
    mark_text: str | None = None,
    mark_depth_mm: float = 0.0,
    mark_font_size_mm: float = DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM,
    mark_font: str = DEFAULT_PHYSICAL_MARK_FONT,
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
        engrave_part_number(
            b,
            geometry,
            mark_text,
            z_start_mm=front_depth_mm - mark_depth_mm,
            depth_mm=mark_depth_mm,
            max_font_size_mm=mark_font_size_mm,
            font=mark_font,
        )
    return part_builder.part


def sketch_geometry(b, geometry) -> None:
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


def engrave_part_number(
    b,
    geometry,
    mark_text: str | None,
    z_start_mm: float,
    depth_mm: float,
    max_font_size_mm: float,
    font: str,
) -> None:
    if not mark_text or depth_mm <= 0:
        return
    x_mm, y_mm = mark_point(geometry)
    font_size_mm = mark_font_size_mm(mark_text, geometry, max_font_size_mm)
    with b.BuildPart(mode=b.Mode.PRIVATE) as text_cutter:
        with b.BuildSketch(b.Plane.XY.offset(z_start_mm)):
            with b.Locations((x_mm, y_mm)):
                b.Text(
                    mark_text,
                    font_size_mm,
                    font=font,
                    font_style=b.FontStyle.BOLD,
                    single_line_width=max(font_size_mm * 0.04, 0.08),
                )
        b.extrude(amount=depth_mm)
    b.add(text_cutter.part, mode=b.Mode.SUBTRACT)


def cad_geometry_to_hollow_front_cap(
    b,
    outer_geometry,
    cavity_geometry,
    front_depth_mm: float,
    front_face_thickness_mm: float,
    mark_text: str | None = None,
    mark_depth_mm: float = 0.0,
    mark_font_size_mm: float = DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM,
    mark_font: str = DEFAULT_PHYSICAL_MARK_FONT,
):
    cavity_depth = front_depth_mm - front_face_thickness_mm
    with b.BuildPart() as part_builder:
        with b.BuildSketch(b.Plane.XY):
            sketch_geometry(b, outer_geometry)
        b.extrude(amount=front_depth_mm)
        with b.BuildSketch(b.Plane.XY.offset(front_face_thickness_mm)):
            sketch_geometry(b, cavity_geometry)
        b.extrude(amount=cavity_depth + 0.1, mode=b.Mode.SUBTRACT)
        engrave_part_number(
            b,
            cavity_geometry,
            mark_text,
            z_start_mm=front_face_thickness_mm - mark_depth_mm,
            depth_mm=mark_depth_mm,
            max_font_size_mm=mark_font_size_mm,
            font=mark_font,
        )
    return part_builder.part


def cad_geometry_to_part_backplate(
    b,
    geometry,
    backplate_thickness_mm: float,
    mount_holes: list[dict],
    mark_text: str | None = None,
    mark_depth_mm: float = 0.0,
    mark_font_size_mm: float = DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM,
    mark_font: str = DEFAULT_PHYSICAL_MARK_FONT,
):
    with b.BuildPart() as backplate_builder:
        with b.BuildSketch(b.Plane.XY):
            sketch_geometry(b, geometry)
        b.extrude(amount=backplate_thickness_mm)
        pin_cut_height = backplate_thickness_mm + 0.2
        for hole in mount_holes:
            with b.Locations((hole["x_mm"], hole["y_mm"], -0.1)):
                b.Cylinder(
                    hole["diameter_mm"] / 2,
                    pin_cut_height,
                    align=(b.Align.CENTER, b.Align.CENTER, b.Align.MIN),
                    mode=b.Mode.SUBTRACT,
                )
        engrave_part_number(
            b,
            geometry,
            mark_text,
            z_start_mm=backplate_thickness_mm - mark_depth_mm,
            depth_mm=mark_depth_mm,
            max_font_size_mm=mark_font_size_mm,
            font=mark_font,
        )
    return backplate_builder.part


def kit_compound(
    b,
    placements: list[dict],
    args: argparse.Namespace,
    plate: int | None = None,
):
    children = []
    for placement in placements:
        if plate is not None and placement["plate"] != plate:
            continue
        plate_offset_y = 0.0
        if plate is None:
            plate_offset_y = (placement["plate"] - 1) * (args.bed_depth_mm + args.plate_gap_mm)
        geometry = affinity.translate(
            placement["geometry"],
            xoff=placement["geometry_xoff"],
            yoff=placement["geometry_yoff"] + plate_offset_y,
        )
        mark_text = None if args.no_physical_marks else placement.get("piece_mark")
        part = cad_geometry_to_part(
            b,
            geometry,
            args.front_depth_mm,
            mark_text=mark_text,
            mark_depth_mm=args.physical_mark_depth_mm if mark_text else 0.0,
            mark_font_size_mm=args.physical_mark_font_size_mm,
            mark_font=args.physical_mark_font,
        )
        part.label = (
            placement.get("step_body_label")
            or placement.get("piece_mark")
            or placement["piece_id"]
        )
        children.append(part)
    if not children:
        raise SystemExit("No kit pieces to export")
    return b.Compound(children=children, label="visit_icon_kit")


def part_fixture_kit_compound(
    b,
    placements: list[dict],
    args: argparse.Namespace,
    plate: int | None = None,
):
    children = []
    for placement in placements:
        if plate is not None and placement["plate"] != plate:
            continue
        plate_offset_y = 0.0
        if plate is None:
            plate_offset_y = (placement["plate"] - 1) * (args.bed_depth_mm + args.plate_gap_mm)
        geometry = affinity.translate(
            placement["geometry"],
            xoff=placement["geometry_xoff"],
            yoff=placement["geometry_yoff"] + plate_offset_y,
        )
        if placement["role"] == "front_cap":
            cavity_geometry = affinity.translate(
                placement["cavity_geometry"],
                xoff=placement["geometry_xoff"],
                yoff=placement["geometry_yoff"] + plate_offset_y,
            )
            mark_text = None if args.no_physical_marks else placement.get("piece_mark")
            part = cad_geometry_to_hollow_front_cap(
                b,
                geometry,
                cavity_geometry,
                front_depth_mm=args.front_depth_mm,
                front_face_thickness_mm=args.front_face_thickness_mm,
                mark_text=mark_text,
                mark_depth_mm=args.physical_mark_depth_mm if mark_text else 0.0,
                mark_font_size_mm=args.physical_mark_font_size_mm,
                mark_font=args.physical_mark_font,
            )
        elif placement["role"] == "part_backplate":
            mount_holes = [
                {**hole, "y_mm": hole["y_mm"] + plate_offset_y}
                for hole in placement.get("mount_holes_mm", [])
            ]
            mark_text = None if args.no_physical_marks else placement.get("piece_mark")
            part = cad_geometry_to_part_backplate(
                b,
                geometry,
                backplate_thickness_mm=args.backplate_thickness_mm,
                mount_holes=mount_holes,
                mark_text=mark_text,
                mark_depth_mm=args.physical_mark_depth_mm if mark_text else 0.0,
                mark_font_size_mm=args.physical_mark_font_size_mm,
                mark_font=args.physical_mark_font,
            )
        else:
            raise SystemExit(f"Unknown fixture role: {placement['role']}")
        part.label = (
            placement.get("step_body_label")
            or placement.get("piece_mark")
            or placement["piece_id"]
        )
        children.append(part)
    if not children:
        raise SystemExit("No fixture kit pieces to export")
    return b.Compound(children=children, label="visit_icon_part_fixture_kit")


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
        args,
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
                args,
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


def part_fixture_kit_manifest_command(args: argparse.Namespace) -> int:
    manifest, _placements, _spec = build_part_fixture_kit_plan(args)
    out_path = Path(args.out)
    write_manifest(out_path, manifest)
    print(
        f"part fixture manifest: {manifest['total_unique_part_designs']} designs, "
        f"{manifest['total_front_caps']} hollow front caps, "
        f"{manifest['total_part_backplates']} backplates, "
        f"{manifest['layout']['plate_count']} plates -> {out_path.as_posix()}"
    )
    return 0


def export_part_fixture_kit_command(args: argparse.Namespace) -> int:
    b = require_build123d()
    manifest, placements, _spec = build_part_fixture_kit_plan(args)
    output_path = Path(args.out)

    compound = part_fixture_kit_compound(b, placements, args)
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
            plate_shape = part_fixture_kit_compound(b, placements, args, plate=plate)
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

    manifest["generator"] = "tools/export_step.py part-fixture-kit"
    manifest["outputs"] = outputs
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    write_manifest(manifest_path, manifest)
    print(
        f"part fixture STEP: {manifest['total_unique_part_designs']} designs, "
        f"{manifest['total_front_caps']} hollow front caps, "
        f"{manifest['total_part_backplates']} backplates, "
        f"{manifest['layout']['plate_count']} plates -> {output_path.as_posix()}"
    )
    print(f"part fixture manifest: {manifest_path.as_posix()}")
    return 0


def export_fit_coupon_kit_command(args: argparse.Namespace) -> int:
    b = require_build123d()
    manifest, placements = build_fit_coupon_plan(args)
    output_path = Path(args.out)

    compound = part_fixture_kit_compound(b, placements, args)
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
            plate_shape = part_fixture_kit_compound(b, placements, args, plate=plate)
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

    manifest["outputs"] = outputs
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    write_manifest(manifest_path, manifest)
    print(
        f"fit coupon STEP: {len(manifest['variants'])} clearance variants, "
        f"{manifest['layout']['plate_count']} plates -> {output_path.as_posix()}"
    )
    print(f"fit coupon manifest: {manifest_path.as_posix()}")
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
    parser.add_argument("--no-physical-marks", action="store_true", help="Do not engrave part numbers into STEP geometry")
    parser.add_argument("--physical-mark-font", default=DEFAULT_PHYSICAL_MARK_FONT)
    parser.add_argument("--physical-mark-font-size-mm", type=float, default=DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM)
    parser.add_argument("--physical-mark-depth-mm", type=float, default=DEFAULT_PHYSICAL_MARK_DEPTH_MM)


def add_part_fixture_kit_arguments(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument("--front-wall-thickness-mm", type=float, default=1.0)
    parser.add_argument("--front-face-thickness-mm", type=float, default=1.2)
    parser.add_argument("--fit-clearance-mm", type=float, default=0.25)
    parser.add_argument("--backplate-thickness-mm", type=float, default=3.0)
    parser.add_argument("--z-clearance-mm", type=float, default=0.3)
    parser.add_argument("--pin-hole-diameter-mm", type=float, default=1.6)
    parser.add_argument("--pin-hole-edge-clearance-mm", type=float, default=1.0)
    parser.add_argument("--pin-hole-min-spacing-mm", type=float, default=4.0)
    parser.add_argument("--bed-width-mm", type=float, default=180.0)
    parser.add_argument("--bed-depth-mm", type=float, default=180.0)
    parser.add_argument("--spacing-mm", type=float, default=4.0)
    parser.add_argument("--no-physical-marks", action="store_true", help="Do not engrave part numbers into STEP geometry")
    parser.add_argument("--physical-mark-font", default=DEFAULT_PHYSICAL_MARK_FONT)
    parser.add_argument("--physical-mark-font-size-mm", type=float, default=DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM)
    parser.add_argument("--physical-mark-depth-mm", type=float, default=DEFAULT_PHYSICAL_MARK_DEPTH_MM)


def add_fit_coupon_kit_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--coupon-width-mm", type=float, default=22.0, help="Coupon footprint width")
    parser.add_argument("--coupon-height-mm", type=float, default=12.0, help="Coupon footprint height")
    parser.add_argument(
        "--clearances",
        nargs="*",
        type=float,
        default=list(DEFAULT_FIT_COUPON_CLEARANCES),
        help="Fit clearance values in mm; one cap/backplate pair is generated per value",
    )
    parser.add_argument("--front-depth-mm", type=float, default=8.0)
    parser.add_argument("--front-wall-thickness-mm", type=float, default=1.0)
    parser.add_argument("--front-face-thickness-mm", type=float, default=1.2)
    parser.add_argument("--backplate-thickness-mm", type=float, default=3.0)
    parser.add_argument("--z-clearance-mm", type=float, default=0.3)
    parser.add_argument("--pin-hole-diameter-mm", type=float, default=1.6)
    parser.add_argument("--pin-hole-edge-clearance-mm", type=float, default=1.0)
    parser.add_argument("--pin-hole-min-spacing-mm", type=float, default=4.0)
    parser.add_argument("--bed-width-mm", type=float, default=180.0)
    parser.add_argument("--bed-depth-mm", type=float, default=180.0)
    parser.add_argument("--spacing-mm", type=float, default=4.0)
    parser.add_argument("--plate-gap-mm", type=float, default=20.0)
    parser.add_argument("--no-physical-marks", action="store_true", help="Do not engrave clearance codes into STEP geometry")
    parser.add_argument("--physical-mark-font", default=DEFAULT_PHYSICAL_MARK_FONT)
    parser.add_argument("--physical-mark-font-size-mm", type=float, default=DEFAULT_PHYSICAL_MARK_FONT_SIZE_MM)
    parser.add_argument("--physical-mark-depth-mm", type=float, default=DEFAULT_PHYSICAL_MARK_DEPTH_MM)


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

    fixture_manifest = subparsers.add_parser(
        "part-fixture-kit-manifest",
        help="Write a hollow-front plus per-part-backplate fixture kit manifest",
    )
    add_part_fixture_kit_arguments(fixture_manifest)
    fixture_manifest.add_argument("--out", required=True, help="Output fixture kit manifest JSON")
    fixture_manifest.set_defaults(func=part_fixture_kit_manifest_command)

    fixture_kit = subparsers.add_parser(
        "part-fixture-kit",
        help="Export hollow front caps and one small two-hole backplate per icon part",
    )
    add_part_fixture_kit_arguments(fixture_kit)
    fixture_kit.add_argument("--out", required=True, help="Output combined STEP file")
    fixture_kit.add_argument("--manifest", help="Optional output manifest JSON path")
    fixture_kit.add_argument("--split-plates", action="store_true", help="Also write one STEP file per plate")
    fixture_kit.add_argument("--plate-gap-mm", type=float, default=20.0)
    fixture_kit.add_argument("--verify-import", action="store_true", help="Re-import exported STEP files and compare volume")
    fixture_kit.add_argument("--volume-tolerance", type=float, default=1e-6)
    fixture_kit.set_defaults(func=export_part_fixture_kit_command)

    coupon_kit = subparsers.add_parser(
        "fit-coupon-kit",
        help="Export cap/backplate fit calibration coupons at multiple XY clearances",
    )
    add_fit_coupon_kit_arguments(coupon_kit)
    coupon_kit.add_argument("--out", required=True, help="Output combined STEP file")
    coupon_kit.add_argument("--manifest", help="Optional output manifest JSON path")
    coupon_kit.add_argument("--split-plates", action="store_true", help="Also write one STEP file per plate")
    coupon_kit.add_argument("--verify-import", action="store_true", help="Re-import exported STEP files and compare volume")
    coupon_kit.add_argument("--volume-tolerance", type=float, default=1e-6)
    coupon_kit.set_defaults(func=export_fit_coupon_kit_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
