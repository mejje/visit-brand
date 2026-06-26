# Icon Analysis Plan

Last updated: 2026-06-27

## Goal

Design the analysis and optimization workflow that converts the icon references into a reusable physical part library while preserving brand fidelity.

This plan covers:

- the editable part-library format,
- reconstruction from parts,
- Shapely-based deviation scoring,
- optimizer objectives,
- visual review outputs.

Reference artifact generation from source SVGs is covered separately in `REFERENCE_RENDERING_PLAN.md`.

## Settled Technical Direction

Use Shapely as the primary comparison kernel, but do not make Shapely serialization or raw SVG the authoring format.

Recommended roles:

- **Raw SVG:** immutable brand/design reference.
- **Generated reference artifacts:** reproducible source-to-geometry snapshots, canonical SVGs, previews, overlays, metrics, and manifests.
- **Parametric 2D part spec:** editable project-native format for reusable physical parts, placements, transforms, and optimizer output.
- **Shapely geometry:** in-memory scoring representation generated from both the source references and the parametric part spec.
- **CadQuery/build123d:** downstream CAD generation from the same parametric 2D part spec.

This makes Shapely the geometry judge, not the design language. The optimizer should iterate on part definitions and placements, then convert each candidate to Shapely geometry for scoring and to CAD sketches/wires for printing.

## Parametric 2D Part Spec

The editable optimization format should describe reusable parts and icon assemblies directly:

```yaml
schema: visit.icon-parts.v1
units: svg_user_units
coordinate_system: svg_y_down
allowed_transforms:
  translate: true
  rotate: true
  mirror: false
  scale: false

parts:
  window_4x6:
    kind: rect
    size: [4, 6]
    anchor: top_left
    print:
      min_feature: 4

  diagonal_bar_4w:
    kind: bar
    length: 26.87
    width: 4
    cap: square
    anchor: center

icons:
  Visit_Icon_Hotel:
    instances:
      - part: window_4x6
        at: [17, 13]
      - part: window_4x6
        at: [27, 13]
```

The spec should preserve CAD-relevant intent that polygon files lose:

- logical part IDs,
- primitive type, such as `rect`, `bar`, `polygon`, `arc_band`, or `custom_polygon`,
- dimensions in source units,
- placement transforms,
- transform permissions,
- printability metadata,
- snap/socket hints,
- optional source primitive references for traceability.

Generated candidate files may also include derived polygon outlines, but those outlines should be treated as caches, not hand-edited source.

## Why Not Raw SVG Or Polygon JSON For Iteration

Raw SVG is too flexible for reliable shape comparison and optimization:

- Visually identical geometry can be written with different element types, path commands, relative or absolute coordinates, whitespace, transform placement, precision, or path shorthand.
- SVG paths can include implicit commands and multiple equivalent curve/path spellings.
- `viewBox` and element transforms change the effective coordinate system, so comparing XML text or path strings can miss real geometric sameness.
- SVG cleanup tools are useful for deterministic export, but they optimize SVG syntax rather than provide a stable physical-geometry contract.

Plain polygon JSON is also incomplete as an authoring format:

- It loses whether a shape was intended as a rectangle, bar, arc band, or reusable physical part.
- It does not naturally capture allowed transforms, snap hints, printability constraints, or assembly intent.
- It can be converted into CAD profiles, but it is less useful for generating clean parametric CAD than a part spec with dimensions and transforms.

Canonical SVG and polygon/WKB/WKT geometry are still useful, but only as generated artifacts for scoring, review, and regression tests.

## Analysis Pipeline

1. **Load references**
   - Read generated reference artifacts from `analysis/references/`.
   - Load Shapely geometry snapshots.
   - Load optional primitive hints once they exist.

2. **Generate exact baseline**
   - Create a first parametric 2D part spec that reconstructs every icon from source primitives.
   - Treat this as the zero-simplification baseline.
   - Score it against the canonical references to validate the pipeline.

3. **Generate candidate part libraries**
   - Split large polygons into reusable strokes, elbows, rectangles, diagonals, arcs, and end caps.
   - Cluster similar shapes by dimensions, angle, aspect ratio, and local boundary descriptors.
   - Generate simplified candidates using geometric approximation.
   - Reject candidates with unprintable minimum features.

4. **Reconstruct icons**
   - For each icon, solve a placement problem using the candidate part library.
   - Generate reconstructed Shapely geometry from chosen parts.
   - Generate reconstructed SVGs and overlay reports.
   - Generate an assembly map for physical placement on the backplate.

5. **Score deviation**
   - Compare reconstructed geometry against canonical reference geometry with Shapely.
   - Compute area-weighted symmetric difference.
   - Compute boundary distance, such as Hausdorff or Chamfer-like sampled distance.
   - Generate raster overlays for human review, but do not make raster comparison the primary metric.
   - Penalize excessive part count, excessive unique parts, fragile parts, and difficult assembly.

6. **Optimize**
   - Search across simplification levels and candidate libraries.
   - Produce a Pareto frontier: fewer parts versus greater visual deviation.
   - Choose a recommended library only after reviewing visual overlays with stakeholders.

## Scoring Draft

Initial visual-error metrics:

- `area_error = reference.symmetric_difference(candidate).area / reference.area`
- `hausdorff_distance = reference.boundary.hausdorff_distance(candidate.boundary)`
- optional Chamfer-like sampled boundary distance
- component count delta
- hole count delta
- bounds delta

