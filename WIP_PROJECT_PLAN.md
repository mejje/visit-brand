# WIP Project Plan: 3D-Printed Modular Brand Icons

Last updated: 2026-06-29

## Project Intent

Create a complete maker-friendly toolkit that lets employees 3D print, assemble, and display the new stylized brand icons on cubicle or desk walls.

The desired object is a paired fixture for each physical icon part:

- A small hidden backplate for each icon part that can be fixed to a cubicle wall with two small nails, pins, or other approved fasteners.
- Two holes per backplate so the backplate can be attached and oriented on the wall.
- A raised hollow front part that snaps over the matching small backplate.
- Front icon parts printed in translucent white, hollow or partially hollow, so they protrude from the wall and produce a dim see-through effect.
- Parameters for scale, wall thickness, extrusion depth, snap-fit tolerance, backplate thickness, nail-hole style, and icon-part shell thickness.

The project should support two printing modes:

- **Single-session basic-printer kit:** all necessary parts for a small desk-sized icon print together in one job on a typical consumer FDM printer.
- **Larger owner-printer kit:** larger icon components print in separate sessions, with optional higher-quality tolerances, alternate nozzle assumptions, and larger plate usage.

## Current Source Inventory

Source icons are in `SVG/`.

All inspected SVGs use a `48 x 48` viewBox and filled vector primitives. Most geometry is rectangles and polygons; one icon currently includes a curved path.

| SVG | Rects | Polygons | Paths | Notes |
| --- | ---: | ---: | ---: | --- |
| `Visit_Icon_Amusement park.svg` | 7 | 1 | 1 | Contains a curved path |
| `Visit_Icon_DestinationBuilding.svg` | 0 | 5 | 0 | Polygon-only; roof/top and left wall are split primitives |
| `Visit_Icon_Experiences.svg` | 0 | 5 | 0 | Polygon-only |
| `Visit_Icon_Ferry operator.svg` | 4 | 5 | 0 | Mixed rect/polygon |
| `Visit_Icon_Homeowner.svg` | 4 | 2 | 0 | Mixed rect/polygon |
| `Visit_Icon_Hospitality.svg` | 1 | 4 | 0 | Mixed rect/polygon |
| `Visit_Icon_Hotel.svg` | 5 | 2 | 0 | Mixed rect/polygon |
| `Visit_Icon_Platform.svg` | 0 | 8 | 0 | Polygon-only |
| `Visit_Icon_Resort.svg` | 2 | 3 | 0 | Mixed rect/polygon |
| `Visit_Icon_Ski resort.svg` | 1 | 5 | 0 | Mixed rect/polygon |
| `Visit_Icon_Solceller.svg` | 2 | 1 | 0 | Mixed rect/polygon |
| `Visit_Icon_Tour operator.svg` | 1 | 6 | 0 | Mixed rect/polygon |
| `Visit_Icon_Travel agent.svg` | 1 | 4 | 0 | Mixed rect/polygon |
| `Visit_Icon_VacationRental.svg` | 3 | 3 | 0 | Mixed rect/polygon; two roof pieces and right wall are split primitives |

## Success Criteria

- Employees can choose an icon, print a curated kit, and assemble it without CAD knowledge.
- Makers can edit a small parameter file and regenerate printable assets.
- The printable assets include one small two-hole backplate per physical icon part, snap-on hollow front caps, and optional test coupons for fit calibration.
- The simplified reusable part set can reconstruct every source icon within a documented deviation threshold.
- Every simplified reconstruction can be rendered back to SVG and compared against the original reference SVG.
- The toolkit explains printer setup, material choices, orientation, slicing assumptions, assembly, wall mounting, and safety limitations.

## Status Dashboard

