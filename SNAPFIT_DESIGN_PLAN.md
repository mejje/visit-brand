# Snap-Fit Design Plan

Last updated: 2026-06-28

## Current Direction

Use a simple tapered friction peg as the first mechanical interface between translucent front icon pieces and a future backplate/socket layer.

This is deliberately conservative:

- It is easy to print vertically on FDM printers.
- It can be tested with a small coupon before printing a full kit.
- It gives a measurable clearance choice before adding retention lips, cantilever hooks, or keyhole features.

## First Geometry

Default parameters:

- Peg radius: `1.8 mm`
- Peg tip radius: `1.55 mm`
- Peg height: `3.0 mm`
- Peg edge clearance inside part footprint: `1.0 mm`
- Maximum pegs per front piece: `2`

The front piece remains a visible slab. Pegs are added on the back face, so a part can be printed front-face down with the pegs growing upward.

## Commands

Generate the fit coupon:

```text
python tools/export_step.py snap-coupon \
  --out analysis/runs/snapfit/friction-peg-v1/snapfit-coupon.step \
  --manifest analysis/runs/snapfit/friction-peg-v1/snapfit-coupon.manifest.json \
  --verify-import
```

Generate the first snap-enabled icon-piece kit:

```text
python tools/export_step.py kit \
  --scope icon \
  --icon "Visit_Icon_Platform" \
  --snap-style friction-peg \
  --out analysis/runs/snapfit/friction-peg-v1/Visit_Icon_Platform.snap-kit.step \
  --manifest analysis/runs/snapfit/friction-peg-v1/Visit_Icon_Platform.snap-kit.manifest.json \
  --verify-import
```

## Current Results

- Coupon clearances: `0.1`, `0.2`, `0.3`, and `0.4 mm`.
- Coupon STEP re-import delta: `0.0 mm^3`.
- Platform snap kit: 2 part designs, 8 printed pieces, 1 plate.
- Platform snap kit STEP re-import delta: `1e-09 mm^3`.
- Universal single-icon dry run: all 41 part designs can accept the default pegs; 128 pegs across 65 printed pieces.

## Next Validation

1. Print the snap coupon.
2. Test peg insertion and removal against each clearance.
3. Record printer, filament, nozzle, layer height, selected clearance, and failure mode.
4. Use the selected clearance to generate the first socket/backplate prototype.
5. Print the Platform snap kit plus matching socket/backplate as the first complete mechanical assembly.

Do not lock the peg radius, clearance, or retention style until the coupon has been printed and handled.