Draft objective:

```text
total_score =
  visual_error_weight * visual_error
  + unique_part_weight * unique_part_count
  + instance_weight * placed_part_count
  + printability_weight * printability_penalty
  + assembly_weight * assembly_penalty
```

Where:

- `visual_error` combines area difference and boundary distance.
- `unique_part_count` counts distinct printable part designs.
- `placed_part_count` counts how many pieces an employee must snap in.
- `printability_penalty` captures small features, thin sections, unsupported geometry, and weak snap features.
- `assembly_penalty` captures tiny parts, ambiguous orientations, and hard-to-place pieces.

Default weights should be established through a design review using 3-5 generated candidate libraries.

## Optimizer Software Recommendation

The optimization problem has two different layers:

- **Discrete structure:** which unique parts exist, which icons use which part instances, and which transforms are allowed.
- **Geometric scoring:** how close a reconstructed icon is to the reference after Shapely computes area and boundary deviation.

Because the Shapely score is effectively a black-box evaluation, start with search methods that can optimize without gradients or a linear model.

Recommended progression:

1. **Custom Pareto search baseline**
   - Implement a deterministic evaluator that can score one candidate part library and report a Pareto row.
   - Add simple enumerations, greedy merges, and local mutations before adding a heavier optimizer.
   - Keep every evaluated candidate in a run database or JSONL file so experiments are reproducible.

2. **pymoo NSGA-II for first real multi-objective search**
   - Use `pymoo` when the candidate representation is stable enough for evolutionary search.
   - Optimize multiple objectives directly instead of collapsing everything into one weighted score too early:
     - minimize visual error,
     - minimize unique part count,
     - minimize placed part count,
     - minimize printability penalty,
     - minimize assembly penalty.
   - NSGA-II is a good fit because the project explicitly wants a Pareto frontier rather than one single answer.

3. **OR-Tools CP-SAT for exact discrete placement or set-cover subproblems**
   - Use OR-Tools once candidate parts and allowed placements are finite.
   - Good targets:
     - choose the smallest part library under a maximum visual-error threshold,
     - choose placements from a precomputed candidate set,
     - enforce transform, mirroring, size-class, or per-icon part-count constraints.
   - CP-SAT requires integer constraints, so Shapely-derived errors should be precomputed and scaled to integers when used in the model.

4. **SciPy only for continuous parameter tuning**
   - Use `scipy.optimize` for tuning continuous values such as part dimensions, curve flattening tolerance, simplification thresholds, or scoring weights.
   - `scipy.optimize.differential_evolution` can handle black-box global optimization and supports integer-constrained variables, but it is not the best first tool for the whole part-library combinatorial search.

5. **DEAP only if custom genetic operators become central**
   - DEAP is useful when the project needs custom evolutionary operators and very explicit control over chromosome structure.
   - Prefer `pymoo` first for Pareto-front optimization because multi-objective workflows are central to this project.

Initial recommendation:

```text
Phase 1: custom deterministic evaluator + greedy/local search
Phase 2: pymoo NSGA-II for Pareto search
Phase 3: OR-Tools CP-SAT for finite discrete subproblems
Phase 4: SciPy for continuous tuning only where useful
```

Do not start by hand-writing a full genetic algorithm. First make candidate scoring, caching, visualization, and reproducibility solid; then plug in the optimizer.

### Optimizer Research Notes

- `pymoo` provides multi-objective optimization algorithms, including NSGA-II, and supports Pareto-front workflows: <https://pymoo.org/> and <https://pymoo.org/algorithms/moo/nsga2.html>.
- Google OR-Tools CP-SAT is designed for integer programming and constraint-programming problems; constraints must be integer-defined: <https://developers.google.com/optimization/cp/cp_solver>.
- SciPy `optimize` includes local and global optimization tools, and `differential_evolution` supports black-box global search with integrality constraints: <https://docs.scipy.org/doc/scipy/reference/optimize.html> and <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html>.
- DEAP is a flexible evolutionary-computation framework for custom genetic algorithms and operators: <https://deap.readthedocs.io/>.

## First Implementation Slice

Start after the reference-rendering pipeline can generate four representative reference artifacts:

- `Visit_Icon_Hotel.svg`: rect-heavy.
- `Visit_Icon_Platform.svg`: polygon-only.
- `Visit_Icon_Amusement park.svg`: curved path.
- `Visit_Icon_Travel agent.svg`: transformed rotated rectangle.

Done means:

- An exact primitive-based parametric part spec exists for the four icons.
- The part spec can be converted into Shapely geometry.
- The Shapely comparison script reports area error, boundary distance, bounds delta, and component counts.
- The script emits reconstructed SVGs and visual overlays.

## Open Decisions

- Confirm allowed transforms for reusable parts: translation only, translation + rotation, translation + rotation + mirroring, or limited scale classes.
- Decide whether mirroring is allowed for any part family.
- Decide whether individual part scaling is prohibited entirely or allowed only through approved size classes.
- Decide first-pass scoring weights.
- Decide when to add printability penalties versus keeping the first score purely visual.
- Decide the first stable candidate encoding for `pymoo`.
- Decide which subproblems are finite enough to model with OR-Tools CP-SAT.
