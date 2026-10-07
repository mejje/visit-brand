"""Validate exported STEP kits by loading and slicing them with PrusaSlicer.

PrusaSlicer is the only supported slicer for this project. This tool:
  - runs `--info` on each STEP to check manifoldness, body count, and bed fit
  - optionally slices each STEP to G-code using MINI profiles (180x180 bed)
  - writes a machine-readable report and prints a summary table

Example:
  python tools/validate_slicer.py \
    --inputs analysis/runs/kits/recommended \
    --inputs analysis/runs/snapfit/part-backplate-v1 \
    --slice \
    --out analysis/runs/slicer-validation
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_SLICER_PATHS = (
    r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
    r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe",
)
DEFAULT_PRINTER_PROFILE = "Original Prusa MINI & MINI+"
DEFAULT_PRINT_PROFILE = "0.20mm QUALITY @MINI"
DEFAULT_MATERIAL_PROFILE = "Prusament PLA"
DEFAULT_BED_WIDTH_MM = 180.0
DEFAULT_BED_DEPTH_MM = 180.0
KNOWN_NOISE = (
    "flatten_configbundle_hierarchy",
)

INFO_KEYS = (
    "size_x",
    "size_y",
    "size_z",
    "number_of_facets",
    "manifold",
    "number_of_parts",
    "volume",
)


def find_slicer(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise SystemExit(f"Slicer not found: {path}")
        return path
    for candidate in DEFAULT_SLICER_PATHS:
        if Path(candidate).exists():
            return Path(candidate)
    raise SystemExit("PrusaSlicer console not found; pass --slicer explicitly")


def run_slicer(slicer: Path, args: list[str], timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        [str(slicer), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_info(output: str) -> dict:
    info: dict = {}
    for line in output.splitlines():
        match = re.match(r"\s*([a-z_]+)\s*=\s*(.+?)\s*$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key not in INFO_KEYS:
            continue
        if key == "manifold":
            info[key] = value.strip().lower() == "yes"
        elif key == "number_of_facets" or key == "number_of_parts":
            try:
                info[key] = int(value)
            except ValueError:
                info[key] = value
        else:
            try:
                info[key] = float(value)
            except ValueError:
                info[key] = value
    return info


def relevant_problems(output: str) -> list[str]:
    problems = []
    for line in output.splitlines():
        lower = line.lower()
        if KNOWN_NOISE and any(noise in lower for noise in KNOWN_NOISE):
            continue
        if "[error]" in lower or "[warning]" in lower:
            problems.append(line.strip())
        elif re.search(r"\b(repair|not manifold|self-intersect)", lower):
            problems.append(line.strip())
    return problems


def validate_step(
    slicer: Path,
    step_path: Path,
    bed_width: float,
    bed_depth: float,
    timeout: int,
) -> dict:
    record: dict = {"step": step_path.as_posix()}
    exit_code, output = run_slicer(slicer, ["--info", str(step_path)], timeout)
    info = parse_info(output)
    record.update(info)
    size_x = info.get("size_x")
    size_y = info.get("size_y")
    if isinstance(size_x, float) and isinstance(size_y, float):
        record["fits_bed"] = size_x <= bed_width and size_y <= bed_depth
    record["info_exit_code"] = exit_code
    record["info_problems"] = relevant_problems(output)
    return record


def slice_step(
    slicer: Path,
    step_path: Path,
    printer: str,
    print_profile: str,
    material: str,
    gcode_dir: Path,
    timeout: int,
) -> dict:
    gcode_dir.mkdir(parents=True, exist_ok=True)
    gcode_path = gcode_dir / (step_path.stem + ".gcode")
    args = [
        "--printer-profile", printer,
        "--print-profile", print_profile,
        "--material-profile", material,
        "--export-gcode",
        "--loglevel", "3",
        "--output", str(gcode_path),
        str(step_path),
    ]
    try:
        exit_code, output = run_slicer(slicer, args, timeout)
    except subprocess.TimeoutExpired:
        return {"sliced": False, "slice_error": "timeout"}
    record: dict = {
        "sliced": exit_code == 0 and gcode_path.exists() and gcode_path.stat().st_size > 0,
        "gcode": gcode_path.as_posix() if gcode_path.exists() else None,
        "gcode_bytes": gcode_path.stat().st_size if gcode_path.exists() else 0,
        "slice_exit_code": exit_code,
        "slice_problems": relevant_problems(output),
    }
    return record


def collect_steps(inputs: Sequence[str], pattern: str, out_dir: Path) -> list[Path]:
    steps: list[Path] = []
    out_resolved = out_dir.resolve()
    for entry in inputs:
        path = Path(entry)
        if path.is_file() and path.suffix.lower() == ".step":
            steps.append(path)
            continue
        if path.is_dir():
            for candidate in sorted(path.glob(pattern)):
                if candidate.resolve().parent == out_resolved:
                    continue
                steps.append(candidate)
    unique: list[Path] = []
    seen = set()
    for step in steps:
        key = step.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(step)
    return unique


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", action="append", required=True, help="STEP file or directory (repeatable)")
    parser.add_argument("--pattern", default="*.plate_*.step", help="Glob for directory inputs")
    parser.add_argument("--out", default="analysis/runs/slicer-validation", help="Report and gcode output directory")
    parser.add_argument("--slicer", help="Path to prusa-slicer-console.exe")
    parser.add_argument("--printer-profile", default=DEFAULT_PRINTER_PROFILE)
    parser.add_argument("--print-profile", default=DEFAULT_PRINT_PROFILE)
    parser.add_argument("--material-profile", default=DEFAULT_MATERIAL_PROFILE)
    parser.add_argument("--bed-width", type=float, default=DEFAULT_BED_WIDTH_MM)
    parser.add_argument("--bed-depth", type=float, default=DEFAULT_BED_DEPTH_MM)
    parser.add_argument("--slice", action="store_true", help="Also slice each STEP to G-code")
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per slicer invocation")
    args = parser.parse_args(argv)

    slicer = find_slicer(args.slicer)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    gcode_dir = out_dir / "gcode"

    steps = collect_steps(args.inputs, args.pattern, out_dir)
    if not steps:
        raise SystemExit("No STEP files found for the given inputs")

    records = []
    for step in steps:
        record = validate_step(slicer, step, args.bed_width, args.bed_depth, args.timeout)
        if args.slice:
            record.update(
                slice_step(
                    slicer,
                    step,
                    args.printer_profile,
                    args.print_profile,
                    args.material_profile,
                    gcode_dir,
                    args.timeout,
                )
            )
        records.append(record)
        status = "manifold" if record.get("manifold") else "NOT-MANIFOLD"
        parts = record.get("number_of_parts", "?")
        fits = record.get("fits_bed")
        fit_text = "fits" if fits else ("OVERSIZE" if fits is False else "?")
        slice_text = ""
        if args.slice:
            slice_text = " sliced" if record.get("sliced") else " SLICE-FAILED"
        print(
            f"{step.name}: {status}, parts={parts}, {fit_text}{slice_text}, "
            f"problems={len(record.get('info_problems', [])) + len(record.get('slice_problems', []))}"
        )

    report = {
        "schema": "visit.slicer-validation.v1",
        "slicer": str(slicer),
        "printer_profile": args.printer_profile,
        "print_profile": args.print_profile,
        "material_profile": args.material_profile,
        "bed_mm": [args.bed_width, args.bed_depth],
        "files": records,
    }
    report_path = out_dir / "slicer-validation.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nreport written to {report_path}")

    failures = [
        r for r in records
        if not r.get("manifold")
        or r.get("fits_bed") is False
        or (args.slice and not r.get("sliced"))
        or r.get("info_problems")
        or r.get("slice_problems")
    ]
    if failures:
        print(f"\n{len(failures)} file(s) need attention:", file=sys.stderr)
        for record in failures:
            print(f"  {record['step']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
