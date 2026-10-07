# Visit Brand Icons

A scriptable toolkit that turns the Visit brand SVG icons into 3D-printable, wall-mountable modular displays.

Each icon part is a printable pair: a small hidden **backplate** with two mounting holes, and a hollow translucent **front cap** that snaps over it. The pipeline normalizes the source SVGs into reference geometry, simplifies the icons into a reusable part library, searches for the best trade-off between part count and visual fidelity, and generates print-ready STEP kits with engraved assembly marks.

**Everything generated comes from scripts.** Raw SVGs are immutable design references; all JSON, SVG, and STEP outputs in `analysis/` and `cad/` are reproducible.

## Status at a glance

| Area | State |
| --- | --- |
| Source icons | 14 SVGs, all 48 x 48 viewBox |
| Reference pipeline | Done — deterministic, hash-verified, drift-checked |
| Part library | **41 unique parts at 0.0799% area error** across all 14 icons |
| Optimization | Greedy + rotation merging done; NSGA-II (pymoo) pipeline built and run |
| STEP kits | Fixture kit: 41 designs, 67 caps + 67 backplates, 8 plates on 180x180 |
| Slicer validation | Done — all 14 kit STEPs manifold, body counts match, slice clean (PrusaSlicer 2.9.6) |
| Fit calibration | Coupon kit generated (0.15/0.25/0.35 mm) and slicer-validated |
| Physical prints | **Not started** — needs a printer |
| Wall-mount approval | **Blocked / external** — needs facilities sign-off |
| Maker docs | Draft set written under `docs/` |

The living project plan is [`WIP_PROJECT_PLAN.md`](WIP_PROJECT_PLAN.md). It is the single source of truth for decisions, open questions, and milestones.

## Start here

If you just want to print and mount an icon:

1. Read [`docs/quick-start.md`](docs/quick-start.md).
2. Print the fit coupons: `analysis/runs/snapfit/fit-coupons/fit-coupon-kit.step`.
3. Print the kit: `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.step` (or `plate_01..08.step`).
4. Assemble using the legend: `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-legend.svg`.

If you want to understand or change the pipeline, start with [`docs/customization-guide.md`](docs/customization-guide.md) and [`ICON_ANALYSIS_PLAN.md`](ICON_ANALYSIS_PLAN.md).

## How it works

```text
SVG/*.svg                      immutable source design files
   │  icon_reference.py build
   ▼
analysis/references/           *.reference.json (WKB geometry, primitive hints, hashes)
   │  icon_parts.py bootstrap
   ▼
analysis/runs/exact/           part-spec.exact.v1.json (65 primitives as parts, zero simplification)
   │  icon_parts.py simplify / optimize_parts.py / icon_decompose.py
   ▼
analysis/runs/simplify*/       candidate part libraries + pareto.jsonl trade-off logs
   │  (recommended: part-spec.combined_rtol1.0_phd0.5_rot.v1.json — 41 parts)
   ▼
analysis/runs/snapfit/         STEP fixture kits + manifests + legends
   │  validate_slicer.py → PrusaSlicer
   ▼
analysis/runs/slicer-validation/  import/slice evidence report
```

Scoring is done with Shapely: symmetric-difference area, Hausdorff distance, bounds delta, and component counts, compared against the canonical reference geometry for every icon.

## Repository index

### Source and plans

| Path | What it is |
| --- | --- |
| `SVG/` | 14 immutable source icon SVGs |
| `WIP_PROJECT_PLAN.md` | Master plan: intent, milestones, decisions, dashboard |
| `ICON_ANALYSIS_PLAN.md` | Part-spec format, scoring, simplification, pymoo integration plan |
| `REFERENCE_RENDERING_PLAN.md` | Reference artifact schema and canonicalization rules |
| `SNAPFIT_DESIGN_PLAN.md` | Mechanical design: caps, backplates, coupons, validation log |
| `CAD_FEASIBILITY_SPIKE.md` | build123d STEP export prototype results |
| `requirements.txt` | shapely, svgelements, numpy, pymoo |
| `requirements-cad.txt` | `-r requirements.txt` plus build123d |

### Tools (`tools/`)

| Tool | Commands | Purpose |
| --- | --- | --- |
| `icon_reference.py` | `build`, `render`, `check`, `verify` | SVG → reference JSON + canonical SVG + manifest |
| `icon_parts.py` | `bootstrap`, `render`, `score`, `simplify` | Primitive parts, reconstruction, Shapely scoring, merge strategies |
| `icon_decompose.py` | `generate`, `score`, `render` | Triangulated decomposition candidate layer |
| `optimize_parts.py` | (single command) | pymoo NSGA-II search over merge decisions |
| `export_step.py` | `front`, `kit-manifest`, `kit`, `part-fixture-kit-manifest`, `part-fixture-kit`, `fit-coupon-kit` | build123d STEP generation: front pieces, kits, fixtures, coupons |
| `generate_fixture_legend.py` | (single command) | Assembly legend SVG/JSON from a fixture manifest |
| `generate_part_similarity_legend.py` | (single command) | Part-similarity review sheets |
| `validate_slicer.py` | (single command) | PrusaSlicer `--info` + slice validation report |