| Workstream | Status | Current state |
| --- | --- | --- |
| Source SVG inventory | Done | 14 source SVGs inspected; all use a `48 x 48` viewBox. |
| Reference geometry pipeline | Done | `tools/icon_reference.py` generated references, canonical SVGs, overlays, source hashes, and stale checks. |
| Exact part-spec baseline | Done | `tools/icon_parts.py` generated exact reconstruction and near-zero-error scoring for all icons. |
| Simplified reusable part library | In Progress | Current recommended candidate is 41 unique parts at ~0.0799% overall area error after source roof/wall splits and 45-degree rotation reuse; stakeholder review still pending. |
| CAD stack | In Progress | `build123d` is the selected prototype stack with successful STEP export/re-import; slicer and physical validation still pending. |
| Plain universal front-piece STEP kit | Done | `analysis/runs/kits/recommended/universal-single-icon-kit.step`: 41 designs, 66 printed pieces, 4 plates. |
| Corrected per-part fixture STEP kit | Done | `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.step`: 41 designs, 66 hollow caps, 66 two-hole backplates, 8 plates. |
| Old peg/socket approach | Removed | The old generated artifacts and CLI paths were removed; current mechanical direction is hollow cap over per-part backplate. |
| Marking and SVG legend system | In Progress | Global part numbers now appear in manifests, the SVG/JSON legend, and the STEP geometry as shallow engraved CAD text; slicer visibility and print readability still need validation. |
| PrusaSlicer validation | Not Started | Must confirm STEP body handling and usability before promising the workflow. |
| Physical print validation | Not Started | No cap/backplate pair has been printed or handled yet. |
| Facilities/wall mounting validation | Blocked / External | Needs representative cubicle/wall material and approval of pins/nails/alternatives. |
| Maker documentation | Not Started | Quick start, slicer guide, assembly guide, and workshop guide remain to be written. |

## Remaining Work Summary

The project has working analysis, optimization, and STEP generation prototypes. What remains is mostly validation and productization:

- Validate STEP import and separate body handling in PrusaSlicer.
- Validate the generated global part-number legend workflow and the shallow engraved STEP marks in slicer and physical prints.
- Print and test representative hollow-cap/backplate pairs, then tune clearances and hole sizes.
- Confirm wall/cubicle mounting rules and approved fastener options.
- Run brand/design review on the 41-part simplified library and visual deviation.
- Package final print layouts by icon/printer size and write the maker documentation.
- Pilot the workflow with employees or a maker-space group.

## Key Design Questions

- **DECISION:** Do not use a full-icon backplate. Generate one small backplate per physical icon part.
- **DECISION:** Each small backplate has two holes for wall attachment and orientation. The hollow front part snaps over this backplate.
- **DECISION:** The current universal fixture kit is a single-icon universal set: it includes every unique part design and the maximum quantities needed to build any one icon, not all icons simultaneously.
- **DECISION:** Employee-facing markings should use global part numbers only. Duplicate copies of the same part design share the same number.
- **BLOCKED / EXTERNAL:** Validate cubicle-wall fastener assumptions. Nails may not be allowed or may not hold well in some office panel systems. Include alternatives such as push pins, removable adhesive strips, magnetic plates, or over-wall hooks if needed.
- **IN PROGRESS:** Determine target icon sizes for the basic kit and larger kit. Current prototype size is `120 mm` on a `180 x 180 mm` bed; final size presets are not locked.
- **BLOCKED / EXTERNAL:** Determine acceptable brand deviation thresholds with design/brand stakeholders before locking the part library.

## Proposed Toolkit Deliverables

1. **Parametric CAD source** — **In Progress**
   - Scripted model definitions for hollow front caps, per-part two-hole backplates, press-fit features, test coupons, and export assemblies.
   - Parameter presets for small, medium, and large desk display sizes.

2. **Generated CAD and print handoff files** — **In Progress**
   - STEP files for each icon kit, hollow front cap set, per-part backplate set, and fit coupon.
   - Single-session layouts for basic printers.
   - Multi-session larger parts for employee-owned printers.
   - Fit calibration coupons for cap/backplate clearance and mounting-hole usability.
   - No STL deliverables. Mesh conversion, if needed, should happen inside the user's slicer or a documented local slicer workflow.

3. **Icon analysis software** — **Mostly Done**
   - Import original SVGs.
   - Normalize geometry to a common coordinate system.
   - Convert filled SVG primitives into planar polygon geometry.
   - Generate deterministic reference geometry files from the original SVGs.
   - Generate canonical reference SVGs from those geometry files.
   - Generate candidate simplified part libraries.
   - Reconstruct every icon from the simplified library.
   - Export reconstructed geometry, SVGs, and visual overlays.
   - Score deviation against the canonical reference geometry.

