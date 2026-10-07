# Quick Start

Print and mount a Visit brand icon using a standard FDM printer.

**Status:** Prototype workflow. STEP generation and PrusaSlicer import are validated on a Prusa MINI profile. Fit clearances and wall-mounting are not yet physically validated — print the fit coupon first (see `fit-calibration.md`).

## What you need

- A Visit brand icon kit STEP file (per-part fixture kit):
  - Universal single-icon kit: `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.step`
  - One plate at a time (180 x 180 mm bed): `...plate_01.step` ... `...plate_08.step`
  - Single icon example: `analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Platform.fixture-kit.step`
- Assembly legend: `universal-single-icon-fixture-legend.svg`
- PrusaSlicer 2.9 or newer (native STEP import)
- Translucent white filament for the front caps, any PLA for the backplates
- Small pins or nails for wall mounting (pending facilities approval — see `mounting-guide.md`)

## Steps

1. **Calibrate fit once per printer/material** — print `analysis/runs/snapfit/fit-coupons/fit-coupon-kit.step` and follow `fit-calibration.md`. Skip this only if you are using an already-tested printer/material combination with the default 0.25 mm clearance.
2. **Open the kit STEP in PrusaSlicer** — File > Import, or drag the `.step` file in. The file contains separate bodies (caps and backplates); you can use a whole plate file as one print job.
3. **Select a printer/material preset** — validated example: `Original Prusa MINI & MINI+` with `0.20mm QUALITY @MINI` and `Prusament PLA`.
4. **Slice and print** — the default kit fits a 180 x 180 mm bed per plate. No supports are needed for the caps when printed open-side-up (default orientation).
5. **Assemble** — match the engraved part numbers on caps and backplates. See `assembly-guide.md`.
6. **Mount** — pin each backplate to the wall, then snap its cap on. See `mounting-guide.md`.

## How the parts work

Each icon part is a pair:

- a small hidden **backplate** with two mounting holes,
- a hollow **front cap** in translucent filament that snaps over the backplate.

Parts are reusable across icons. The universal kit prints every unique part design at the maximum quantity needed to build any one icon.

## Validated facts

- All kit plates import as manifold bodies; body counts match the manifest exactly (67 front caps + 67 backplates across 8 plates).
- Every plate fits a 180 x 180 mm bed.
- Slicing each plate to G-code succeeds with zero import or geometry warnings (see `analysis/runs/slicer-validation/slicer-validation.json`).

## If something looks wrong

- Missing parts or wrong quantities: check the manifest JSON next to the STEP file.
- Caps too tight or too loose: see `fit-calibration.md`.
- Slicer refuses the STEP: confirm PrusaSlicer 2.9+; older versions cannot import STEP.
