"""Generate finite decomposition candidates from exact icon part specs.

Subcommands:
  generate   Create candidate part specs with decomposed source parts
  score      Score generated candidate specs against reference geometry
  render     Render candidate part outlines for visual review
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from shapely.ops import triangulate, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icon_parts as ip  # noqa: E402
import icon_reference as iref  # noqa: E402


GENERATOR = "tools/icon_decompose.py"


def load_spec(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Part spec not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rounded_bounds(geom, precision: float) -> list[float]:
    bounds = geom.bounds if not geom.is_empty else (0, 0, 0, 0)
    return [iref.round_float(value, precision) for value in bounds]


def translate_to_origin(geom):
    from shapely import affinity

    min_x, min_y, _max_x, _max_y = geom.bounds
    return iref.canonical_geometry(affinity.translate(geom, xoff=-min_x, yoff=-min_y))


def unique_vertex_count(geom) -> int:
    if geom.geom_type != "Polygon":
        return 0
    coords = list(geom.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    return len(coords)


def classify_piece(geom) -> str:
    if ip.is_axis_aligned_rect(geom):
        return "rect"
    if unique_vertex_count(geom) == 3:
        return "triangle"
    return "polygon"


def geometry_signature(kind: str, geom, precision: float) -> str:
    min_x, min_y, max_x, max_y = geom.bounds
    width = iref.round_float(max_x - min_x, precision)
    height = iref.round_float(max_y - min_y, precision)
    if kind == "rect":
        return f"rect_{width}x{height}"
    payload = iref.canonical_geometry(geom).wkb
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{kind}_{width}x{height}_{digest}"


def piece_to_part_def(kind: str, geom, precision: float, source_part: str) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = geom.bounds
    width = iref.round_float(max_x - min_x, precision)
    height = iref.round_float(max_y - min_y, precision)
    part_def: dict[str, Any] = {
        "kind": kind,
        "bounds": [0.0, 0.0, width, height],
        "source_parts": [{"part": source_part, "strategy": "triangulate"}],
        "print": {
            "min_feature": iref.round_float(ip.compute_min_feature(geom, 0.01), 0.01),
        },
    }
    if kind == "rect":
        part_def["width"] = width
        part_def["height"] = height
    else:
        part_def["geometry"] = {
            "format": "wkb_hex",
            "value": iref.canonical_geometry(geom).wkb_hex,
        }
    return part_def


def add_piece_part(
    piece_parts: dict[str, dict],
    signature_to_part: dict[str, str],
    kind: str,
    normalized_geom,
    precision: float,
    source_part: str,
) -> str:
    signature = geometry_signature(kind, normalized_geom, precision)
    if signature in signature_to_part:
        part_id = signature_to_part[signature]
        piece_parts[part_id].setdefault("source_parts", []).append(
            {"part": source_part, "strategy": "triangulate"}
        )
        return part_id

    part_id = f"decomp_{len(piece_parts):04d}"
    signature_to_part[signature] = part_id
    piece_parts[part_id] = piece_to_part_def(kind, normalized_geom, precision, source_part)
    return part_id


def triangulate_geometry(
    geom,
    min_area: float,
    max_area_error_ratio: float,
    max_hausdorff: float,
) -> tuple[list, bool]:
    pieces = []
    if geom.is_empty:
        return pieces, False

    for candidate in triangulate(geom):
        clipped = candidate.intersection(geom)
        for polygon in iref.extract_polygons(clipped):
            if polygon.area <= min_area:
                continue
            pieces.append(iref.canonical_geometry(polygon))

    if not pieces and geom.area > min_area:
        return [iref.canonical_geometry(geom)], True

    if len(pieces) > 1:
        unioned = iref.canonical_geometry(unary_union(pieces))
        area_error = geom.symmetric_difference(unioned).area
        area_ratio = area_error / geom.area if geom.area > 0 else 0.0
        hausdorff = geom.hausdorff_distance(unioned)
        component_delta = len(iref.extract_polygons(unioned)) - len(iref.extract_polygons(geom))
        if area_ratio > max_area_error_ratio or hausdorff > max_hausdorff or component_delta > 0:
            return [iref.canonical_geometry(geom)], True

    pieces.sort(key=lambda g: (*rounded_bounds(g, 0.000000001), iref.round_float(g.area, 0.000000001)))
    return pieces, False


def has_rotated_instances(spec: dict) -> bool:
    return any(
        "rotate" in inst
        for icon_spec in spec["icons"].values()
        for inst in icon_spec["instances"]
    )


def triangulated_spec(
    spec: dict,
    min_area: float,
    max_area_error_ratio: float,
    max_hausdorff: float,
) -> dict:
    if has_rotated_instances(spec):
        raise SystemExit("Triangulation currently expects an unrotated exact baseline spec")

    precision = spec["settings"]["coordinate_precision"]
    original_parts = spec["parts"]

    piece_parts: dict[str, dict] = {}
    signature_to_part: dict[str, str] = {}
    replacements: dict[str, list[dict]] = {}
    split_source_parts = 0
    fallback_source_parts = 0

    for source_part, part_def in sorted(original_parts.items()):
        geom = ip.part_to_geometry(part_def)
        if part_def["kind"] != "polygon":
            pieces = [geom]
            used_fallback = False
        else:
            pieces, used_fallback = triangulate_geometry(
                geom,
                min_area,
                max_area_error_ratio,
                max_hausdorff,
            )
            if used_fallback:
                fallback_source_parts += 1
            elif len(pieces) > 1:
                split_source_parts += 1

        replacement_entries = []
        for piece in pieces:
            min_x, min_y, _max_x, _max_y = piece.bounds
            normalized = translate_to_origin(piece)
            kind = classify_piece(normalized)
            part_id = add_piece_part(
                piece_parts,
                signature_to_part,
                kind,
                normalized,
                precision,
                source_part,
            )
            replacement_entries.append({
                "part": part_id,
                "offset": [
                    iref.round_float(min_x, precision),
                    iref.round_float(min_y, precision),
                ],
            })

        replacements[source_part] = replacement_entries

    icons: dict[str, dict] = {}
    for icon_id, icon_spec in sorted(spec["icons"].items()):
        instances = []
        for inst in icon_spec["instances"]:
            source_part = inst["part"]
            at_x, at_y = inst["at"]
            for entry in replacements[source_part]:
                off_x, off_y = entry["offset"]
                new_inst = {
                    "part": entry["part"],
                    "at": [
                        iref.round_float(at_x + off_x, precision),
                        iref.round_float(at_y + off_y, precision),
                    ],
                    "source_part": source_part,
                    "source_index": inst.get("source_index"),
                }
                instances.append(new_inst)
        icons[icon_id] = {"instances": instances}

    return {
        "schema": spec["schema"],
        "generator": f"{GENERATOR} generate triangulated",
        "units": spec["units"],
        "coordinate_system": spec["coordinate_system"],
        "allowed_transforms": {
            "translate": True,
            "rotate": False,
            "mirror": False,
            "scale": False,
        },
        "settings": {
            **spec["settings"],
            "decomposition_strategy": "triangulate",
            "fallback_source_parts": fallback_source_parts,
            "min_piece_area": min_area,
            "split_source_parts": split_source_parts,
            "triangulation_max_area_error_ratio": max_area_error_ratio,
            "triangulation_max_hausdorff": max_hausdorff,
        },
        "parts": piece_parts,
        "icons": icons,
    }


def score_spec_file(spec_path: Path, refs: dict[str, tuple]) -> dict:
    spec = load_spec(spec_path)
    summary = ip.score_spec(spec, refs)
    worst_icon = max((row["area_error_ratio"] for row in summary["per_icon"]), default=0.0)
    return {
        "label": spec_path.stem.removeprefix("part-spec.").removesuffix(".v1"),
        "spec": spec_path.name,
        "unique_parts": summary["unique_parts"],
        "total_instances": summary["total_instances"],
        "area_error_ratio": summary["overall_area_error_ratio"],
        "total_area_error": iref.round_float(summary["total_area_error"], 0.000001),
        "worst_icon_error": worst_icon,
        "worst_hausdorff": summary["worst_hausdorff"],
    }


def write_score_rows(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def score_candidates(baseline: Path, candidates: Path, references: Path, out_path: Path) -> list[dict]:
    refs = {r[0]: r for r in ip.load_references(references)}
    rows = [score_spec_file(baseline, refs)]
    for spec_path in sorted(candidates.glob("part-spec.*.v1.json"), key=lambda p: p.name.lower()):
        if spec_path.resolve() == baseline.resolve():
            continue
        rows.append(score_spec_file(spec_path, refs))
    write_score_rows(rows, out_path)
    return rows


def print_rows(rows: list[dict]) -> None:
    print(f"{'label':<24s} {'parts':>6s} {'inst':>6s} {'area_err':>12s} {'hausdorff':>10s}")
    print("-" * 68)
    for row in rows:
        print(
            f"{row['label']:<24s} {row['unique_parts']:>6d} {row['total_instances']:>6d} "
            f"{row['area_error_ratio']:>12.6g} {row['worst_hausdorff']:>10.4f}"
        )


def generate_command(args: argparse.Namespace) -> int:
    spec = load_spec(Path(args.spec))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = triangulated_spec(
        spec,
        args.min_piece_area,
        args.max_local_area_error_ratio,
        args.max_local_hausdorff,
    )
    out_path = out_dir / "part-spec.triangulated.v1.json"
    write_json(out_path, generated)

    part_count = len(generated["parts"])
    instance_count = sum(len(icon["instances"]) for icon in generated["icons"].values())
    print(f"generate: wrote {out_path}")
    print(f"  triangulated candidate: {part_count} unique parts, {instance_count} instances")
    print(
        "  source parts split/fallback: "
        f"{generated['settings']['split_source_parts']}/"
        f"{generated['settings']['fallback_source_parts']}"
    )

    if args.score:
        rows = score_candidates(
            Path(args.spec),
            out_dir,
            Path(args.references),
            out_dir / "pareto.jsonl",
        )
        print_rows(rows)

    if args.render:
        render_dir = out_dir / "triangulated"
        render_args = argparse.Namespace(
            spec=str(out_path),
            references=args.references,
            out=str(render_dir),
        )
        ip.render_command(render_args)

    return 0


def score_command(args: argparse.Namespace) -> int:
    rows = score_candidates(
        Path(args.baseline),
        Path(args.candidates),
        Path(args.references),
        Path(args.out),
    )
    print_rows(rows)
    print(f"score: wrote {args.out}")
    return 0


def render_command(args: argparse.Namespace) -> int:
    render_args = argparse.Namespace(
        spec=args.spec,
        references=args.references,
        out=args.out,
    )
    return ip.render_command(render_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="Generate decomposition candidate specs")
    gen.add_argument("--spec", default="analysis/runs/exact/part-spec.exact.v1.json")
    gen.add_argument("--references", default="analysis/references")
    gen.add_argument("--out", default="analysis/runs/decompose")
    gen.add_argument("--min-piece-area", type=float, default=1e-8)
    gen.add_argument("--max-local-area-error-ratio", type=float, default=1e-8)
    gen.add_argument("--max-local-hausdorff", type=float, default=1e-6)
    gen.add_argument("--score", action="store_true", help="Score generated candidates after writing")
    gen.add_argument("--render", action="store_true", help="Render generated candidate outlines")
    gen.set_defaults(func=generate_command)

    score = subparsers.add_parser("score", help="Score decomposition candidate specs")
    score.add_argument("--baseline", default="analysis/runs/exact/part-spec.exact.v1.json")
    score.add_argument("--candidates", default="analysis/runs/decompose")
    score.add_argument("--references", default="analysis/references")
    score.add_argument("--out", default="analysis/runs/decompose/pareto.jsonl")
    score.set_defaults(func=score_command)

    render = subparsers.add_parser("render", help="Render one decomposition candidate spec")
    render.add_argument("--spec", default="analysis/runs/decompose/part-spec.triangulated.v1.json")
    render.add_argument("--references", default="analysis/references")
    render.add_argument("--out", default="analysis/runs/decompose/triangulated")
    render.set_defaults(func=render_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
