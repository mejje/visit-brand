# Reference Rendering Plan

Last updated: 2026-06-27

## Goal

Build a small, deterministic reference-rendering pipeline for the current brand icon SVGs.

The immediate purpose is to create trustworthy generated artifacts that make later Shapely scoring and STEP generation easier to validate:

```text
SVG source
  -> parsed filled geometry
  -> *.reference.json
  -> canonical SVG
  -> geometry verification and metrics
```

This plan is intentionally narrower than the overall project plan. It focuses only on producing and validating generated reference artifacts.

## Inputs

- `SVG/Visit_Icon_*.svg`

Current source assumptions:

- All source icons use `viewBox="0 0 48 48"`.
- Icons use filled `rect`, `polygon`, and `path` primitives.
- `Visit_Icon_Amusement park.svg` includes a curved path.
- `Visit_Icon_Travel agent.svg` includes a transformed rotated rectangle.
- No strokes, masks, gradients, clipping, or nested groups have been observed so far.

## Outputs

Generated files should live under `analysis/references/`:

```text
analysis/
  references/
    manifest.json
    Visit_Icon_Hotel.reference.json
    Visit_Icon_Hotel.canonical.svg
```

All files in `analysis/references/` are generated artifacts. They may be committed for review and regression checks, but they should be recreated by tooling rather than hand-edited.

## Reference JSON Contract

Use `*.reference.json` as a generated snapshot of the source SVG's filled geometry and metadata.

Recommended v1 shape:

```json
{
  "schema": "visit.icon-reference.v1",
  "icon_id": "Visit_Icon_Hotel",
  "source": {
    "path": "SVG/Visit_Icon_Hotel.svg",
    "sha256": "...",
    "viewBox": [0, 0, 48, 48]
  },
  "normalization": {
    "units": "svg_user_units",
    "coordinate_system": "svg_y_down",
    "fill_rule": "nonzero",
    "curve_flatten_tolerance": 0.02,
    "coordinate_precision": 0.000000001
  },
  "geometry": {
    "format": "wkb_hex",
    "value": "..."
  },
  "primitive_hints": [],
  "metrics": {
    "area": 0,
    "bounds": [0, 0, 0, 0],
    "component_count": 0,
    "hole_count": 0
  }
}
```

Notes:

- Prefer WKB hex for the primary Shapely geometry snapshot because it is compact and round-trips cleanly through Shapely.
- Optionally include WKT during early debugging if readability is useful.
- Keep `primitive_hints` optional in v1. The renderer should not depend on them.
- Store enough generation settings to detect stale references after parser or tolerance changes.

## Canonicalization Rules

The source-to-reference conversion should be strict:

- Resolve CSS classes and presentation attributes to effective fill metadata.
- Resolve all transforms into coordinates before storing geometry.
- Convert rects, polygons, and paths into filled polygons.
- Flatten curves with a documented tolerance, initially `0.02` SVG units, then validate against render overlays.
- Merge same-fill primitives per icon with polygon union.
- Preserve original primitive boundaries only as optional `primitive_hints`; the merged filled silhouette is the comparison reference.
- Round coordinates to a fixed precision, initially `0.000001` SVG units.
- Orient and sort polygon rings deterministically so text diffs are stable.
- Store source file hashes and generator settings so generated references can be detected as stale.

## Renderer Responsibilities

The renderer should convert `*.reference.json` into deterministic visual artifacts:

- Load the Shapely geometry snapshot.
- Validate geometry before rendering.
- Convert exterior and interior rings into SVG path data.
- Preserve the normalized `0..48` coordinate system.
- Render a canonical SVG with fixed precision and stable ordering.
- Write metrics that can be compared in CI.

The renderer should not:

- reinterpret the original SVG,
- optimize or simplify the geometry,
- make brand decisions,
- depend on raw SVG element ordering once reference JSON exists.

## Tooling Plan

Create `tools/icon_reference.py` with subcommands:

```text
python tools/icon_reference.py build --input SVG --out analysis/references
python tools/icon_reference.py render --input analysis/references --out analysis/references
python tools/icon_reference.py check --input SVG --references analysis/references
python tools/icon_reference.py verify --references analysis/references
```

