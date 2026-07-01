# CAD Feasibility Spike

Last updated: 2026-06-30

## Goal

Prove that generated reference geometry can become editable STEP solids without going through STL.

Initial scope:

- Load `analysis/references/Visit_Icon_Hotel.reference.json`.
- Convert Shapely `Polygon`/`MultiPolygon` geometry into CAD sketch profiles.
- Scale SVG units into millimeters.
- Flip SVG y-down coordinates into CAD y-up coordinates.
- Extrude the front icon into a raised solid.
- Export STEP.
- Re-import STEP and compare volume.

## First Stack Tested

The first implementation uses `build123d`.

Reasons:

- It is Python-first and Open Cascade based.
- It can import and export STEP.
- Its sketch/profile model maps naturally from Shapely polygon rings.

Install CAD dependencies with the CAD-specific requirements file:

```text
python -m pip install -r requirements-cad.txt
```

This file includes the base reference-rendering dependencies, then adds `build123d`.
Using a virtual environment is recommended because `build123d` brings in a larger CAD dependency stack.

## Current Command

```text
python tools/export_step.py front \
  --reference analysis/references/Visit_Icon_Hotel.reference.json \
  --out cad/exports/step/Visit_Icon_Hotel.front.step \
  --icon-size-mm 120 \
  --front-depth-mm 8 \
  --verify-import
```

The part-library kit exporter uses the selected part spec instead of a whole-icon reference:

```text
python tools/export_step.py kit \
  --spec analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json \
  --out analysis/runs/kits/recommended/universal-single-icon-kit.step \
  --manifest analysis/runs/kits/recommended/universal-single-icon-kit.manifest.json \
  --split-plates \
  --verify-import
```

## Coordinate Mapping

Reference SVGs use `viewBox="0 0 48 48"` with y increasing downward.

The STEP export maps this into a centered CAD coordinate system:

- x: `(svg_x - center_x) * scale`
- y: `(center_y - svg_y) * scale`
- z: extrusion depth in millimeters

For a 120 mm icon, one SVG unit is `2.5 mm`.

## Success Criteria

- STEP export succeeds.
- STEP re-import succeeds.
- Re-imported volume matches the generated part volume within tolerance.
- The output remains STEP-only; no STL files are generated.

## Current Result

The checked-in Hotel front-icon export succeeded:

```text
python tools/export_step.py front \
  --reference analysis/references/Visit_Icon_Hotel.reference.json \
  --out cad/exports/step/Visit_Icon_Hotel.front.step \
  --icon-size-mm 120 \
  --front-depth-mm 8 \
  --verify-import
```

Observed result:

```text
exported cad/exports/step/Visit_Icon_Hotel.front.step volume=24600.000000mm^3 reimport_delta=0.000000
```

The generated STEP file is deterministic across repeated exports when using the fixed exporter timestamp.

A smoke test also exported all 14 current reference JSON files to temporary STEP files and
re-imported each one with `reimport_delta=0.000000`. That means the current front-icon
reference geometry is broadly compatible with the build123d sketch-to-STEP path.

The first laid-out universal single-icon kit export also succeeded:

```text
python tools/export_step.py kit \
  --out analysis/runs/kits/recommended/universal-single-icon-kit.step \
  --manifest analysis/runs/kits/recommended/universal-single-icon-kit.manifest.json \
  --split-plates \
  --verify-import
```

Observed result:

```text
41 unique part designs, 66 printed pieces, 4 plates
combined STEP reimport_delta=0.000000002mm^3
```

This proves the selected 41-part spec can be turned into separate laid-out STEP solids.
It does not yet prove PrusaSlicer preserves those bodies in the desired workflow.

## Current Mechanical Path

The mechanical path is `tools/export_step.py part-fixture-kit`, which exports hollow front caps plus one small two-hole backplate for each physical icon part.

Current Platform fixture result:

```text
python tools/export_step.py part-fixture-kit \
  --scope icon \
  --icon "Visit_Icon_Platform" \
  --out analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Platform.fixture-kit.step \
  --manifest analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Platform.fixture-kit.manifest.json \
  --verify-import
```

Observed result:

```text
1 unique part design, 8 hollow front caps, 8 backplates, 1 plate
combined STEP reimport_delta=0.000000001mm^3
```

Current universal fixture result:

```text
41 unique part designs, 66 hollow front caps, 66 backplates, 8 plates
combined STEP reimport_delta=0.000000500mm^3
```

The current STEP exporters also include shallow engraved global part-number geometry by default. Plain front pieces are engraved on the top face; hollow fixture caps are engraved on the inside face; matching backplates are engraved on the cap-facing face. Use `--no-physical-marks` for clean geometry exports if print testing shows the text is too small or visually intrusive.

## Follow-Up Questions

- Does the generated STEP open cleanly in FreeCAD?
- Does the generated STEP import cleanly in PrusaSlicer?
- Does PrusaSlicer preserve separate STEP bodies/parts well enough for the employee workflow?
- Does PrusaSlicer preserve the front-cap/backplate body labels well enough for the employee workflow?
- Are the hollow cap walls and small backplate pin holes printable and usable at the current scale?
