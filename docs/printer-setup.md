# Printer Setup

Recommended printer, material, and slicing settings for the Visit brand icon kits.

**Status:** Slicing is validated with PrusaSlicer 2.9.6 on the `Original Prusa MINI & MINI+` profile. Physical print quality claims are not yet validated.

## Printer

- Any FDM printer with a bed of at least 180 x 180 mm works with the provided plate files.
- The validated reference profile is `Original Prusa MINI & MINI+` (180 x 180 x 180 mm).
- A 0.4 mm nozzle is assumed for all default settings.

## Slicer

- Use **PrusaSlicer 2.9 or newer** — native STEP import was added in 2.7.
- Import the `.step` files directly. Do not convert to STL; STEP keeps every body separate and marked.
- Validated profile combination:
  - Printer: `Original Prusa MINI & MINI+`
  - Print: `0.20mm QUALITY @MINI`
  - Filament: `Prusament PLA`

## Materials

- **Front caps:** translucent white PLA or PETG. PETG transmits light slightly better and is less brittle, but sticks more aggressively if the fit is too tight.
- **Backplates:** any PLA or PETG; they are hidden and can use leftover spools.
- Print all parts of one icon in the same material for consistent shrinkage, especially caps and backplates that must fit each other.

## Print settings

Defaults that were validated to slice cleanly:

- Layer height: 0.20 mm
- Perimeters: 2 minimum (the cap wall is 1.0 mm, so 3 perimeters can be safer on 0.4 mm nozzles)
- Infill: 15% for backplates; caps are mostly perimeter and solid face, infill matters little
- Supports: not needed. Caps print open-side-up as shallow trays; backplates are flat.
- Brim: not needed at default size; use one if your bed adhesion is marginal
- Orientation: import as-is from the STEP. The STEP layout already places every piece in its printable orientation.

## Translucent look

The see-through effect depends on how light passes through the 1.2 mm front face:

- Keep the front face solid (it is 1.2 mm by default).
- Lower layer height on the cap face (0.15 mm) improves light diffusion.
- White or natural translucent filaments give the intended dim glow; avoid opaque colors.

## Fit clearance

The cap-to-backplate fit is controlled by `--fit-clearance-mm` (default 0.25 mm):

- Too tight: caps crack or are impossible to remove.
- Too loose: caps fall off when brushed.
- Calibrate with the coupon kit before printing a full kit — see `fit-calibration.md`.

## Plate strategy

- The universal fixture kit for one icon is 8 plates on a 180 x 180 mm bed:
  `universal-single-icon-fixture-kit.plate_01.step` ... `plate_08.step`
- The single-icon Platform kit fits on 1 plate: `Visit_Icon_Platform.fixture-kit.step`
- Plate files are independent print jobs; print them in any order.