4. **Optimization software** — **In Progress**
   - Search for the best trade-off between part count, visual deviation, printability, and assembly complexity.
   - Produce reports showing trade-off curves and visual overlays.

5. **Maker documentation** — **Not Started**
   - Quick-start guide.
   - Printer/material guide.
   - Assembly guide.
   - Troubleshooting guide for snap fits.
   - Optional maker-space workshop script.

## CAD And Modeling Software Plan

The modeling workflow should be scriptable and parametric, because the project needs repeatable generation from SVG data and easy tuning of tolerances.

The generated CAD handoff format should be **STEP only**. STEP is the canonical interchange format for CAD review, downstream CAD editing, slicer import where supported, and archival generated geometry. STL should not be generated or shipped as a project deliverable.

### Current Shortlist

- **CadQuery**: Python-based parametric CAD. Strong candidate if it can reliably turn Shapely-derived profiles into solids and export clean STEP parts/assemblies. Its documentation covers STEP import/export and assembly export: <https://cadquery.readthedocs.io/en/latest/importexport.html>.
- **build123d**: Python-based parametric BREP modeling built on Open Cascade. Strong candidate if its sketch/profile workflow maps cleanly from Shapely polygons and exports clean STEP parts/assemblies. Its documentation covers `import_step` and `export_step`: <https://build123d.readthedocs.io/en/latest/import_export.html>.
- **FreeCAD**: Open-source parametric modeler with Python support and a visual CAD environment. Good candidate for STEP inspection, interchange validation, and manual QA: <https://wiki.freecad.org/Import_Export_Preferences>.
- **OpenSCAD**: De-prioritized for production unless a reliable STEP/BREP path is proven, because the project now requires STEP as the generated handoff format.

### Current CAD Direction

Use a Python-first pipeline with **build123d** as the active prototype CAD stack. It has successfully exported and re-imported front pieces, laid-out front-piece kits, and corrected hollow-cap/backplate fixture kits as STEP.

Reasoning:

- The SVG parsing, geometry simplification, scoring, and optimization will likely be Python anyway.
- A Python CAD library avoids passing fragile intermediate geometry between unrelated tools.
- build123d is built around parametric CAD-as-code, which fits the need to regenerate variants from the part spec.
- STEP keeps generated geometry editable and inspectable in other CAD tools.
- FreeCAD can remain the visual QA and STEP round-trip inspection tool even if the production generator is code-first.

### CAD Research TODOs

Detailed implementation spike: `CAD_FEASIBILITY_SPIKE.md`

- **DEFERRED:** Prototype one backplate and one hollow front part in CadQuery. Not needed unless build123d fails slicer or physical validation.
- **DONE:** Prototype the same part in build123d. Front pieces, universal kits, and hollow-cap/backplate fixture kits export and re-import as STEP.
- **IN PROGRESS:** Compare Shapely polygon import, offsetting, shelling, fillets/chamfers, STEP part export, STEP assembly export, STEP re-import, and CLI automation. build123d is proven enough for current prototypes; slicer behavior and physical fit remain open.
- **NOT STARTED:** Validate generated STEP files in **PrusaSlicer** as the only supported slicer workflow for the maker guide. PrusaSlicer is free/open-source, cross-platform, documents native STEP import, and includes/imports third-party printer profiles: <https://www.prusa3d.com/p/prusaslicer/>, <https://help.prusa3d.com/article/supported-file-formats_1772>, <https://help.prusa3d.com/article/profiles-for-3rd-party-printers_246178>.
- **NOT STARTED:** Confirm whether PrusaSlicer preserves separate STEP bodies/parts well enough for the employee workflow.
- **RESEARCH NOTE:** Do not use UltiMaker Cura as the supported slicer workflow unless native free STEP support is confirmed. Current UltiMaker documentation describes CAD file import through an UltiMaker Cura CAD plugin/subscription workflow, which is not acceptable for this project: <https://support.makerbot.com/s/article/1667412730014>.
- **IN PROGRESS:** Decide the production CAD stack after prototype evidence, not preference. build123d is the provisional winner, pending slicer and physical validation.
- **DONE:** Document that non-STEP CAD exports are out of scope unless a future explicit requirement overrides the STEP-only decision.
- Snap-fit implementation spike: `SNAPFIT_DESIGN_PLAN.md`.

