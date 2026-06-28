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
from shapely.geometry import MultiPolygon, Polygon


FIXED_STEP_TIMESTAMP = "2026-06-27T00:00:00"
KIT_SCHEMA = "visit.icon-kit.v1"
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
) -> tuple[list[dict], dict[str, dict]]:
    pieces = []
    part_details = {}
    for part_id in sorted(quantities):
        part_def = spec["parts"][part_id]
        geometry = svg_to_mm_geometry(ip.part_to_geometry(part_def), scale)
        width, height = geometry_size(geometry)
        min_x, min_y, max_x, max_y = geometry.bounds
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

    counts_by_icon = icon_part_counts(spec)
    quantities = kit_quantities(counts_by_icon, args.scope, args.icon)
    scale = args.icon_size_mm / args.source_size_svg

    pieces, part_details = build_kit_pieces(spec, quantities, scale)
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


def cad_geometry_to_part(b, geometry, front_depth_mm: float):
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
    return part_builder.part


def kit_compound(
    b,
    placements: list[dict],
    front_depth_mm: float,
    bed_depth_mm: float,
    plate_gap_mm: float,
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
        part = cad_geometry_to_part(b, geometry, front_depth_mm)
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
