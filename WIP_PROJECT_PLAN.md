# WIP Project Plan: 3D-Printed Modular Brand Icons

Last updated: 2026-06-26

## Project Intent

Create a complete maker-friendly toolkit that lets employees 3D print, assemble, and display the new stylized brand icons on cubicle or desk walls.

The desired object is a two-layer physical icon:

- A backplate that can be fixed to a cubicle wall with nails, pins, or other approved fasteners.
- A raised front icon assembly that snaps into the backplate.
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
| `Visit_Icon_DestinationBuilding.svg` | 0 | 4 | 0 | Polygon-only |
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
| `Visit_Icon_VacationRental.svg` | 2 | 2 | 0 | Mixed rect/polygon |

## Success Criteria

- Employees can choose an icon, print a curated kit, and assemble it without CAD knowledge.
- Makers can edit a small parameter file and regenerate printable assets.
- The printable assets include backplates, snap-in front parts, and optional test coupons for fit calibration.
- The simplified reusable part set can reconstruct every source icon within a documented deviation threshold.
- Every simplified reconstruction can be rendered back to SVG and compared against the original reference SVG.
- The toolkit explains printer setup, material choices, orientation, slicing assumptions, assembly, wall mounting, and safety limitations.

## Key Design Questions

- **RESEARCH TODO:** Decide whether each icon gets its own backplate with sockets, or whether a universal backplate with all possible socket locations is realistic.
- **RESEARCH TODO:** Decide whether "one printed set can build any icon" means one physical superset of front parts plus icon-specific backplates, or one universal display system that can be reconfigured without reprinting the backplate.
- **RESEARCH TODO:** Validate cubicle-wall fastener assumptions. Nails may not be allowed or may not hold well in some office panel systems. Include alternatives such as push pins, removable adhesive strips, magnetic plates, or over-wall hooks if needed.
- **RESEARCH TODO:** Determine target icon sizes for the basic kit and larger kit, based on common consumer printer build plates.
- **RESEARCH TODO:** Determine acceptable brand deviation thresholds with design/brand stakeholders before optimizing part reduction.

## Proposed Toolkit Deliverables

1. **Parametric CAD source**
   - Scripted model definitions for backplates, front shells, snap features, test coupons, and export assemblies.
   - Parameter presets for small, medium, and large desk display sizes.

2. **Generated CAD and print handoff files**
   - STEP files for each icon, backplate, front assembly, and fit coupon.
   - Single-session layouts for basic printers.
   - Multi-session larger parts for employee-owned printers.
   - Fit calibration coupons with snap tabs and sockets.
   - No STL deliverables. Mesh conversion, if needed, should happen inside the user's slicer or a documented local slicer workflow.

3. **Icon analysis software**
   - Import original SVGs.
   - Normalize geometry to a common coordinate system.
   - Convert filled SVG primitives into planar polygon geometry.
   - Generate deterministic reference geometry files from the original SVGs.
   - Generate canonical reference SVGs from those geometry files.
   - Generate candidate simplified part libraries.
   - Reconstruct every icon from the simplified library.
   - Export reconstructed geometry, SVGs, and visual overlays.
   - Score deviation against the canonical reference geometry.

4. **Optimization software**
   - Search for the best trade-off between part count, visual deviation, printability, and assembly complexity.
   - Produce reports showing trade-off curves and visual overlays.

5. **Maker documentation**
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

### Initial Recommendation

Start with a Python-first pipeline and prototype both **CadQuery** and **build123d** on one icon, using STEP export as the deciding handoff test.

Reasoning:

- The SVG parsing, geometry simplification, scoring, and optimization will likely be Python anyway.
- A Python CAD library avoids passing fragile intermediate geometry between unrelated tools.
- Both CadQuery and build123d are built around parametric CAD-as-code, which fits the need to regenerate variants.
- STEP keeps generated geometry editable and inspectable in other CAD tools.
- FreeCAD can remain the visual QA and STEP round-trip inspection tool even if the production generator is code-first.

### CAD Research TODOs

Detailed implementation spike: `CAD_FEASIBILITY_SPIKE.md`

