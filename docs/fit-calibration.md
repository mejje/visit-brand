# Fit Calibration

Find the right cap-to-backplate clearance for your printer and material before printing a full kit.

**Status:** The coupon geometry is generated and slicer-validated. The clearance recommendation (0.25 mm default) is provisional until coupons are physically printed and handled.

## Why

Cap fit varies with printer, nozzle, material, and slicer settings. A clearance that works on one machine can be too tight or too loose on another. The coupon kit tests three clearances in one print.

## The coupon kit

- File: `analysis/runs/snapfit/fit-coupons/fit-coupon-kit.step`
- One plate: 3 cap/backplate pairs, 6 pieces total
- Coupon footprint: 22 x 12 mm, same wall (1.0 mm), face (1.2 mm), depth (8 mm), and backplate (3.0 mm) as the real kit
- Each pair is marked with a two-digit code on the cap inside face and the backplate top face

| Code | Clearance |
| --- | --- |
| 15 | 0.15 mm |
| 25 | 0.25 mm |
| 35 | 0.35 mm |

The code is the clearance in hundredths of a millimeter: `25` means 0.25 mm.

## Steps

1. Slice and print `fit-coupon-kit.step` with the same printer, material, nozzle, and profile you plan to use for the icon kit.
2. After printing, snap each cap over the backplate with the matching code.
3. Test both directions:
   - Cap should slide on with light hand pressure.
   - Cap should stay on when the assembly is turned upside down and lightly shaken.
   - Cap should be removable by hand without tools and without cracking.
4. Record the code that feels best for your machine and material.
5. Regenerate the kit with that clearance:

```text
python tools/export_step.py part-fixture-kit \
  --scope universal \
  --fit-clearance-mm <chosen value, e.g. 0.25> \
  --out analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.step \
  --manifest analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.manifest.json \
  --split-plates \
  --verify-import
```

## Changing the coupon values

Generate a coupon set with different test clearances:

```text
python tools/export_step.py fit-coupon-kit \
  --clearances 0.1 0.2 0.3 0.4 \
  --out analysis/runs/snapfit/fit-coupons/fit-coupon-kit.step \
  --manifest analysis/runs/snapfit/fit-coupons/fit-coupon-kit.manifest.json \
  --split-plates
```

## Recording results

Record for each printer/material combination:

- printer model, nozzle size
- filament brand and type
- chosen clearance code
- notes (tight/loose, removal force, any cracking)

Keep this table somewhere shared so other makers can skip calibration when using the same setup.

| Printer | Nozzle | Material | Chosen clearance | Notes |
| --- | --- | --- | --- | --- |
| Original Prusa MINI | 0.4 | Prusament PLA | pending print test | slicer-validated only |