### Generated analysis (`analysis/`)

| Path | What it is |
| --- | --- |
| `analysis/references/` | Per-icon `*.reference.json`, canonical SVGs, `manifest.json` |
| `analysis/runs/exact/` | Zero-simplification baseline part spec (65 parts) + `*.parts.svg` reviews |
| `analysis/runs/simplify/` | Candidate specs from greedy merges; `pareto.jsonl`; **recommended spec lives here** |
| `analysis/runs/simplify/combined_rtol1.0_phd0.5_rot/` | Review SVGs for the recommended spec (all 14 icons) |
| `analysis/runs/simplify-centroid-fine/` | Finer candidate sweep used by the optimizer (tol ladder 0.5–1.0) |
| `analysis/runs/nsga2/` | First NSGA-II run (cluster decisions) |
| `analysis/runs/nsga2-centroid-tol0.55` / `tol0.6` / `tol0.85` | NSGA-II Pareto fronts at three merge tolerances |
| `analysis/runs/decompose/` | Triangulated decomposition candidate + scoring |
| `analysis/runs/kits/recommended/` | Plain universal front-piece STEP kit (4 plates) |
| `analysis/runs/snapfit/part-backplate-v1/` | **Fixture kit**: caps + backplates, Platform single-icon kit, legends |
| `analysis/runs/snapfit/fit-coupons/` | Fit calibration coupon kit |
| `analysis/runs/similarity/`, `analysis/runs/comparison-legends/` | Candidate comparison and similarity review sheets |
| `analysis/runs/slicer-validation/` | PrusaSlicer import/slice report (G-code excluded from git) |
| `cad/exports/step/` | Early feasibility spike artifact (Hotel front STEP) |

### Documentation (`docs/`)

| Doc | Contents |
| --- | --- |
| `quick-start.md` | Print and mount an icon end-to-end |
| `printer-setup.md` | Printer, material, slicing settings, translucent tips |
| `fit-calibration.md` | Coupon workflow, clearance table, regeneration command |
| `assembly-guide.md` | Part marks, legend, snap assembly, troubleshooting |
| `mounting-guide.md` | Fastener options, wall policy, removal |
| `customization-guide.md` | All CLI parameters, library regeneration, validation |
| `workshop-guide.md` | Group build session format |

## Recommended artifacts (the short list)

| Artifact | Path |
| --- | --- |
| Part library (41 parts, 0.0799% error) | `analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json` |
| Part review SVGs (black ref + colored part outlines) | `analysis/runs/simplify/combined_rtol1.0_phd0.5_rot/*.parts.svg` |
| Trade-off log | `analysis/runs/simplify/pareto.jsonl` |
| Fixture kit STEP (all 8 plates in one file) | `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.step` |
| Fixture kit plates | `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.plate_01..08.step` |
| Single-icon Platform kit | `analysis/runs/snapfit/part-backplate-v1/Visit_Icon_Platform.fixture-kit.step` |
| Assembly legend | `analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-legend.svg` / `.json` |
| Fit coupons | `analysis/runs/snapfit/fit-coupons/fit-coupon-kit.step` |
| Slicer validation report | `analysis/runs/slicer-validation/slicer-validation.json` |

## Quick command reference

```powershell
# Setup
python -m venv .venv; .venv\Scripts\Activate.ps1
python -m pip install -r requirements-cad.txt

# Reference pipeline
python tools/icon_reference.py build
python tools/icon_reference.py verify

# Part library
python tools/icon_parts.py bootstrap
python tools/icon_parts.py simplify --no-bbox-decompose --polygon-tolerances 0.5 --rect-tolerances 1.0
python tools/icon_parts.py score --spec analysis/runs/simplify/part-spec.combined_rtol1.0_phd0.5_rot.v1.json

# Optimization
python tools/optimize_parts.py --spec analysis/runs/simplify-centroid-fine/part-spec.combined_rtol1.0_phd0.6_rot.v1.json

# STEP kits and coupons
python tools/export_step.py part-fixture-kit --scope universal --out analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.step --manifest analysis/runs/snapfit/part-backplate-v1/universal-single-icon-fixture-kit.manifest.json --split-plates --verify-import
python tools/export_step.py fit-coupon-kit --out analysis/runs/snapfit/fit-coupons/fit-coupon-kit.step --manifest analysis/runs/snapfit/fit-coupons/fit-coupon-kit.manifest.json --split-plates --verify-import

# Validation
python tools/validate_slicer.py --inputs analysis/runs/snapfit/part-backplate-v1 --slice --out analysis/runs/slicer-validation
```