- **RESEARCH TODO:** Prototype one backplate and one hollow front part in CadQuery.
- **RESEARCH TODO:** Prototype the same part in build123d.
- **RESEARCH TODO:** Compare Shapely polygon import, offsetting, shelling, fillets/chamfers, STEP part export, STEP assembly export, STEP re-import, and CLI automation.
- **RESEARCH TODO:** Validate generated STEP files in **PrusaSlicer** as the only supported slicer workflow for the maker guide. PrusaSlicer is free/open-source, cross-platform, documents native STEP import, and includes/imports third-party printer profiles: <https://www.prusa3d.com/p/prusaslicer/>, <https://help.prusa3d.com/article/supported-file-formats_1772>, <https://help.prusa3d.com/article/profiles-for-3rd-party-printers_246178>.
- **RESEARCH TODO:** Confirm whether PrusaSlicer preserves separate STEP bodies/parts well enough for the employee workflow.
- **RESEARCH NOTE:** Do not use UltiMaker Cura as the supported slicer workflow unless native free STEP support is confirmed. Current UltiMaker documentation describes CAD file import through an UltiMaker Cura CAD plugin/subscription workflow, which is not acceptable for this project: <https://support.makerbot.com/s/article/1667412730014>.
- **RESEARCH TODO:** Decide the production CAD stack after prototype evidence, not preference.
- **RESEARCH TODO:** Document that non-STEP CAD exports are out of scope unless a future explicit requirement overrides the STEP-only decision.

## Parametric Model Requirements

Minimum parameters:

- `icon_size_mm`: final display size.
- `front_depth_mm`: distance the translucent icon protrudes from the wall.
- `front_shell_wall_mm`: translucent shell wall thickness.
- `front_face_thickness_mm`: visible front face thickness.
- `backplate_thickness_mm`: backplate body thickness.
- `backplate_margin_mm`: border around reconstructed icon geometry.
- `snap_clearance_mm`: clearance between snap male/female features.
- `snap_engagement_mm`: insertion depth.
- `snap_retention_lip_mm`: retention feature height.
- `minimum_feature_mm`: smallest printable generated feature.
- `nail_hole_diameter_mm`: fastener hole diameter.
- `nail_head_relief_mm`: countersink or relief diameter.
- `printer_nozzle_mm`: assumed nozzle size.
- `layer_height_mm`: assumed layer height.

Snap-fit concepts to test:

- Simple friction pegs into sockets.
- Dovetail slides.
- Cantilever snap tabs.
- Mushroom/keyhole studs.
- Swappable magnet pockets as an alternate premium variant.

**RESEARCH TODO:** Print tolerance coupons before committing to a snap design. Test at least three clearances per printer/material combination.

## Scientific Icon Part-Set Analysis

Goal: create a canonical physical part library that can reconstruct all source icons with a minimal number of unique parts while staying close to the original brand geometry.

### Working Assumptions

- Source SVGs are the design reference.
- Source SVGs should stay immutable and human-auditable; generated reference files should be recreated from them instead of hand-edited.
- Generated geometry should preserve the visual weight of the original icons.
- Reuse may allow translation and rotation of a part.
- Mirroring needs stakeholder approval, because mirrored asymmetry can feel off-brand.
- Scaling individual parts independently should be avoided unless approved, because it can erode brand consistency.

**RESEARCH TODO:** Confirm allowed transforms for reusable parts: translation only, translation + rotation, translation + rotation + mirroring, or limited scale classes.

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

**RESEARCH TODO:** Validate exact library choices by building a small proof of concept against `Visit_Icon_Hotel.svg`, `Visit_Icon_Platform.svg`, `Visit_Icon_Amusement park.svg`, and `Visit_Icon_Travel agent.svg`.

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
- [ ] Validate PrusaSlicer STEP import before any physical print.
- [ ] Print snap-fit coupons.
- [ ] Print one complete small icon.
- [ ] Record printer, filament, nozzle, layer height, clearances, and fit outcome.

### Milestone 3: Simplified Part Library Prototype

Tool: `tools/icon_parts.py` (bootstrap, render, score subcommands)

- [x] Generate exact primitive-based reconstruction for all icons as a parametric 2D part spec (61 unique parts, 83 instances).
- [x] Deduplicate identical shapes via canonical part signatures (rects by size, polygons by WKB hash).
- [x] Convert part specs into Shapely geometry for scoring (reconstruction from placed instances).
- [x] Export reconstructed SVGs and overlay reports (`analysis/runs/exact/svgs/`, `overlays/`).
- [x] Score reference deviation with Shapely: area error ~1e-17, Hausdorff 0.0, bounds delta 0.0 across all 14 icons.
- [x] Create visual overlay report (black reference + red dashed reconstruction per icon).

### Milestone 4: Optimization Loop

