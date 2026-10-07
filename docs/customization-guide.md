# Customization Guide

How to change icon size, mechanical parameters, and part selection, then regenerate STEP kits.

**Status:** Prototype. Commands are validated by slicer import on the default parameters.

## Setup

```text
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-cad.txt
```

`requirements-cad.txt` includes `requirements.txt` (shapely, svgelements, numpy, pymoo) plus build123d, which is needed for STEP generation.

## Change icon size

Icon size sets the printed size of the whole icon in millimeters. The source SVGs are 48 units wide, so scaling is `icon-size-mm / 48`.

```text
python tools/export_step.py part-fixture-kit \
  --scope icon --icon "Visit_Icon_Hotel" \
  --icon-size-mm 180 \
  --out analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Hotel.fixture-kit.step \
  --manifest analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Hotel.fixture-kit.manifest.json \
  --split-plates --verify-import
```

Note: larger icons mean larger individual parts; check that each part still fits your bed (the tool refuses pieces wider than `--bed-width-mm`).

## Change mechanical parameters

All mechanical values are CLI flags. Defaults:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--front-depth-mm` | 8.0 | How far the cap protrudes from the wall |
| `--front-wall-thickness-mm` | 1.0 | Cap side wall thickness |
| `--front-face-thickness-mm` | 1.2 | Visible translucent face thickness |
| `--fit-clearance-mm` | 0.25 | Cap-to-backplate XY clearance (calibrate this) |
| `--backplate-thickness-mm` | 3.0 | Hidden backplate thickness |
| `--z-clearance-mm` | 0.3 | Depth clearance between backplate and cap face |
| `--pin-hole-diameter-mm` | 1.6 | Mounting hole diameter |
| `--pin-hole-edge-clearance-mm` | 1.0 | Material required around each hole |
| `--pin-hole-min-spacing-mm` | 4.0 | Minimum distance between the two holes |
| `--bed-width-mm` / `--bed-depth-mm` | 180 / 180 | Printer bed used for plate layout |
| `--spacing-mm` | 4.0 | Gap between pieces on a plate |

The tool refuses parameter combinations that cannot work, for example a backplate thicker than the cap cavity, or a part too small for two mounting holes. Errors name the part and the reason.

## Choose a different part library

The kit is generated from a part spec. The current recommended spec is:

```text
analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json
```

Generate a kit from another spec with `--spec path/to/part-spec.json`.

To rebuild the simplified part library from the source SVGs:

```text
python tools/icon_reference.py build
python tools/icon_parts.py bootstrap
python tools/icon_parts.py simplify --no-bbox-decompose --polygon-tolerances 0.5 --rect-tolerances 1.0
python tools/icon_parts.py score --spec analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json
```

The `simplify` command writes candidate specs and a `pareto.jsonl` trade-off log.

## Regenerate the assembly legend

After regenerating a fixture kit, regenerate the legend:

```text
python tools/generate_fixture_legend.py \
  --manifest analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.manifest.json \
  --out analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-legend.svg
```

Turn engraving off for a plain test print with `--no-physical-marks`.

## Validate before printing

```text
python tools/validate_slicer.py \
  --inputs analysis/runs/snapfit/part-backplate-v1 \
  --inputs "analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Platform.fixture-kit.step" \
  --slice \
  --out analysis/runs/slicer-validation
```

This checks manifoldness, body counts, bed fit, and produces G-code with PrusaSlicer.

## Rebuild reference geometry

If source SVGs change:

```text
python tools/icon_reference.py build
python tools/icon_reference.py verify
```

`verify` compares source and canonical geometry against the stored references and fails loudly on drift.
