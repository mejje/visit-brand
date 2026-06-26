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

2. **Generated print files**
   - STL and/or 3MF files for each icon.
   - Single-session layouts for basic printers.
   - Multi-session larger parts for employee-owned printers.
   - Fit calibration coupons with snap tabs and sockets.

3. **Icon analysis software**
   - Import original SVGs.
   - Normalize geometry to a common coordinate system.
   - Convert filled SVG primitives into planar polygon geometry.
   - Generate candidate simplified part libraries.
   - Reconstruct every icon from the simplified library.
   - Export reconstructed SVGs.
   - Score deviation against the original SVGs.

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

### Current Shortlist

- **CadQuery**: Python-based parametric CAD. Its official documentation describes it as a Python library for parametric 3D CAD models and lists STEP, AMF, 3MF, and STL output support: <https://cadquery.readthedocs.io/>.
- **build123d**: Python-based parametric BREP modeling built on Open Cascade, with an expressive Python API suitable for 3D printing workflows: <https://build123d.readthedocs.io/>.
- **FreeCAD**: Open-source parametric modeler with Python support and a visual CAD environment. Good candidate for inspection, interchange, and manual validation: <https://github.com/FreeCAD/FreeCAD>.
- **OpenSCAD**: Free script-based solid CAD tool. Strong for approachable parametric models, but likely less comfortable for SVG-driven geometry optimization than a Python-first workflow: <https://openscad.org/>.

### Initial Recommendation

Start with a Python-first pipeline and prototype both **CadQuery** and **build123d** on one icon.

Reasoning:

- The SVG parsing, geometry simplification, scoring, and optimization will likely be Python anyway.
- A Python CAD library avoids passing fragile intermediate geometry between unrelated tools.
- Both CadQuery and build123d are built around parametric CAD-as-code, which fits the need to regenerate variants.
- FreeCAD can remain the visual QA and manual-inspection tool even if the production generator is code-first.

### CAD Research TODOs

- **RESEARCH TODO:** Prototype one backplate and one hollow front part in CadQuery.
- **RESEARCH TODO:** Prototype the same part in build123d.
- **RESEARCH TODO:** Compare SVG polygon import, offsetting, shelling, fillets/chamfers, assembly export, 3MF export, and CLI automation.
- **RESEARCH TODO:** Confirm whether exported 3MF files preserve multiple bodies/material groups in the slicers employees are likely to use.
- **RESEARCH TODO:** Decide the production CAD stack after prototype evidence, not preference.
- **RESEARCH TODO:** Decide whether to provide OpenSCAD exports for advanced hobbyists or keep the public source in Python only.

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
- Generated geometry should preserve the visual weight of the original icons.
- Reuse may allow translation and rotation of a part.
- Mirroring needs stakeholder approval, because mirrored asymmetry can feel off-brand.
- Scaling individual parts independently should be avoided unless approved, because it can erode brand consistency.

**RESEARCH TODO:** Confirm allowed transforms for reusable parts: translation only, translation + rotation, translation + rotation + mirroring, or limited scale classes.

### Analysis Pipeline

1. **SVG ingestion**
   - Parse all SVGs from `SVG/`.
   - Resolve style classes and fills.
   - Convert rectangles, polygons, and paths into filled planar geometry.
   - Flatten curves to polygons at a configurable precision.

2. **Normalization**
   - Normalize all icons to a shared unit system.
   - Remove irrelevant metadata.
   - Merge overlapping filled primitives per icon.
   - Preserve original primitive boundaries as optional hints.

3. **Candidate part generation**
   - Start with exact original primitives.
   - Split large polygons into reusable strokes, elbows, rectangles, diagonals, arcs, and end caps.
   - Cluster similar shapes by dimensions, angle, aspect ratio, and local boundary descriptors.
   - Generate simplified candidates using geometric approximation.
   - Reject candidates with unprintable minimum features.

4. **Reconstruction**
   - For each icon, solve a placement problem using the candidate part library.
   - Generate a reconstructed SVG from chosen parts.
   - Generate an assembly map for physical placement on the backplate.

5. **Scoring**
   - Compare reconstructed SVG against original SVG.
   - Compute area-weighted symmetric difference.
   - Compute boundary distance, such as Hausdorff or Chamfer distance.
   - Penalize missing salient corners and over-smoothed silhouettes.
   - Penalize excessive part count, excessive unique parts, fragile parts, and difficult assembly.

6. **Optimization**
   - Search across simplification levels and candidate libraries.
   - Produce a Pareto frontier: fewer parts versus greater visual deviation.
   - Choose a recommended library only after reviewing visual overlays with stakeholders.