## Parametric Model Requirements

Minimum parameters:

- `icon_size_mm`: final display size.
- `front_depth_mm`: distance the translucent icon protrudes from the wall.
- `front_shell_wall_mm`: translucent shell wall thickness.
- `front_face_thickness_mm`: visible front face thickness.
- `backplate_thickness_mm`: per-part hidden backplate body thickness.
- `fit_clearance_mm`: XY clearance between the hidden backplate and the hollow front cap cavity.
- `z_clearance_mm`: depth clearance between the backplate and inside face of the cap.
- `pin_hole_diameter_mm`: two-hole mounting diameter for each small backplate.
- `pin_hole_edge_clearance_mm`: minimum material around each mounting hole.
- `snap_engagement_mm`: insertion depth.
- `snap_retention_lip_mm`: retention feature height.
- `minimum_feature_mm`: smallest printable generated feature.
- `nail_head_relief_mm`: countersink or relief diameter.
- `printer_nozzle_mm`: assumed nozzle size.
- `layer_height_mm`: assumed layer height.

Snap-fit concepts to test:

- Hollow cap press fit over a smaller two-hole backplate. Current first-pass implementation uses `1.0 mm` cap walls, `1.2 mm` face thickness, a `3.0 mm` backplate, and `0.25 mm` XY fit clearance.
- Dovetail slides.
- Cantilever snap tabs.
- Mushroom/keyhole studs.
- Swappable magnet pockets as an alternate premium variant.

**NOT STARTED:** Print cap/backplate fit coupons before committing to the press-fit clearance. Test at least three XY clearances per printer/material combination.

## Scientific Icon Part-Set Analysis

Goal: create a canonical physical part library that can reconstruct all source icons with a minimal number of unique parts while staying close to the original brand geometry.

### Working Assumptions

- Source SVGs are the design reference.
- Source SVGs should stay immutable and human-auditable; generated reference files should be recreated from them instead of hand-edited.
- Generated geometry should preserve the visual weight of the original icons.
- Reuse may allow translation and rotation of a part.
- Mirroring needs stakeholder approval, because mirrored asymmetry can feel off-brand.
- Scaling individual parts independently should be avoided unless approved, because it can erode brand consistency.

**DONE / WORKING DECISION:** Reusable parts may use translation plus 45-degree-increment rotation with centroid anchoring. Mirroring and independent scaling remain disallowed until brand stakeholders approve them.

### Detailed Plans

- Reference generation and rendering: `REFERENCE_RENDERING_PLAN.md`.
- Part-library analysis, Shapely scoring, and optimizer workflow: `ICON_ANALYSIS_PLAN.md`.

### Settled Technical Direction

- Raw SVGs remain immutable brand/design references.
- Generated reference artifacts are recreated from SVGs and not hand-edited.
- Shapely is the primary geometry comparison kernel.
- A project-native parametric 2D part spec is the editable optimizer format.
- CadQuery or build123d should consume the same part spec for downstream STEP generation.

### Current Source Summary

- Every inspected SVG uses `viewBox="0 0 48 48"`.
- The set is mostly filled rect/polygon geometry.
- `Visit_Icon_Amusement park.svg` contains the only curved path found so far.
- `Visit_Icon_Travel agent.svg` contains a transformed rotated rectangle.

### High-Level Analysis Pipeline

1. Generate canonical reference artifacts from the raw SVGs.
2. Generate an exact parametric part-spec baseline.
3. Search for reusable simplified part libraries.
4. Reconstruct each icon from candidate parts.
5. Score candidates against references with Shapely.
6. Review overlays and select candidates for physical prototyping.

Detailed scoring metrics and optimizer objectives live in `ICON_ANALYSIS_PLAN.md`.

## Proposed Software Architecture

Potential repository layout:

