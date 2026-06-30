"""Generate printable SVG assembly legends for per-part fixture kits."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_step as step  # noqa: E402
import icon_parts as ip  # noqa: E402
import icon_reference as iref  # noqa: E402


DEFAULT_OUT = "analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-legend.svg"
DEFAULT_MANIFEST = "analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.manifest.json"
PALETTE = [
    "#276EF1",
    "#0E9F6E",
    "#D97706",
    "#DC2626",
    "#7C3AED",
    "#0891B2",
    "#BE185D",
    "#4D7C0F",
    "#B45309",
    "#475569",
]


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def part_color(part_id: str) -> str:
    try:
        index = int(part_id.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        index = sum(ord(char) for char in part_id)
    return PALETTE[index % len(PALETTE)]


def display_icon_name(icon_id: str) -> str:
    name = icon_id.removeprefix("Visit_Icon_").replace("_", " ")
    return " ".join(part for part in name.split())


def scope_from_manifest(manifest_scope: str | None) -> str:
    return {
        "universal_single_icon": "universal",
        "single_icon": "icon",
        "all_icons": "all-icons",
    }.get(manifest_scope or "", "universal")


def assembly_from_inputs(args: argparse.Namespace, spec: dict, fixture_manifest: dict | None) -> dict:
    if (
        fixture_manifest
        and fixture_manifest.get("assembly")
        and fixture_manifest.get("marking", {}).get("scheme") == "global-part-number-v1"
    ):
        return fixture_manifest["assembly"]

    scope = args.scope
    icon_id = args.icon
    if fixture_manifest:
        scope = scope_from_manifest(fixture_manifest.get("scope"))
        icon_id = fixture_manifest.get("icon")

    counts_by_icon = step.icon_part_counts(spec)
    quantities = step.kit_quantities(counts_by_icon, scope, icon_id)
    part_numbers = step.part_number_map(spec["parts"])
    return step.icon_assembly_map(spec, quantities, scope, icon_id, part_numbers)


def geometry_for_placement(spec: dict, placement: dict):
    part_id = placement["part"]
    base_geometry = ip.part_to_geometry(
        spec["parts"][part_id],
        anchor=placement.get("anchor", "min_corner"),
    )
    at_x, at_y = placement["at_svg"]
    return ip.place_part(
        base_geometry,
        float(at_x),
        float(at_y),
        rotate=float(placement.get("rotate_deg") or 0.0),
    )


def placement_sort_key(placement: dict) -> tuple[int, str]:
    return (
        int(placement.get("placement_index", placement.get("source_index", 9998) + 1)),
        placement.get("part", ""),
    )


def selected_icon_ids(args: argparse.Namespace, assembly: dict) -> list[str]:
    available = assembly.get("icon_order") or sorted(assembly["icons"])
    requested = args.icons or ([args.icon] if args.icon else None)
    if not requested:
        return [icon_id for icon_id in available if icon_id in assembly["icons"]]

    missing = [icon_id for icon_id in requested if icon_id not in assembly["icons"]]
    if missing:
        raise SystemExit(f"Icons not found in assembly map: {', '.join(missing)}")
    return requested


def panel_height(placements: list[dict], icon_pixels: float) -> float:
    icon_height = 62 + icon_pixels
    return max(226.0, icon_height) + 18


def render_panel(
    icon_id: str,
    placements: list[dict],
    spec: dict,
    x: float,
    y: float,
    panel_width: float,
    panel_height_value: float,
    icon_pixels: float,
) -> list[str]:
    precision = float(spec.get("settings", {}).get("coordinate_precision", 1e-6))
    source_size = 48.0
    icon_scale = icon_pixels / source_size
    icon_x = x + (panel_width - icon_pixels) / 2
    icon_y = y + 56
    escaped_title = html.escape(display_icon_name(icon_id))
    lines = [
        f'<g id="{html.escape(icon_id)}">',
        f'  <rect class="panel" x="{x:.1f}" y="{y:.1f}" width="{panel_width:.1f}" height="{panel_height_value:.1f}" rx="6"/>',
        f'  <text class="panel-title" x="{x + 18:.1f}" y="{y + 28:.1f}">{escaped_title}</text>',
        f'  <rect class="icon-box" x="{icon_x:.1f}" y="{icon_y:.1f}" width="{icon_pixels:.1f}" height="{icon_pixels:.1f}"/>',
        f'  <g transform="translate({icon_x:.3f} {icon_y:.3f}) scale({icon_scale:.6f})">',
    ]

    for placement in placements:
        geometry = geometry_for_placement(spec, placement)
        path_data = iref.geometry_to_path_data(geometry, precision)
        color = part_color(placement["part"])
        lines.append(
            f'    <path class="part-shape" fill="{color}" d="{html.escape(path_data)}"/>'
        )

    lines.append("  </g>")

    for placement in placements:
        label_x, label_y = placement["label_point_svg"]
        cx = icon_x + float(label_x) * icon_scale
        cy = icon_y + float(label_y) * icon_scale
        label = html.escape(str(placement.get("part_number", placement["legend_label"])))
        lines.extend([
            f'  <circle class="callout" cx="{cx:.1f}" cy="{cy:.1f}" r="8.2"/>',
            f'  <text class="callout-text" x="{cx:.1f}" y="{cy + 3.6:.1f}">{label}</text>',
        ])

    lines.append("</g>")
    return lines


def render_svg(spec: dict, assembly: dict, icon_ids: list[str], args: argparse.Namespace) -> str:
    columns = max(1, args.columns)
    panel_width = 228.0
    gap = 18.0
    margin = 24.0
    header_height = 70.0
    icon_pixels = float(args.icon_pixels)

    panels = []
    for icon_id in icon_ids:
        placements = sorted(
            assembly["icons"][icon_id]["placements"],
            key=placement_sort_key,
        )
        panels.append((icon_id, placements, panel_height(placements, icon_pixels)))

    row_heights = []
    for start in range(0, len(panels), columns):
        row_heights.append(max(panel[2] for panel in panels[start:start + columns]))

    width = margin * 2 + columns * panel_width + (columns - 1) * gap
    height = header_height + margin + sum(row_heights) + gap * max(0, len(row_heights) - 1) + margin

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        "  <style>",
        "    .background { fill: #ffffff; }",
        "    .doc-title { font: 700 22px Arial, sans-serif; fill: #111827; }",
        "    .doc-note { font: 12px Arial, sans-serif; fill: #4b5563; }",
        "    .panel { fill: #f8fafc; stroke: #cbd5e1; stroke-width: 1; }",
        "    .panel-title { font: 700 15px Arial, sans-serif; fill: #111827; }",
        "    .icon-box { fill: #ffffff; stroke: #94a3b8; stroke-width: 1; }",
        "    .part-shape { fill-opacity: 0.68; stroke: #111827; stroke-width: 0.22; vector-effect: non-scaling-stroke; fill-rule: evenodd; }",
        "    .callout { fill: #ffffff; stroke: #111827; stroke-width: 1.4; }",
        "    .callout-text { font: 700 10px Arial, sans-serif; text-anchor: middle; fill: #111827; }",
        "  </style>",
        f'  <rect class="background" x="0" y="0" width="{width:.0f}" height="{height:.0f}"/>',
        f'  <text class="doc-title" x="{margin:.1f}" y="32">Visit icon fixture assembly legend</text>',
        f'  <text class="doc-note" x="{margin:.1f}" y="54">Callouts are global part numbers. Repeated numbers use duplicate copies of the same printed part.</text>',
    ]

    panel_index = 0
    current_y = header_height
    for row_height in row_heights:
        for column in range(columns):
            if panel_index >= len(panels):
                break
            icon_id, placements, actual_panel_height = panels[panel_index]
            x = margin + column * (panel_width + gap)
            lines.extend(
                "  " + line
                for line in render_panel(
                    icon_id,
                    placements,
                    spec,
                    x,
                    current_y,
                    panel_width,
                    actual_panel_height,
                    icon_pixels,
                )
            )
            panel_index += 1
        current_y += row_height + gap

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=step.DEFAULT_KIT_SPEC, help="Input part spec JSON")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Fixture kit manifest JSON")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output legend SVG")
    parser.add_argument("--json-out", help="Output legend mapping JSON; defaults to SVG path with .json")
    parser.add_argument(
        "--scope",
        choices=["universal", "icon", "all-icons"],
        default="universal",
        help="Fallback kit quantity scope when no manifest assembly map is available",
    )
    parser.add_argument("--icon", help="Optional single icon id")
    parser.add_argument("--icons", nargs="*", help="Optional list of icon ids to include")
    parser.add_argument("--columns", type=int, default=4, help="Number of legend columns")
    parser.add_argument("--icon-pixels", type=float, default=148.0, help="Rendered icon size per panel")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec_path = Path(args.spec)
    output_path = Path(args.out)
    json_path = Path(args.json_out) if args.json_out else output_path.with_suffix(".json")
    fixture_manifest_path = Path(args.manifest) if args.manifest else None

    spec = load_json(spec_path)
    fixture_manifest = load_json(fixture_manifest_path) if fixture_manifest_path else None
    assembly = assembly_from_inputs(args, spec, fixture_manifest)
    icon_ids = selected_icon_ids(args, assembly)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_svg(spec, assembly, icon_ids, args), encoding="utf-8")
    write_json(json_path, {
        "schema": "visit.fixture-legend.v1",
        "generator": "tools/generate_fixture_legend.py",
        "source_spec": spec_path.as_posix(),
        "fixture_manifest": fixture_manifest_path.as_posix() if fixture_manifest_path else None,
        "legend_svg": output_path.as_posix(),
        "icon_count": len(icon_ids),
        "part_numbers": assembly.get("part_numbers", {}),
        "icons": {
            icon_id: assembly["icons"][icon_id]
            for icon_id in icon_ids
        },
    })
    print(f"fixture legend: {len(icon_ids)} icons -> {output_path.as_posix()}")
    print(f"fixture legend map: {json_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