### Optimizer Objective Draft

Minimize:

`total_score = visual_error_weight * visual_error + unique_part_weight * unique_part_count + instance_weight * placed_part_count + printability_weight * printability_penalty + assembly_weight * assembly_penalty`

Where:

- `visual_error` combines area difference and boundary distance.
- `unique_part_count` counts distinct printable part designs.
- `placed_part_count` counts how many pieces an employee must snap in.
- `printability_penalty` captures small features, thin sections, unsupported geometry, and weak snap features.
- `assembly_penalty` captures tiny parts, ambiguous orientations, and hard-to-place pieces.

**RESEARCH TODO:** Establish default weights through a design review using 3-5 generated candidate libraries.

## Proposed Software Architecture

Potential repository layout:

```text
SVG/
  Visit_Icon_*.svg
analysis/
  normalized/
  reconstructed/
  reports/
cad/
  parameters/
  generators/
  exports/
docs/
  maker-guide.md
  printer-setup.md
  assembly-guide.md
  workshop-guide.md
tools/
  analyze_icons.py
  generate_candidates.py
  optimize_part_library.py
  render_reconstruction.py
  compare_svg.py
  export_cad.py
```

Suggested Python libraries to evaluate:

- SVG parsing: `svgelements`, `svgpathtools`, or equivalent.
- Polygon geometry: `shapely`.
- Raster comparison: `cairosvg`, `Pillow`, `opencv-python`, or equivalent.
- Optimization: `scipy.optimize`, OR-Tools, simulated annealing, genetic algorithms, or custom Pareto search.
- CAD generation: CadQuery or build123d.

**RESEARCH TODO:** Validate exact library choices by building a small proof of concept against `Visit_Icon_Hotel.svg`, `Visit_Icon_Platform.svg`, and `Visit_Icon_Amusement park.svg`.

## Design Phase Milestones

### Milestone 1: Reference Geometry Baseline

- [ ] Parse every SVG.
- [ ] Export normalized reference SVGs.
- [ ] Generate raster previews for every icon.
- [ ] Document source geometry quirks.
- [ ] Decide curve-flattening tolerance for path-based icons.

### Milestone 2: First Physical Prototype

- [ ] Select provisional CAD stack.
- [ ] Generate one backplate and one translucent front icon from source geometry.
- [ ] Add editable extrusion-depth and wall-thickness parameters.
- [ ] Print snap-fit coupons.
- [ ] Print one complete small icon.
- [ ] Record printer, filament, nozzle, layer height, clearances, and fit outcome.

### Milestone 3: Simplified Part Library Prototype

- [ ] Generate exact primitive-based reconstruction for all icons.
- [ ] Generate first simplified candidate library.
- [ ] Export reconstructed SVGs.
- [ ] Score reference deviation.
- [ ] Create visual overlay report.

### Milestone 4: Optimization Loop

- [ ] Implement objective scoring.
- [ ] Run multiple optimization strategies.
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
- **Customization:** edit parameter file, regenerate STL/3MF, print larger versions.
- **Maker Workshop:** suggested agenda, shared printer workflow, group assembly session, safety notes.

**RESEARCH TODO:** Decide whether docs should assume a named slicer workflow or remain slicer-neutral.

## Risks And Unknowns

- Snap-fit tolerances vary heavily by printer, material, nozzle, temperature, and slicer settings.
- Translucent white filament may look too opaque unless wall thickness and infill are tuned.
- Hollow translucent parts may need drain/vent holes, support strategy, or minimum face thickness rules.
- Nails may be unsuitable for some cubicle walls or workplace policies.
- Simplifying icons into reusable parts may conflict with brand fidelity.
- A universal part set might reduce uniqueness but increase assembly burden.
- Very small pieces can become frustrating or unsafe to handle.
- Single-session print layouts may require compromises on maximum icon size.

## Immediate Next Steps

1. **RESEARCH TODO:** Pick three representative icons for prototype analysis: one rect-heavy, one polygon-heavy, and one path/curve icon.
2. **RESEARCH TODO:** Build a parsing proof of concept that renders normalized references and reports primitive geometry.
3. **RESEARCH TODO:** Prototype the CAD stack in CadQuery and build123d using one simple icon.
4. **RESEARCH TODO:** Design and print snap-fit tolerance coupons.
5. **RESEARCH TODO:** Define the first visual-deviation scoring method and generate reconstructed SVG overlays.
6. **RESEARCH TODO:** Review physical assumptions with facilities/brand/design before locking mounting and visual tolerance decisions.

