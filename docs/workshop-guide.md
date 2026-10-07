# Maker Workshop Guide

A suggested format for running a group build session with the Visit brand icon kits.

**Status:** Draft. Agenda is a proposal, not yet piloted.

## Audience and goals

- Employees or maker-space members with no CAD experience.
- Goal: each participant prints and assembles one icon, and can show others how to do the same.
- Duration: 2 to 3 hours, or split into two sessions (print day, assembly day).

## Materials per participant

- One kit plate set (`universal-single-icon-fixture-kit.plate_01.step` ... `plate_08.step`) or one single-icon kit
- Printed assembly legend for the participant's chosen icon
- Translucent filament for caps, scrap PLA for backplates
- Pins or adhesive strips for mounting (confirm policy first)
- Small parts tray or bag for keeping marked pieces organized

## Agenda (single 3-hour session)

1. **(15 min) Intro** — show a finished icon; explain the cap/backplate concept and that every part is marked with a number.
2. **(15 min) Slicer walkthrough** — open a plate STEP in PrusaSlicer, show separate bodies, slice to G-code.
3. **(20 min) Fit calibration demo** — print a coupon from a pre-heated printer; show how to read the two-digit code.
4. **(90 min) Print** — start the plate jobs; while printing, preview the legend and the assembly layout.
5. **(30 min) Assembly** — participants sort marked pieces, mount backplates on a demo board or wall, snap caps on.
6. **(10 min) Wrap-up** — collect clearance notes and feedback; take a group photo of the icons.

## Two-session variant

- Session 1 (60 min): intro, slicer walkthrough, start prints, collect kits when done.
- Session 2 (60 min): fit calibration results, assembly, mounting.

## Shared printer workflow

- Queue all plates as separate jobs; label each job with the owner name in the slicer.
- Print caps in translucent filament on one printer continuously; backplates can share any printer.
- Keep a single "calibration results" sheet on the wall so later jobs reuse known-good clearances.

## Safety

- Hot beds and nozzles: no reaching into printers; use tools to remove prints.
- Sharp tools: flush cutters and scrapers are the only sharp tools needed; store them when not in use.
- Small parts: backplates for the smallest parts fit in a choke-hazard size range; keep them away from young children.
- Wall mounting: follow `mounting-guide.md`; do not drill or pin anything without facilities approval.

## Facilitator checklist

- [ ] Kits sliced and verified with `tools/validate_slicer.py` before the session
- [ ] At least one printer pre-heated and loaded with translucent filament
- [ ] Coupons printed ahead of time as backup if a printer fails
- [ ] Legends printed per participant
- [ ] Demo wall or board for mounting practice
- [ ] Feedback sheet: fit results, confusing steps, missing parts

## Feedback to capture

- Chosen clearance per printer/material (add to the table in `fit-calibration.md`)
- Assembly confusion (which steps needed help)
- Print failures (which parts, which plate)
- Suggestions for the icon set or kit contents
