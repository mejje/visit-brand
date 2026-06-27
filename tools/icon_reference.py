"""Build deterministic reference artifacts from source SVG icons."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Iterable, Sequence

from shapely import make_valid, wkb
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import explain_validity
from svgelements import SVG, Path as SvgPath


SCHEMA = "visit.icon-reference.v1"
GENERATOR = "tools/icon_reference.py"
DEFAULT_CURVE_TOLERANCE = 0.02
DEFAULT_COORDINATE_PRECISION = 0.000000001
SUPPORTED_SHAPES = {"Path", "Polygon", "Rect"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_places(step: float) -> int:
    text = f"{step:.12f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1])


def round_float(value: float, precision: float) -> float:
    if precision <= 0:
        return float(value)
    rounded = round(round(float(value) / precision) * precision, decimal_places(precision))
    return 0.0 if rounded == -0.0 else rounded


def format_float(value: float, precision: float) -> str:
    places = decimal_places(precision)
    rounded = round_float(value, precision)
    text = f"{rounded:.{places}f}" if places else f"{rounded:.0f}"
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return text or "0"


def parse_viewbox(path: Path) -> list[float]:
    import xml.etree.ElementTree as ET

    root = ET.parse(path).getroot()
    value = root.attrib.get("viewBox")
    if not value:
        raise ValueError(f"{path} is missing an SVG viewBox")
    parts = [float(part) for part in value.replace(",", " ").split()]
    if len(parts) != 4:
        raise ValueError(f"{path} has unsupported viewBox: {value!r}")
    return parts


def point_tuple(point) -> tuple[float, float]:
    return (float(point.x), float(point.y))


def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def distance_point_to_line(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = math.hypot(dx, dy)
    if denominator == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / denominator


def flatten_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    tolerance: float,
    depth: int = 0,
) -> list[tuple[float, float]]:
    flatness = max(distance_point_to_line(p1, p0, p3), distance_point_to_line(p2, p0, p3))
    if flatness <= tolerance or depth >= 20:
        return [p3]

    p01 = midpoint(p0, p1)
    p12 = midpoint(p1, p2)
    p23 = midpoint(p2, p3)
    p012 = midpoint(p01, p12)
    p123 = midpoint(p12, p23)
    p0123 = midpoint(p012, p123)

    return flatten_cubic(p0, p01, p012, p0123, tolerance, depth + 1) + flatten_cubic(
        p0123, p123, p23, p3, tolerance, depth + 1
    )


def flatten_quadratic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    tolerance: float,
    depth: int = 0,
) -> list[tuple[float, float]]:
    flatness = distance_point_to_line(p1, p0, p2)
    if flatness <= tolerance or depth >= 20:
        return [p2]

    p01 = midpoint(p0, p1)
    p12 = midpoint(p1, p2)
    p012 = midpoint(p01, p12)
    return flatten_quadratic(p0, p01, p012, tolerance, depth + 1) + flatten_quadratic(
        p012, p12, p2, tolerance, depth + 1
    )


def append_point(points: list[tuple[float, float]], point: tuple[float, float]) -> None:
    if not points or math.hypot(points[-1][0] - point[0], points[-1][1] - point[1]) > 1e-9:
        points.append(point)


def fallback_sample_segment(segment, tolerance: float) -> list[tuple[float, float]]:
    try:
        length = float(segment.length())
    except Exception:
        length = 1.0
    max_segment = max(tolerance * 8, 0.1)
    steps = max(1, math.ceil(length / max_segment))
    return [point_tuple(segment.point(index / steps)) for index in range(1, steps + 1)]


def flatten_segment(segment, tolerance: float) -> list[tuple[float, float]]:
    name = type(segment).__name__
    if name == "Move":
        return []
    if name in {"Line", "Close"}:
        return [point_tuple(segment.end)]
    if name == "CubicBezier":
        return flatten_cubic(
            point_tuple(segment.start),
            point_tuple(segment.control1),
            point_tuple(segment.control2),
            point_tuple(segment.end),
            tolerance,
        )
    if name == "QuadraticBezier":
        return flatten_quadratic(
            point_tuple(segment.start),
            point_tuple(segment.control),
            point_tuple(segment.end),
            tolerance,
        )
    return fallback_sample_segment(segment, tolerance)


def path_to_rings(path: SvgPath, tolerance: float) -> list[list[tuple[float, float]]]:
    rings: list[list[tuple[float, float]]] = []
    for subpath in path.as_subpaths():
        points: list[tuple[float, float]] = []
        for segment in subpath:
            if type(segment).__name__ == "Move":
                append_point(points, point_tuple(segment.end))
                continue
            if not points and hasattr(segment, "start"):
                append_point(points, point_tuple(segment.start))
            for point in flatten_segment(segment, tolerance):
                append_point(points, point)
        if len(points) < 3:
            continue
        if math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) > 1e-9:
            points.append(points[0])
        rings.append(points)
    return rings


def extract_polygons(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        polygons: list[Polygon] = []
        for child in geometry.geoms:
            polygons.extend(extract_polygons(child))
        return polygons
    return []


def repair_polygon(polygon: Polygon):
    if polygon.is_valid:
        return polygon
    repaired = make_valid(polygon)
    polygons = extract_polygons(repaired)
    if not polygons:
        return polygon.buffer(0)
    return unary_union(polygons)


def shape_to_geometry(element, tolerance: float):
    path = SvgPath(element).reify()
    rings = path_to_rings(path, tolerance)
    polygons = []
    for ring in rings:
        polygon = Polygon(ring)
        if polygon.is_empty or polygon.area == 0:
            continue
        polygons.extend(extract_polygons(repair_polygon(polygon)))
    if not polygons:
        return None
    return unary_union(polygons)


def canonical_geometry(geometry):
    repaired = repair_polygon(geometry) if isinstance(geometry, Polygon) else make_valid(geometry)
    polygons = extract_polygons(repaired)
    if not polygons:
        return MultiPolygon([])
    unioned = unary_union(polygons)
    polygons = extract_polygons(unioned)
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def geometry_metrics(geometry, precision: float) -> dict:
    polygons = extract_polygons(geometry)
    bounds = geometry.bounds if not geometry.is_empty else (0, 0, 0, 0)
    return {
        "area": round_float(geometry.area, precision),
        "bounds": [round_float(value, precision) for value in bounds],
        "component_count": len(polygons),
        "hole_count": sum(len(poly.interiors) for poly in polygons),
        "is_valid": bool(geometry.is_valid),
        "validity": "Valid Geometry" if geometry.is_valid else explain_validity(geometry),
    }


def iter_filled_shapes(svg: SVG) -> Iterable:
    for element in svg.elements():
        name = type(element).__name__
        if name not in SUPPORTED_SHAPES:
            continue
        fill = str(getattr(element, "fill", "") or "").strip().lower()
        if fill == "none":
            continue
        yield element


def build_reference(
    source_path: Path,
    curve_tolerance: float,
    coordinate_precision: float,
) -> tuple[dict, object]:
    svg = SVG.parse(str(source_path))
    viewbox = parse_viewbox(source_path)
    primitive_hints = []
    geometries = []
    fills: list[str] = []
    unsupported: set[str] = set()

    for element in svg.elements():
        name = type(element).__name__
        if name not in SUPPORTED_SHAPES and name not in {
            "SVG",
            "Defs",
            "Style",
            "Group",
            "Title",
            "Desc",
        }:
            unsupported.add(name)

    for index, element in enumerate(iter_filled_shapes(svg)):
        fill = str(getattr(element, "fill", "") or "#000000")
        if fill not in fills:
            fills.append(fill)
        primitive_hints.append(
            {
                "index": index,
                "kind": type(element).__name__,
                "fill": fill,
                "bounds": [round_float(value, coordinate_precision) for value in element.bbox()],
                "has_transform": not getattr(element, "transform", None).is_identity(),
            }
        )
        geometry = shape_to_geometry(element, curve_tolerance)
        if geometry is not None:
            geometries.append(geometry)

    if not geometries:
        raise ValueError(f"{source_path} did not produce any filled geometry")

    geometry = canonical_geometry(unary_union(geometries))
    icon_id = source_path.stem
    reference = {
        "schema": SCHEMA,
        "icon_id": icon_id,
        "source": {
            "path": str(source_path.as_posix()),
            "sha256": sha256_file(source_path),
            "viewBox": [round_float(value, coordinate_precision) for value in viewbox],
        },
        "normalization": {
            "units": "svg_user_units",
            "coordinate_system": "svg_y_down",
            "fill_rule": "nonzero",
            "curve_flatten_tolerance": curve_tolerance,
            "coordinate_precision": coordinate_precision,
        },
        "style": {
            "fills": fills,
            "canonical_fill": fills[0] if fills else "#000000",
        },
        "geometry": {
            "format": "wkb_hex",
            "value": geometry.wkb_hex,
        },
        "primitive_hints": primitive_hints,
        "metrics": geometry_metrics(geometry, coordinate_precision),
        "unsupported_elements": sorted(unsupported),
    }
    return reference, geometry


def load_reference(path: Path) -> tuple[dict, object]:
    reference = json.loads(path.read_text(encoding="utf-8"))
    geometry_info = reference["geometry"]
    if geometry_info["format"] != "wkb_hex":
        raise ValueError(f"{path} uses unsupported geometry format {geometry_info['format']!r}")
    return reference, wkb.loads(geometry_info["value"], hex=True)


def sorted_polygons(geometry) -> list[Polygon]:
    polygons = extract_polygons(geometry)
    return sorted(
        polygons,
        key=lambda poly: (
            round(poly.bounds[0], 9),
            round(poly.bounds[1], 9),
            round(poly.bounds[2], 9),
            round(poly.bounds[3], 9),
            -round(poly.area, 9),
        ),
    )


def ring_to_path(coords: Sequence[tuple[float, float]], precision: float) -> str:
    open_coords = list(coords[:-1]) if coords and coords[0] == coords[-1] else list(coords)
    if not open_coords:
        return ""
    first = open_coords[0]
    parts = [f"M {format_float(first[0], precision)} {format_float(first[1], precision)}"]
    for x, y in open_coords[1:]:
        parts.append(f"L {format_float(x, precision)} {format_float(y, precision)}")
    parts.append("Z")
    return " ".join(parts)


def geometry_to_path_data(geometry, precision: float) -> str:
    parts: list[str] = []
    for polygon in sorted_polygons(geometry):
        parts.append(ring_to_path(list(polygon.exterior.coords), precision))
        for interior in polygon.interiors:
            parts.append(ring_to_path(list(interior.coords), precision))
    return " ".join(part for part in parts if part)


def canonical_svg(reference: dict, geometry) -> str:
    viewbox = reference["source"]["viewBox"]
    precision = reference["normalization"]["coordinate_precision"]
    fill = reference.get("style", {}).get("canonical_fill") or "#000000"
    path_data = geometry_to_path_data(geometry, precision)
    viewbox_text = " ".join(format_float(value, precision) for value in viewbox)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg id="CanonicalReference" xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox_text}">\n'
        f'  <path fill="{fill}" fill-rule="evenodd" d="{path_data}"/>\n'
        "</svg>\n"
    )


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def output_paths(out_dir: Path, icon_id: str) -> tuple[Path, Path]:
    return (
        out_dir / f"{icon_id}.reference.json",
        out_dir / f"{icon_id}.canonical.svg",
    )


def render_reference(reference_path: Path, out_dir: Path) -> dict:
    reference, geometry = load_reference(reference_path)
    icon_id = reference["icon_id"]
    _, svg_path = output_paths(out_dir, icon_id)
    svg_path.write_text(canonical_svg(reference, geometry), encoding="utf-8")
    return {
        "canonical_svg": svg_path.as_posix(),
    }


def source_files(input_dir: Path, icons: Sequence[str] | None) -> list[Path]:
    all_files = sorted(input_dir.glob("*.svg"), key=lambda path: path.name.lower())
    if not icons:
        return all_files
    requested = set(icons)
    selected = []
    for path in all_files:
        if path.name in requested or path.stem in requested or path.as_posix() in requested:
            selected.append(path)
    missing = sorted(requested - {path.name for path in selected} - {path.stem for path in selected})
    if missing:
        raise SystemExit(f"No SVG found for: {', '.join(missing)}")
    return selected


def build_command(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = source_files(input_dir, args.icons)
    if not files:
        raise SystemExit(f"No SVG files found in {input_dir}")

    manifest = {
        "schema": "visit.icon-reference-manifest.v1",
        "generator": GENERATOR,
        "settings": {
            "curve_flatten_tolerance": args.curve_tolerance,
            "coordinate_precision": args.coordinate_precision,
        },
        "icons": {},
    }

    for source_path in files:
        reference, _geometry = build_reference(source_path, args.curve_tolerance, args.coordinate_precision)
        reference_path, svg_path = output_paths(out_dir, reference["icon_id"])
        write_json(reference_path, reference)
        render_reference(reference_path, out_dir)
        manifest["icons"][reference["icon_id"]] = {
            "source": source_path.as_posix(),
            "sha256": reference["source"]["sha256"],
            "reference_json": reference_path.as_posix(),
            "canonical_svg": svg_path.as_posix(),
            "metrics": reference["metrics"],
            "unsupported_elements": reference["unsupported_elements"],
        }
        print(f"built {reference['icon_id']}")

    write_json(out_dir / "manifest.json", manifest)
    return 0


def render_command(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    references = sorted(input_dir.glob("*.reference.json"), key=lambda path: path.name.lower())
    if not references:
        raise SystemExit(f"No *.reference.json files found in {input_dir}")
    for reference_path in references:
        render_reference(reference_path, out_dir)
        print(f"rendered {reference_path.stem.removesuffix('.reference')}")
    return 0


def check_command(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    references_dir = Path(args.references)
    manifest_path = references_dir / "manifest.json"
    errors: list[str] = []

    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for icon_id, info in sorted(manifest.get("icons", {}).items()):
        source_path = Path(info["source"])
        if not source_path.is_absolute():
            source_path = input_dir.parent / source_path
        reference_path = Path(info["reference_json"])
        canonical_svg_path = Path(info["canonical_svg"])

        for path in (source_path, reference_path, canonical_svg_path):
            if not path.exists():
                errors.append(f"{icon_id}: missing {path}")

        if source_path.exists():
            actual_hash = sha256_file(source_path)
            if actual_hash != info["sha256"]:
                errors.append(f"{icon_id}: source hash changed; rebuild references")

        if reference_path.exists():
            reference, _geometry = load_reference(reference_path)
            if reference["source"]["sha256"] != info["sha256"]:
                errors.append(f"{icon_id}: reference hash does not match manifest")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"checked {len(manifest.get('icons', {}))} references")
    return 0


def verify_command(args: argparse.Namespace) -> int:
    references_dir = Path(args.references)
    manifest_path = references_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    max_source = ("none", -1.0)
    max_canonical = ("none", -1.0)

    for icon_id, info in sorted(manifest.get("icons", {}).items()):
        reference_path = Path(info["reference_json"])
        canonical_svg_path = Path(info["canonical_svg"])
        if not reference_path.exists() or not canonical_svg_path.exists():
            errors.append(f"{icon_id}: missing reference or canonical SVG")
            continue

        reference, reference_geometry = load_reference(reference_path)
        tolerance = reference["normalization"]["curve_flatten_tolerance"]
        precision = reference["normalization"]["coordinate_precision"]
        source_path = Path(reference["source"]["path"])

        _source_reference, source_geometry = build_reference(source_path, tolerance, precision)
        _canonical_reference, canonical_geometry = build_reference(canonical_svg_path, tolerance, precision)

        source_diff = reference_geometry.symmetric_difference(source_geometry).area
        canonical_diff = reference_geometry.symmetric_difference(canonical_geometry).area
        max_source = max(max_source, (icon_id, source_diff), key=lambda item: item[1])
        max_canonical = max(max_canonical, (icon_id, canonical_diff), key=lambda item: item[1])

        if source_diff > args.source_tolerance:
            errors.append(
                f"{icon_id}: source/reference area diff {source_diff:.12g} exceeds {args.source_tolerance:g}"
            )
        if canonical_diff > args.canonical_tolerance:
            errors.append(
                f"{icon_id}: canonical/reference area diff {canonical_diff:.12g} exceeds {args.canonical_tolerance:g}"
            )

        if args.verbose:
            print(
                f"{icon_id}: source_diff={source_diff:.12g}, "
                f"canonical_diff={canonical_diff:.12g}"
            )

    print(
        f"verified {len(manifest.get('icons', {}))} references; "
        f"max_source={max_source[0]}:{max_source[1]:.12g}; "
        f"max_canonical={max_canonical[0]}:{max_canonical[1]:.12g}"
    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build reference JSON, canonical SVG, and manifest")
    build.add_argument("--input", default="SVG", help="Directory containing source SVG files")
    build.add_argument("--out", default="analysis/references", help="Output directory for generated references")
    build.add_argument("--icons", nargs="*", help="Optional list of SVG filenames or stems to build")
    build.add_argument("--curve-tolerance", type=float, default=DEFAULT_CURVE_TOLERANCE)
    build.add_argument("--coordinate-precision", type=float, default=DEFAULT_COORDINATE_PRECISION)
    build.set_defaults(func=build_command)

    render = subparsers.add_parser("render", help="Render canonical SVGs from reference JSON")
    render.add_argument("--input", default="analysis/references", help="Directory containing *.reference.json files")
    render.add_argument("--out", default="analysis/references", help="Output directory for rendered files")
    render.set_defaults(func=render_command)

    check = subparsers.add_parser("check", help="Check generated references for staleness and missing files")
    check.add_argument("--input", default="SVG", help="Directory containing source SVG files")
    check.add_argument("--references", default="analysis/references", help="Generated reference directory")
    check.set_defaults(func=check_command)

    verify = subparsers.add_parser("verify", help="Compare source and canonical SVG geometry against references")
    verify.add_argument("--references", default="analysis/references", help="Generated reference directory")
    verify.add_argument("--source-tolerance", type=float, default=1e-12)
    verify.add_argument("--canonical-tolerance", type=float, default=1e-8)
    verify.add_argument("--verbose", action="store_true")
    verify.set_defaults(func=verify_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
