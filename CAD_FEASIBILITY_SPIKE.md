# CAD Feasibility Spike

Last updated: 2026-06-27

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

## Follow-Up Questions

- Does the generated STEP open cleanly in FreeCAD?
- Does the generated STEP import cleanly in PrusaSlicer?
- Does PrusaSlicer preserve separate STEP bodies/parts well enough for the employee workflow?
- Should the front icon be one combined solid or separate STEP bodies per physical snap-in part?
- How should wall thickness and hollow translucent parts be represented before the part-library split exists?
