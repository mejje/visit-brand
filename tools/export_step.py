"""Export STEP geometry from generated icon reference files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

from shapely import wkb
from shapely.geometry import MultiPolygon, Polygon


FIXED_STEP_TIMESTAMP = "2026-06-27T00:00:00"


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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