```text
SVG/
  Visit_Icon_*.svg
analysis/
  references/
    manifest.json
    *.reference.json
    *.canonical.svg
  runs/
    exact/
      part-spec.exact.v1.json
      svgs/
        *.reconstructed.svg
      overlays/
        *.overlay.svg
      metrics.json
  reconstructed/
  reports/
cad/
  parameters/
  generators/
  exports/
    step/
docs/
  maker-guide.md
  printer-setup.md
  assembly-guide.md
  workshop-guide.md
tools/
  icon_reference.py
  icon_parts.py          # bootstrap, render, score subcommands
  export_step.py
  generate_candidates.py
  optimize_part_library.py
```

Suggested Python libraries to evaluate:

- SVG parsing and transforms: `svgelements`.
- Polygon geometry: `shapely`.
- SVG rendering: generated directly from Shapely geometry.
- Optimization: custom Pareto evaluator first, `pymoo` NSGA-II for multi-objective search, OR-Tools CP-SAT for finite discrete subproblems, and `scipy.optimize` for continuous tuning.
- CAD generation: CadQuery or build123d, selected by STEP export/re-import quality.

**DONE FOR CURRENT PROTOTYPE:** Library choices are validated enough to continue: `svgelements`, `shapely`, `pymoo`, and `build123d` are all in use. Revisit only if slicer validation or physical testing exposes a tool limitation.

## Design Phase Milestones

### Milestone 1: Reference Geometry Baseline

Detailed implementation plan: `REFERENCE_RENDERING_PLAN.md`

Tool: `tools/icon_reference.py` (build, check, verify, render subcommands)

- [x] Parse every SVG (14 icons).
- [x] Resolve style classes, fills, `viewBox`, and transforms.
- [x] Export generated `*.reference.json` files with source hashes, parser settings, metrics, and Shapely-compatible geometry snapshots.
- [x] Export normalized reference SVGs generated from reference geometry.
- [x] Generate canonical SVGs and overlay templates for every icon.
- [x] Add `manifest.json` with source hashes, generator versions, precision, and curve tolerance.
- [x] Add a stale-reference check command for CI.
- [x] Document source geometry quirks.
- [x] Decide curve-flattening tolerance for path-based icons (0.02 SVG units).

### Milestone 2: First Physical Prototype

- [x] Select provisional CAD stack (build123d over CadQuery, based on STEP re-import quality).
- [x] Generate one STEP front icon from source geometry (`tools/export_step.py`).
- [x] Validate STEP re-import with zero volume delta.
- [x] Add editable extrusion-depth and wall-thickness parameters.
- [x] Generate an initial laid-out STEP kit from the selected part spec (`tools/export_step.py kit`).
  - Current universal single-icon kit: 41 unique part designs, 66 printed pieces, 4 plates at 120 mm icon size on a 180 x 180 mm bed.
  - Output: `analysis/runs/kits/recommended/universal-single-icon-kit.step` plus per-plate STEP files and manifest.
- [x] Generate first corrected per-part fixture STEP artifact.
  - `tools/export_step.py part-fixture-kit` creates hollow front caps plus one small two-hole backplate per physical icon part.
  - Current Platform fixture: 1 unique part design, 8 hollow front caps, 8 backplates, 16 total printed pieces, 1 plate, STEP re-import delta `0.000000001 mm^3`.
  - Current test output: `analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Platform.fixture-kit.step`.
  - Universal single-icon fixture STEP: 41 unique part designs, 66 hollow front caps, 66 backplates, 132 total printed pieces, 8 plates, STEP re-import delta `0.000000500 mm^3`.
- [ ] **Not Started:** Validate PrusaSlicer STEP import before any physical print.
- [x] Implement first-pass part marking and assembly legend system before broad physical testing.
  - Each unique part design now gets a stable global part number.
  - Duplicate copies of the same part design share the same number; for example Amusement park uses `1, 2, 3, 3, 3, 3, 3, 3, 3`.
  - Fixture manifests carry the part numbers and still retain internal front/backplate copy IDs for traceability.
  - Generated all-icons legend: `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-legend.svg`.
  - Generated machine-readable legend map: `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-legend.json`.