- [x] Implement objective scoring (area error, Hausdorff, bounds delta, component delta).
- [x] Run greedy/local simplification via `tools/icon_parts.py simplify`:
  - Rect size merging: saves 1 part (61→60), near-zero error.
  - Polygon Hausdorff merging: saves 12 parts (61→49), 0.05% error, worst icon 0.44%.
  - Polygon Hausdorff + rotation: saves 19 parts (61→42), 0.075% error, worst icon 0.78%.
  - Combined rect+polygon_rot: 41 parts at 0.076% error.
  - 6 rotation-aware cross-icon clusters found.
- [x] Log Pareto rows per candidate (`analysis/runs/simplify/pareto.jsonl`).
- [x] Allow rotation in part placements (centroid anchoring, 0/90/180/270 degree rotations).
- [ ] Pre-generate polygon decomposition candidates (grid-split, strip-split, inscribed-rect).
- [ ] Build pymoo NSGA-II pipeline: chromosome selects which candidate parts to include and which decomposition per instance. Objectives: minimize unique parts, placed instances, area error, worst-icon Hausdorff.
- [ ] Generate Pareto frontier reports.
- [ ] Review trade-offs with brand/design stakeholders.
- [ ] Select a recommended part library for physical testing.

### Milestone 5: Maker Toolkit

- [ ] Create small single-session print layouts.
- [ ] Create larger multi-session layouts.
- [ ] Write maker quick-start guide.
- [ ] Write print setup guide.
- [ ] Write assembly and wall-mounting guide.
- [ ] Package files by icon and by printer size.
- [ ] Pilot with internal employees or a maker-space group.

## Documentation Plan

Final documentation should be friendly, practical, and confidence-building.

Required docs:

- **Quick Start:** choose icon, download files, print, snap together, mount.
- **Printer Setup:** material, nozzle, bed adhesion, supports, infill, layer height, translucent filament guidance.
- **Fit Calibration:** print tolerance coupon, choose clearance preset, regenerate parts if needed.
- **Assembly:** identify parts, snap order, troubleshooting tight or loose fits.
- **Mounting:** nail/pin/adhesive options, cubicle-wall cautions, removal instructions.
- **Customization:** edit parameter file, regenerate STEP files, import them into the slicer, and print larger versions.
- **Maker Workshop:** suggested agenda, shared printer workflow, group assembly session, safety notes.

Supported slicer workflow: document **PrusaSlicer** only, using it as the public-printer baseline for native STEP import, printer profile selection, slicing, and troubleshooting.

## Risks And Unknowns

- Snap-fit tolerances vary heavily by printer, material, nozzle, temperature, and slicer settings.
- STEP import quality may vary by slicer; the project should validate PrusaSlicer before promising employee-friendly printing.
- Translucent white filament may look too opaque unless wall thickness and infill are tuned.
- Hollow translucent parts may need drain/vent holes, support strategy, or minimum face thickness rules.
- Nails may be unsuitable for some cubicle walls or workplace policies.
- Simplifying icons into reusable parts may conflict with brand fidelity.
- A universal part set might reduce uniqueness but increase assembly burden.
- Very small pieces can become frustrating or unsafe to handle.
- Single-session print layouts may require compromises on maximum icon size.

## Immediate Next Steps

Completed:
1. ~~Pick three representative icons for prototype analysis~~ → Four icons selected: Hotel (rect-heavy), Platform (polygon-only), Amusement Park (curved path), Travel Agent (transformed rect).
2. ~~Build `tools/icon_reference.py build`~~ → Done: 14 icons, WKB references, canonical SVGs, manifest, check/verify commands.
3. ~~Prototype STEP generation in CadQuery and build123d~~ → Done: build123d selected, `tools/export_step.py` working with zero re-import delta.
4. ~~Build comparison tool~~ → Done: `tools/icon_parts.py score` with area error, Hausdorff, bounds delta, component delta.
5. ~~Greedy simplification~~ → Done: 61→42 parts (31% reduction) at 0.075% area error via rect merge + polygon Hausdorff + rotation clustering.

Current priorities:
- **Polygon decomposition candidate generation**: grid-split, strip-split, inscribed-rect pre-processing.
- **pymoo NSGA-II**: chromosome selects from the pre-generated candidate pool; multi-objective Pareto search.
- **Physical prototype**: print snap-fit coupons, validate PrusaSlicer STEP import.
- **Design review** with facilities/brand/design before locking mounting and visual tolerance decisions.