Subcommand behavior:

- `build`: parse SVG sources, generate `*.reference.json`, canonical SVGs, and `manifest.json`.
- `render`: regenerate canonical SVGs from existing `*.reference.json` files only.
- `check`: fail if source hashes, generator settings, or expected generated files are stale.
- `verify`: re-import source SVGs and canonical SVGs, compare both against reference JSON geometry, and fail if geometric round-trip error exceeds tolerance.

Recommended libraries:

- SVG parsing and transforms: `svgelements`.
- Geometry: `shapely`.
- SVG writing: standard XML/string generation from Shapely rings.

## Determinism Rules

- Sort icons by filename.
- Sort geometry components deterministically, such as by bounds and area.
- Use fixed coordinate precision, initially `0.000000001` SVG units.
- Use fixed SVG output structure and attributes.
- Write JSON with sorted keys and stable indentation.
- Do not include timestamps in generated artifacts.
- Record generator version/settings in `manifest.json`.

## Validation

Minimum checks for the first implementation:

- Every source SVG produces one reference JSON and one canonical SVG.
- Running `build` twice produces no file diffs.
- `check` fails when a source SVG changes without regenerating references.
- Bounds remain within the expected `0..48` coordinate space unless explicitly documented.
- Geometry is valid or repaired with a documented operation.
- Canonical SVGs visually match the original SVG render when inspected.
- `verify` reports zero source/reference geometry diff and only near-zero canonical/reference text-rounding diff.

Recommended comparison metrics:

- filled area,
- bounds,
- component count,
- hole count,
- Shapely validity status.

## First Implementation Slice

Start with four representative icons:

- `Visit_Icon_Hotel.svg`: rect-heavy.
- `Visit_Icon_Platform.svg`: polygon-only.
- `Visit_Icon_Amusement park.svg`: curved path.
- `Visit_Icon_Travel agent.svg`: transformed rotated rectangle.

Done means:

- The four icons generate reference JSON and canonical SVG.
- The canonical SVGs visually match the source SVGs.
- The build is deterministic across two consecutive runs.
- Unsupported SVG features produce clear errors.

After that, expand to all icons in `SVG/`.

## Open Decisions

- Confirm whether WKB hex should remain the primary stored geometry, or whether a debug WKT field should be included during early development.
- Confirm the initial curve flattening tolerance.
- Confirm whether `primitive_hints` are needed in the first implementation or can wait for part-library generation.
- Decide whether generated reference artifacts should be committed once the pipeline is stable.
- Decide whether CI should check only source hashes and deterministic SVG output, or also run the full geometry `verify` step.

## Relationship To The Main Plan

This plan supports Milestone 1, Reference Geometry Baseline, in `WIP_PROJECT_PLAN.md`.

The broader project still uses:

- Shapely as the primary geometry comparison kernel.
- A parametric 2D part spec as the editable optimizer format.
- CadQuery or build123d as downstream STEP generators.

## Research Notes

- SVG paths cover lines, cubic/quadratic Beziers, arcs, and closed subpaths: <https://www.w3.org/TR/SVG2/paths.html>.
- SVG basic shapes can be normalized into path-like geometry: <https://www.w3.org/TR/SVG2/shapes.html>.
- SVG coordinates are affected by `viewBox` and transforms, with the default coordinate system using x-right and y-down: <https://www.w3.org/TR/SVG2/coords.html>.
- SVG fill coverage depends on fill rules, with `nonzero` as the initial fill-rule value: <https://www.w3.org/TR/SVG2/painting.html>.
- Shapely supports geometric union, symmetric difference, Hausdorff distance, WKB/WKT serialization, and GeoJSON-like mappings: <https://shapely.readthedocs.io/en/stable/manual.html>.
- `svgelements` is a good SVG ingestion candidate because it focuses on SVG parsing, affine transforms, viewports, colors, and shape primitives: <https://github.com/meerk40t/svgelements>.
- SVGO can be useful for generated SVG cleanup, numeric rounding, and transform/path normalization, but should not replace generated reference artifacts or the Shapely scoring pipeline: <https://svgo.dev/docs/plugins/convertPathData/> and <https://svgo.dev/docs/plugins/cleanupNumericValues/>.