- [x] Add physical engraved number geometry to STEP pieces.
  - `tools/export_step.py` now engraves shallow `0.25 mm` global part numbers into plain front pieces, hollow cap inside faces, and backplate cap-facing faces by default.
  - Use `--no-physical-marks` for clean STEP exports if the physical print review rejects visible/engraved numbers.
  - Several backplates are only `7.5 mm` across, so print readability still needs physical validation.
- [ ] **Not Started:** Print one or two representative hollow-cap/backplate pairs.
- [ ] **Not Started:** Print one complete small icon from the corrected per-part fixture kit.
- [ ] **Not Started:** Record printer, filament, nozzle, layer height, clearances, and fit outcome.

### Milestone 3: Simplified Part Library Prototype

Tool: `tools/icon_parts.py` (bootstrap, render, score subcommands)

- [x] Generate exact primitive-based reconstruction for all icons as a parametric 2D part spec (64 unique parts, 86 instances).
- [x] Deduplicate identical shapes via canonical part signatures (rects by size, polygons by WKB hash).
- [x] Convert part specs into Shapely geometry for scoring (reconstruction from placed instances).
- [x] Export reconstructed SVGs and overlay reports (`analysis/runs/exact/svgs/`, `overlays/`).
- [x] Score reference deviation with Shapely: area error ~1e-17, Hausdorff 0.0, bounds delta 0.0 across all 14 icons.
- [x] Create visual overlay report (black reference + red dashed reconstruction per icon).

### Milestone 4: Optimization Loop

- [x] Implement objective scoring (area error, Hausdorff, bounds delta, component delta).
- [x] Run greedy/local simplification via `tools/icon_parts.py simplify`:
  - Rect size merging: saves 1 part (64→63), near-zero error.
  - Polygon Hausdorff merging: saves 12 parts (64→52), 0.05% error, worst icon 0.44%.
  - Polygon Hausdorff + rotation: saves 21 parts (64→43), 0.0785% error, worst icon 0.78%.
  - Combined rect+polygon_rot: 41 parts at 0.0799% error.
  - 8 rotation-aware cross-icon clusters found.
- [x] Log Pareto rows per candidate (`analysis/runs/simplify/pareto.jsonl`).
- [x] Allow rotation in part placements (centroid anchoring, 45-degree increments).
- [x] Pre-generate conservative polygon decomposition candidates with `tools/icon_decompose.py`.
  - Axis-aligned grid-split and largest-inscribed-rect strategies were attempted and abandoned because they distorted irregular icon polygons.
  - Current triangulated candidate preserves geometry nearly exactly: 160 unique parts, 195 instances, area error ~3.5e-12, Hausdorff ~0.
  - It is a candidate-pool feeder, not a recommended kit: the existing 41-part greedy Hausdorff result is still the best practical result.
- [x] Add cached/bounded optimizer search for decomposition candidate pools.
  - `tools/optimize_parts.py` now supports decision-score caching, persistent cache files, bounded cluster selection, exhaustive subset search, and reproducible run metadata.
  - `analysis/runs/decompose/nsga2_top8/` is the current bounded exhaustive test loop for the triangulated pool.
- [ ] **In Progress:** Generate broader Pareto frontier reports from improved candidate-selection/search loops.
- [ ] **Blocked / External:** Review trade-offs with brand/design stakeholders.
- [x] Select a provisional recommended part library for physical testing.
  - Current candidate: `analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json` (41 unique parts, 86 placed instances, ~0.0799% overall area error).
  - This can change after design review, but it is good enough to drive the first STEP kit export and slicer validation.

### Milestone 5: Maker Toolkit

- [ ] **In Progress:** Create small single-session print layouts. Prototype universal layouts exist; final employee-ready packaging is not done.
- [ ] **Not Started:** Create larger multi-session layouts.
- [x] Generate all-icons SVG assembly legend with global part-number callouts.
- [x] Add physical piece marking scheme for front caps and matching backplates.
  - Global part numbers exist in manifests and legend JSON/SVG.
  - STEP files now contain shallow engraved CAD text, not only STEP body labels.
  - Printability and readability remain open validation items.
