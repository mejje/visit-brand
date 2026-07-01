"""Generate a part gallery ordered by adjacent Hausdorff similarity."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

from shapely import affinity

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_step as step  # noqa: E402
import icon_parts as ip  # noqa: E402
import icon_reference as iref  # noqa: E402


DEFAULT_MANIFEST = "analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.manifest.json"
DEFAULT_OUT = "analysis/runs/similarity/universal-single-icon-fixture-part-similarity.svg"

KIND_COLORS = {
    "rect": "#2563EB",
    "polygon": "#059669",
    "custom_polygon": "#7C3AED",
    "bar": "#D97706",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_for_distance(geometry):
    geometry = iref.canonical_geometry(geometry)
    if geometry.is_empty:
        return geometry
    centroid = geometry.centroid
    return affinity.translate(geometry, xoff=-centroid.x, yoff=-centroid.y)


def normalized_for_display(geometry):
    geometry = iref.canonical_geometry(geometry)
    if geometry.is_empty:
        return geometry
    min_x, min_y, _max_x, _max_y = geometry.bounds
    return affinity.translate(geometry, xoff=-min_x, yoff=-min_y)


def geometry_size(geometry) -> tuple[float, float]:
    if geometry.is_empty:
        return 0.0, 0.0
    min_x, min_y, max_x, max_y = geometry.bounds
    return max_x - min_x, max_y - min_y


def part_numbers_for(spec: dict, manifest: dict | None) -> dict[str, int]:
    if manifest and manifest.get("parts"):
        return {
            part_id: int(detail["part_number"])
            for part_id, detail in manifest["parts"].items()
            if "part_number" in detail
        }
    return step.part_number_map(spec["parts"])


def selected_part_ids(spec: dict, manifest: dict | None) -> list[str]:
    if manifest and manifest.get("parts"):
        return [part_id for part_id in manifest["parts"] if part_id in spec["parts"]]
    return list(spec["parts"])


def build_items(spec: dict, manifest: dict | None, scale_svg_to_mm: float) -> list[dict[str, Any]]:
    part_numbers = part_numbers_for(spec, manifest)
    manifest_parts = manifest.get("parts", {}) if manifest else {}
    counts_by_icon = step.icon_part_counts(spec)
    quantities = step.kit_quantities(counts_by_icon, "universal")
    items: list[dict[str, Any]] = []

    for part_id in selected_part_ids(spec, manifest):
        part_def = spec["parts"][part_id]
        geometry = ip.part_to_geometry(part_def)
        display_geometry = normalized_for_display(geometry)
        distance_geometry = normalized_for_distance(geometry)
        width_svg, height_svg = geometry_size(display_geometry)
        detail = manifest_parts.get(part_id, {})
        used_by_icons = detail.get("used_by_icons")
        if used_by_icons is None:
            used_by_icons = step.part_usage_by_icon(counts_by_icon, part_id)

        items.append({
            "part_id": part_id,
            "part_number": part_numbers.get(part_id, 0),
            "kind": part_def["kind"],
            "quantity": int(detail.get("quantity", quantities.get(part_id, 0))),
            "source_count": int(detail.get("source_count", len(part_def.get("source_primitives", [])))),
            "used_by_icons": used_by_icons,
            "width_svg": width_svg,
            "height_svg": height_svg,
            "width_mm": width_svg * scale_svg_to_mm,
            "height_mm": height_svg * scale_svg_to_mm,
            "display_geometry": display_geometry,
            "distance_geometry": distance_geometry,
        })

    return sorted(items, key=lambda item: (item["part_number"], item["part_id"]))


def best_hausdorff(geometry_a, geometry_b, angles: Sequence[float]) -> tuple[float, float]:
    best_distance = float("inf")
    best_angle = 0.0
    distance_at_zero: float | None = None

    for angle in angles:
        rotated = affinity.rotate(geometry_b, angle, origin=(0, 0)) if angle else geometry_b
        distance = geometry_a.hausdorff_distance(rotated)
        if angle == 0:
            distance_at_zero = distance
        if distance < best_distance:
            best_distance = distance
            best_angle = float(angle)

    if distance_at_zero is not None and best_angle != 0 and distance_at_zero <= best_distance * 1.05:
        return distance_at_zero, 0.0
    return best_distance, best_angle


def pair_key(part_a: str, part_b: str) -> tuple[str, str]:
    return tuple(sorted((part_a, part_b)))


def distance_lookup(items: list[dict[str, Any]], angles: Sequence[float], scale_svg_to_mm: float) -> dict[tuple[str, str], dict]:
    distances: dict[tuple[str, str], dict] = {}
    for index, item_a in enumerate(items):
        for item_b in items[index + 1:]:
            distance_svg, rotation_deg = best_hausdorff(
                item_a["distance_geometry"],
                item_b["distance_geometry"],
                angles,
            )
            distances[pair_key(item_a["part_id"], item_b["part_id"])] = {
                "distance_svg": distance_svg,
                "distance_mm": distance_svg * scale_svg_to_mm,
                "rotation_deg": rotation_deg,
            }
    return distances


def choose_similarity_chain(items: list[dict[str, Any]], distances: dict[tuple[str, str], dict]) -> list[str]:
    ids = [item["part_id"] for item in items]
    number_by_id = {item["part_id"]: item["part_number"] for item in items}

    def distance_between(part_a: str, part_b: str) -> float:
        return distances[pair_key(part_a, part_b)]["distance_mm"]

    def chain_from(start_id: str) -> tuple[list[str], float, float]:
        remaining = set(ids)
        remaining.remove(start_id)
        chain = [start_id]
        total = 0.0
        maximum = 0.0

        while remaining:
            current = chain[-1]
            next_id = min(
                remaining,
                key=lambda part_id: (
                    distance_between(current, part_id),
                    number_by_id[part_id],
                    part_id,
                ),
            )
            distance = distance_between(current, next_id)
            total += distance
            maximum = max(maximum, distance)
            chain.append(next_id)
            remaining.remove(next_id)

        return chain, total, maximum

    return min(
        (chain_from(part_id) for part_id in ids),
        key=lambda result: (result[1], result[2], number_by_id[result[0][0]], result[0][0]),
    )[0]


def connector_label(distance: dict) -> str:
    label = f"HD {distance['distance_mm']:.2f} mm"
    if abs(distance["rotation_deg"]) > 1e-9:
        label += f" | rot {distance['rotation_deg']:.0f}"
    return label


def title_for_item(item: dict[str, Any]) -> str:
    icons = ", ".join(
        f"{icon.replace('Visit_Icon_', '')}: {count}"
        for icon, count in sorted(item["used_by_icons"].items())
    )
    return (
        f"Part {item['part_number']} ({item['part_id']})\n"
        f"kind: {item['kind']}\n"
        f"size: {item['width_mm']:.3f} x {item['height_mm']:.3f} mm\n"
        f"quantity: {item['quantity']}\n"
        f"source count: {item['source_count']}\n"
        f"used by: {icons or 'n/a'}"
    )


def render_item(item: dict[str, Any], rank: int, x: float, y: float, width: float, height: float, precision: float) -> list[str]:
    preview_x = x + 17.0
    preview_y = y + 38.0
    preview_w = width - 34.0
    preview_h = 78.0
    geometry = item["display_geometry"]
    shape_w, shape_h = geometry_size(geometry)
    shape_scale = min(
        preview_w / shape_w if shape_w > 0 else 1.0,
        preview_h / shape_h if shape_h > 0 else 1.0,
    )
    shape_scale = min(shape_scale, 8.0)
    draw_w = shape_w * shape_scale
    draw_h = shape_h * shape_scale
    tx = preview_x + (preview_w - draw_w) / 2
    ty = preview_y + (preview_h - draw_h) / 2
    path_data = iref.geometry_to_path_data(geometry, precision)
    fill = KIND_COLORS.get(item["kind"], "#475569")
    dims = f"{item['width_mm']:.1f} x {item['height_mm']:.1f} mm"

    return [
        f'<g id="rank-{rank:02d}-{html.escape(item["part_id"])}">',
        f'  <title>{html.escape(title_for_item(item))}</title>',
        f'  <rect class="part-card" x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="6"/>',
        f'  <text class="rank" x="{x + 10:.1f}" y="{y + 18:.1f}">{rank:02d}</text>',
        f'  <text class="part-title" x="{x + 42:.1f}" y="{y + 18:.1f}">Part {item["part_number"]}</text>',
        f'  <text class="part-id" x="{x + 10:.1f}" y="{y + 33:.1f}">{html.escape(item["part_id"])}</text>',
        f'  <rect class="preview-box" x="{preview_x:.1f}" y="{preview_y:.1f}" width="{preview_w:.1f}" height="{preview_h:.1f}"/>',
        f'  <g transform="translate({tx:.3f} {ty:.3f}) scale({shape_scale:.6f})">',
        f'    <path class="part-shape" fill="{fill}" d="{html.escape(path_data)}"/>',
        "  </g>",
        f'  <text class="part-meta" x="{x + 10:.1f}" y="{y + height - 21:.1f}">{html.escape(dims)}</text>',
        f'  <text class="part-meta" x="{x + 10:.1f}" y="{y + height - 8:.1f}">qty {item["quantity"]} | src {item["source_count"]}</text>',
        "</g>",
    ]


def render_connector(x1: float, y1: float, x2: float, y2: float, distance: dict) -> list[str]:
    label = connector_label(distance)
    label_width = max(76.0, len(label) * 5.2 + 10.0)
    label_x = (x1 + x2) / 2
    label_y = (y1 + y2) / 2 - 7
    if abs(x1 - x2) < 1e-6:
        label_x += 42
        label_y += 6
    return [
        f'<line class="connector" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" marker-end="url(#arrow)"/>',
        f'<rect class="connector-label-bg" x="{label_x - label_width / 2:.1f}" y="{label_y - 10:.1f}" width="{label_width:.1f}" height="16" rx="3"/>',
        f'<text class="connector-label" x="{label_x:.1f}" y="{label_y + 2:.1f}">{html.escape(label)}</text>',
    ]


def render_svg(
    items_by_id: dict[str, dict[str, Any]],
    chain: list[str],
    distances: dict[tuple[str, str], dict],
    args: argparse.Namespace,
    source_spec: Path,
    manifest_path: Path | None,
) -> str:
    columns = max(2, args.columns)
    precision = float(args.coordinate_precision)
    margin = 28.0
    header_height = 98.0
    card_w = 132.0
    card_h = 144.0
    connector_w = 82.0
    row_gap = 48.0
    rows = math.ceil(len(chain) / columns)
    width = margin * 2 + columns * card_w + (columns - 1) * connector_w
    height = header_height + rows * card_h + (rows - 1) * row_gap + margin

    positions: dict[str, tuple[float, float]] = {}
    for index, part_id in enumerate(chain):
        row = index // columns
        offset = index % columns
        visual_col = offset if row % 2 == 0 else columns - 1 - offset
        x = margin + visual_col * (card_w + connector_w)
        y = header_height + row * (card_h + row_gap)
        positions[part_id] = (x, y)

    source_note = f"source spec: {source_spec.as_posix()}"
    manifest_note = f"fixture manifest: {manifest_path.as_posix()}" if manifest_path else ""

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        "  <defs>",
        '    <marker id="arrow" markerWidth="8" markerHeight="8" refX="6.5" refY="4" orient="auto" markerUnits="strokeWidth">',
        '      <path d="M 0 0 L 8 4 L 0 8 z" fill="#B45309"/>',
        "    </marker>",
        "  </defs>",
        "  <style>",
        "    .background { fill: #FFFFFF; }",
        "    .doc-title { font: 700 22px Arial, sans-serif; fill: #111827; }",
        "    .doc-note { font: 12px Arial, sans-serif; fill: #475569; }",
        "    .part-card { fill: #F8FAFC; stroke: #CBD5E1; stroke-width: 1; }",
        "    .rank { font: 700 12px Arial, sans-serif; fill: #475569; }",
        "    .part-title { font: 700 14px Arial, sans-serif; fill: #111827; }",
        "    .part-id { font: 10px Arial, sans-serif; fill: #475569; }",
        "    .preview-box { fill: #FFFFFF; stroke: #E2E8F0; stroke-width: 1; }",
        "    .part-shape { fill-opacity: 0.78; stroke: #111827; stroke-width: 0.18; vector-effect: non-scaling-stroke; fill-rule: evenodd; }",
        "    .part-meta { font: 10px Arial, sans-serif; fill: #334155; }",
        "    .connector { stroke: #B45309; stroke-width: 1.6; fill: none; }",
        "    .connector-label-bg { fill: #FFFFFF; stroke: #FDBA74; stroke-width: 0.8; }",
        "    .connector-label { font: 700 9px Arial, sans-serif; fill: #7C2D12; text-anchor: middle; }",
        "  </style>",
        f'  <rect class="background" x="0" y="0" width="{width:.0f}" height="{height:.0f}"/>',
        f'  <text class="doc-title" x="{margin:.1f}" y="32">Fixture parts ordered by adjacent Hausdorff similarity</text>',
        f'  <text class="doc-note" x="{margin:.1f}" y="54">Greedy nearest-neighbor chain chosen from every possible start. Distances are centroid-normalized 2D Hausdorff values in millimeters.</text>',
        f'  <text class="doc-note" x="{margin:.1f}" y="72">{html.escape(source_note)}</text>',
        f'  <text class="doc-note" x="{margin:.1f}" y="90">{html.escape(manifest_note)}</text>',
    ]

    for index, part_id in enumerate(chain):
        x, y = positions[part_id]
        lines.extend(
            "  " + line
            for line in render_item(items_by_id[part_id], index + 1, x, y, card_w, card_h, precision)
        )

    for index, part_id in enumerate(chain[:-1]):
        next_id = chain[index + 1]
        x1, y1 = positions[part_id]
        x2, y2 = positions[next_id]
        if abs(y1 - y2) < 1e-6:
            if x2 > x1:
                start = (x1 + card_w, y1 + card_h / 2)
                end = (x2, y2 + card_h / 2)
            else:
                start = (x1, y1 + card_h / 2)
                end = (x2 + card_w, y2 + card_h / 2)
        else:
            start = (x1 + card_w / 2, y1 + card_h)
            end = (x2 + card_w / 2, y2)
        lines.extend(
            "  " + line
            for line in render_connector(
                start[0],
                start[1],
                end[0],
                end[1],
                distances[pair_key(part_id, next_id)],
            )
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def build_report(
    items_by_id: dict[str, dict[str, Any]],
    chain: list[str],
    distances: dict[tuple[str, str], dict],
    args: argparse.Namespace,
    source_spec: Path,
    manifest_path: Path | None,
    output_path: Path,
    json_path: Path,
    scale_svg_to_mm: float,
    angles: Sequence[float],
) -> dict:
    order = []
    adjacent_distances = []
    for index, part_id in enumerate(chain):
        item = items_by_id[part_id]
        row = {
            "rank": index + 1,
            "part_id": part_id,
            "part_number": item["part_number"],
            "kind": item["kind"],
            "quantity": item["quantity"],
            "source_count": item["source_count"],
            "used_by_icons": item["used_by_icons"],
            "width_svg": round(item["width_svg"], 6),
            "height_svg": round(item["height_svg"], 6),
            "width_mm": round(item["width_mm"], 6),
            "height_mm": round(item["height_mm"], 6),
        }
        if index < len(chain) - 1:
            next_id = chain[index + 1]
            distance = distances[pair_key(part_id, next_id)]
            adjacent_distances.append(distance["distance_mm"])
            row["next"] = {
                "part_id": next_id,
                "part_number": items_by_id[next_id]["part_number"],
                "hausdorff_svg": round(distance["distance_svg"], 6),
                "hausdorff_mm": round(distance["distance_mm"], 6),
                "best_rotation_deg": round(distance["rotation_deg"], 6),
            }
        order.append(row)

    return {
        "schema": "visit.part-similarity-legend.v1",
        "generator": "tools/generate_part_similarity_legend.py",
        "source_spec": source_spec.as_posix(),
        "fixture_manifest": manifest_path.as_posix() if manifest_path else None,
        "legend_svg": output_path.as_posix(),
        "report_json": json_path.as_posix(),
        "part_count": len(chain),
        "metric": {
            "name": "centroid-normalized Hausdorff distance",
            "source_units": "svg_user_units",
            "report_units": "mm",
            "scale_svg_to_mm": scale_svg_to_mm,
            "rotation_aware": not args.no_rotation,
            "rotation_angles_deg": list(angles),
        },
        "ordering": {
            "method": "greedy nearest-neighbor chain, best total adjacent distance across all starts",
            "total_adjacent_hausdorff_mm": round(sum(adjacent_distances), 6),
            "max_adjacent_hausdorff_mm": round(max(adjacent_distances), 6) if adjacent_distances else 0.0,
        },
        "order": order,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=step.DEFAULT_KIT_SPEC, help="Input part spec JSON")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Fixture manifest JSON")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output similarity legend SVG")
    parser.add_argument("--json-out", help="Output JSON report; defaults to SVG path with .json")
    parser.add_argument("--scale-svg-to-mm", type=float, help="Scale used for millimeter distance reporting; defaults to manifest scale or 1.0")
    parser.add_argument("--columns", type=int, default=4, help="Number of cards per row")
    parser.add_argument("--coordinate-precision", type=float, default=0.001)
    parser.add_argument("--no-rotation", action="store_true", help="Use only unrotated Hausdorff comparisons")
    parser.add_argument(
        "--rotation-angles",
        nargs="*",
        type=float,
        help="Angles to test for rotation-aware distance, default matches icon_parts simplification",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_spec = Path(args.spec)
    output_path = Path(args.out)
    json_path = Path(args.json_out) if args.json_out else output_path.with_suffix(".json")
    manifest_path = Path(args.manifest) if args.manifest else None

    spec = load_json(source_spec)
    manifest = load_json(manifest_path) if manifest_path else None
    scale_svg_to_mm = (
        float(args.scale_svg_to_mm)
        if args.scale_svg_to_mm is not None
        else float(manifest.get("scale_svg_to_mm", 1.0)) if manifest else 1.0
    )
    angles = [0.0] if args.no_rotation else list(args.rotation_angles or ip.DEFAULT_ROTATION_ANGLES)

    items = build_items(spec, manifest, scale_svg_to_mm)
    if len(items) < 2:
        raise SystemExit("Need at least two parts for similarity ordering")

    distances = distance_lookup(items, angles, scale_svg_to_mm)
    chain = choose_similarity_chain(items, distances)
    items_by_id = {item["part_id"]: item for item in items}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_svg(items_by_id, chain, distances, args, source_spec, manifest_path),
        encoding="utf-8",
    )
    write_json(
        json_path,
        build_report(
            items_by_id,
            chain,
            distances,
            args,
            source_spec,
            manifest_path,
            output_path,
            json_path,
            scale_svg_to_mm,
            angles,
        ),
    )

    adjacent = [
        distances[pair_key(part_id, chain[index + 1])]["distance_mm"]
        for index, part_id in enumerate(chain[:-1])
    ]
    print(f"part similarity legend: {len(chain)} parts -> {output_path.as_posix()}")
    print(f"part similarity report: {json_path.as_posix()}")
    print(f"adjacent Hausdorff: total={sum(adjacent):.3f}mm max={max(adjacent):.3f}mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
