"""pymoo NSGA-II optimizer for the icon part library problem.

Chromosome: per-cluster binary decisions — merge a cluster to 1 part, or keep
all members separate. Clusters come from the greedy simplification pass
(polygon Hausdorff + rotation). This keeps the search bounded to known-good merges.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.operators.sampling.rnd import BinaryRandomSampling
from pymoo.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icon_parts as ip


def _get_clusters(spec: dict) -> tuple[list[list[str]], dict[str, float]]:
    """Run rotation-enabled polygon Hausdorff clustering on the spec."""
    clusters, rotations = ip.cluster_polygons_by_hausdorff(
        spec["parts"], tolerance=0.5, allow_rotation=True
    )
    return clusters, rotations


def _spec_for_decision(
    spec: dict, clusters: list[list[str]], rotations: dict[str, float], decision: np.ndarray
) -> dict:
    """Build a part spec where each cluster i is merged if decision[i] == 1."""
    clusters_to_merge = []
    rots_for_merge = {}
    for i, cluster in enumerate(clusters):
        if decision[i] > 0.5:
            clusters_to_merge.append(cluster)
            for pid in cluster:
                rots_for_merge[pid] = rotations.get(pid, 0.0)
    if not clusters_to_merge:
        return spec
    return ip.merge_polygon_clusters(spec, clusters_to_merge, rotations=rots_for_merge)


class ClusterMergeProblem(Problem):
    def __init__(self, spec: dict, refs: dict, clusters: list[list[str]], rotations: dict[str, float]):
        self._spec = spec
        self._refs = refs
        self._clusters = clusters
        self._rotations = rotations

        n_var = len(clusters)
        super().__init__(
            n_var=n_var,
            n_obj=2,
            n_constr=0,
            xl=0,
            xu=1,
            type_var=int,
        )

    def _evaluate(self, x, out, *args, **kwargs):
        n_pop = x.shape[0]
        F = np.zeros((n_pop, 2))

        for i in range(n_pop):
            merged_spec = _spec_for_decision(
                self._spec, self._clusters, self._rotations, x[i]
            )
            result = ip.score_spec(merged_spec, self._refs)
            unique = result["unique_parts"]
            area_err = result["overall_area_error_ratio"]
            hausdorff = result["worst_hausdorff"]
            F[i] = [unique, area_err + hausdorff * 0.01]

        out["F"] = F


def optimize_command(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        raise SystemExit(f"Part spec not found: {spec_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    ref_dir = Path(args.references)
    refs = {r[0]: r for r in ip.load_references(ref_dir)}

    clusters, rotations = _get_clusters(spec)
    print(f"Clusters from greedy pass: {len(clusters)}")
    for i, cl in enumerate(clusters):
        sizes = [len(spec["parts"][p].get("source_primitives", [])) for p in cl]
        print(f"  [{i}] {len(cl)} parts: {cl[:3]}{'...' if len(cl)>3 else ''}  sources: {sizes}")

    problem = ClusterMergeProblem(spec, refs, clusters, rotations)

    pop_size = args.population
    algorithm = NSGA2(
        pop_size=pop_size,
        sampling=BinaryRandomSampling(),
        crossover=UniformCrossover(prob=0.9),
        mutation=BitflipMutation(prob=1.0 / max(len(clusters), 1)),
        eliminate_duplicates=True,
    )

    print(f"\nRunning NSGA-II: pop={pop_size}, gens={args.generations}, vars={len(clusters)}")
    result = minimize(
        problem,
        algorithm,
        ("n_gen", args.generations),
        seed=args.seed,
        verbose=True,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pareto_F = result.algorithm.opt.get("F")
    pareto_X = result.algorithm.opt.get("X")

    pareto_rows = []
    for i in range(len(pareto_F)):
        parts = int(pareto_F[i][0])
        score = float(pareto_F[i][1])
        merged_count = int(sum(pareto_X[i] > 0.5))
        print(f"  parts={parts:3d}  score={score:.6g}  merged_clusters={merged_count}")
        pareto_rows.append({
            "unique_parts": parts,
            "score": score,
            "merged_clusters": merged_count,
            "decision": pareto_X[i].tolist(),
        })

    pareto_path = out_dir / "pareto_nsga2.json"
    pareto_path.write_text(json.dumps(pareto_rows, indent=2) + "\n", encoding="utf-8")
    print(f"\nPareto front ({len(pareto_rows)} points) -> {pareto_path}")

    # Save best spec (all clusters merged = maximum simplification)
    best_x = np.ones(len(clusters))
    merged_all = _spec_for_decision(spec, clusters, rotations, best_x)
    ip.score_spec(merged_all, refs)  # warm-cache
    best_path = out_dir / "part-spec.nsga2_all_merged.v1.json"
    best_path.write_text(json.dumps(merged_all, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"All-merged spec written to {best_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default="analysis/runs/exact/part-spec.exact.v1.json", help="Input part spec JSON")
    parser.add_argument("--references", default="analysis/references", help="Reference JSON directory")
    parser.add_argument("--out", default="analysis/runs/nsga2", help="Output directory")
    parser.add_argument("--population", type=int, default=100, help="NSGA-II population size")
    parser.add_argument("--generations", type=int, default=30, help="Number of generations")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return optimize_command(args)


if __name__ == "__main__":
    raise SystemExit(main())