- [ ] **Not Started:** Write maker quick-start guide.
- [ ] **Not Started:** Write print setup guide.
- [ ] **Not Started:** Write assembly and wall-mounting guide.
- [ ] **Not Started:** Package files by icon and by printer size.
- [ ] **Not Started:** Pilot with internal employees or a maker-space group.

## Documentation Plan

Final documentation should be friendly, practical, and confidence-building.

Required docs:

- **Not Started - Quick Start:** choose icon, download files, print, snap together, mount.
- **Not Started - Printer Setup:** material, nozzle, bed adhesion, supports, infill, layer height, translucent filament guidance.
- **Not Started - Fit Calibration:** print cap/backplate clearance coupon, choose clearance preset, regenerate parts if needed.
- **Not Started - Assembly:** identify indexed parts, match front caps to backplates, use the SVG legend for placement/orientation, snap order, troubleshooting tight or loose fits.
- **Blocked / External - Mounting:** nail/pin/adhesive options, cubicle-wall cautions, removal instructions. Needs facilities/material validation.
- **Not Started - Customization:** edit parameter file, regenerate STEP files, import them into the slicer, and print larger versions.
- **Not Started - Maker Workshop:** suggested agenda, shared printer workflow, group assembly session, safety notes.

Supported slicer workflow: document **PrusaSlicer** only, using it as the public-printer baseline for native STEP import, printer profile selection, slicing, and troubleshooting.

## Risks And Unknowns

- Snap-fit tolerances vary heavily by printer, material, nozzle, temperature, and slicer settings.
- STEP import quality may vary by slicer; the project should validate PrusaSlicer before promising employee-friendly printing.
- Translucent white filament may look too opaque unless wall thickness and infill are tuned.
- Hollow translucent parts may need drain/vent holes, support strategy, or minimum face thickness rules.
- Per-part backplates must leave enough material for two mounting holes without weakening small icon parts.
- Nails may be unsuitable for some cubicle walls or workplace policies.
- Simplifying icons into reusable parts may conflict with brand fidelity.
- A universal part set might reduce uniqueness but increase assembly burden.
- Very small pieces can become frustrating or unsafe to handle.
- Without visible legends and hidden physical markings, employees may not know which part belongs where or how to orient it.
- Single-session print layouts may require compromises on maximum icon size.

## Immediate Next Steps

Completed:
1. ~~Pick three representative icons for prototype analysis~~ → Four icons selected: Hotel (rect-heavy), Platform (polygon-only), Amusement Park (curved path), Travel Agent (transformed rect).
2. ~~Build `tools/icon_reference.py build`~~ → Done: 14 icons, WKB references, canonical SVGs, manifest, check/verify commands.
3. ~~Prototype STEP generation in CadQuery and build123d~~ → Done: build123d selected, `tools/export_step.py` working with zero re-import delta.
4. ~~Build comparison tool~~ → Done: `tools/icon_parts.py score` with area error, Hausdorff, bounds delta, component delta.
5. ~~Greedy simplification~~ → Done: 64→41 parts (36% reduction) at 0.080% area error via rect merge + polygon Hausdorff + 45-degree rotation clustering.

Current priorities:
- **Corrected fixture validation**: print one or two Platform hollow-cap/backplate pairs from `analysis/runs/snapfit/part-backplate-v1/`, test wall pin holes, and evaluate the `0.25 mm` cap fit clearance.
- **Marking and legend validation**: review the generated all-icons SVG legend, confirm global part numbers are understandable, and validate whether the shallow engraved STEP numbers remain readable on small printed parts.
- **Source primitive split validation**: DestinationBuilding roof/top vs left wall, plus VacationRental two roof pieces and right wall, are now split at the source SVG primitive level. Review the updated legend and reconstructed SVGs visually before locking the physical part library.
- **Rotation policy validation**: Done for the current baseline. Platform now uses one global part number because `tools/icon_parts.py simplify` defaults to 45-degree rotation increments; `--rotation-angles` remains available for future experiments.
- **Fixture kit expansion**: run `tools/export_step.py part-fixture-kit` for additional representative icons after the Platform pair validates.
- **Slicer validation**: open generated STEP files in PrusaSlicer, checking native import and separate body handling.
- **Design review** with facilities/brand/design before locking mounting and visual tolerance decisions.