## Project history

The commit history below is the story of the project, in order.

### Era 1 — Planning (2026-06-26 to 06-27)

| Commit | What happened |
| --- | --- |
| `f983dd0` | Initial project plan: two-layer modular icons, snap-fit research, milestones |
| `6f30d54` | Analysis workflow plans: part spec format, Shapely scoring, optimizer options |
| `73c9f76` | Optimizer approach documented: greedy first, then pymoo/OR-Tools/SciPy |

### Era 2 — Reference pipeline and CAD stack (06-27)

| Commit | What happened |
| --- | --- |
| `08bf455` | `icon_reference.py` toolchain: SVG → reference JSON + canonical SVG + manifest |
| `881aec1` | STEP declared the only generated CAD handoff format (no STL) |
| `490bdc6` | build123d feasibility spike: STEP export + re-import verified |
| `fe89a11` | First slicer decision: Cura |
| `9202a48` | Slicer decision revised to PrusaSlicer (native STEP) |

### Era 3 — Exact baseline and scoring loop (06-27)

| Commit | What happened |
| --- | --- |
| `4ad9545` | `icon_parts.py`: bootstrap/render/score; exact 61-part baseline at ~0 error (the baseline later grew to 65 parts after three source SVG splits in Era 6) |

### Era 4 — Greedy simplification and rotations (06-27)

| Commit | What happened |
| --- | --- |
| `ef6c582` | Greedy merges: rect sizes, polygon Hausdorff, bbox decomposition; Pareto logging |
| `1becfa8` | Rotation-aware clustering with centroid anchoring (90° steps) |
| `8abef57` | Rotation bug fix: prefer 0° when within 5% of best match |
| `5e211b7` | Plan updated: greedy pass complete (61→42 parts at 0.075%) |

### Era 5 — Decomposition experiments and cleanup (06-27 to 06-28)

| Commit | What happened |
| --- | --- |
| `f975813` | Oriented bounding-box rect fit attempted |
| `3313a50` | Oriented rect fit removed — no better than Hausdorff merging |
| `daca49e` | pymoo integration plan added to analysis plan |
| `0283113` | Inscribed-rectangle decomposition attempted (43 parts at 0.70%) |
| `d079efb` | `render --outlines`: per-part colored outlines for visual review |
| `cbc14cb` | Render output simplified: overlays + outlines only |
| `569d15c` | Overlays and outlines merged into one `*.parts.svg` per icon |
| `bfb3a48` | All axis-aligned decomposition experiments stripped as failed; plans documented it |

### Era 6 — Optimizer, triangulated decomposition, physical design (06-28 to 07-01)

| Commit | What happened |
| --- | --- |
| `cb5a39b` | Optimizer artifacts repaired after cleanup |
| `c2a0bc7` | Triangulated decomposition candidate layer (`icon_decompose.py`) |
| `d22a870` | Cached bounded optimizer loop (NSGA-II at three tolerances) |
| `2979fb0` | Laid-out universal front-piece STEP kit export |
| `ba23ccd` | Friction peg snap-fit prototype (later superseded) |
| `75b3fdc` | Platform socket backplate prototype (later superseded) |
| `8a3c490` | Per-part fixture kit: hollow cap + hidden two-hole backplate per part |
| `b1f932e` | Platform reuse fix, 45°-increment rotation allowed, fixture legend |
| `4745aa1` | Engraved global part numbers in STEP exports |
| `1d24254` | Ski resort chevron split; final candidate 41 parts at 0.0799% |

### Era 7 — Validation, coupons, docs (10-07)

| Commit | What happened |
| --- | --- |
| `fceda22` | `validate_slicer.py`, fit-coupon kit subcommand, 7 maker docs, plan status updates |

## Known gaps and dead ends

**Not done (physical/external):**

- Physical print of caps/backplates and clearance confirmation
- Wall-mount fastener approval (facilities)
- Brand/design sign-off on the 41-part library
- Employee/maker-space pilot

**Dead ends — do not resurrect without new evidence:**

- Axis-aligned decomposition of polygons (grid-split, bbox, inscribed rect, oriented rect): all produced worse part counts or visible distortion. Documented in `ICON_ANALYSIS_PLAN.md`.
- Full-icon backplate and peg/socket snap designs: replaced by the per-part cap/backplate press-fit.
- Cura as slicer target: PrusaSlicer only (native STEP).

**Exploratory but unproven:**

- Triangulated decomposition (`analysis/runs/decompose/`): expands the baseline to 160 parts; reuse value not demonstrated.
- 45-degree rotation reuse: working, but finer angle steps remain an open question.
