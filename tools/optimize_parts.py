"""pymoo NSGA-II optimizer for the icon part library problem.

Chromosome: per-cluster binary decisions — merge a cluster to 1 part, or keep
all members separate. Clusters come from the greedy simplification pass
(polygon Hausdorff + rotation). This keeps the search bounded to known-good merges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from itertools import product
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


def stable_hash(data: object) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _get_clusters(
    spec: dict,
    polygon_tolerance: float,
    rotation_angles: Sequence[float] | None,
) -> tuple[list[list[str]], dict[str, float]]:
    """Run rotation-enabled polygon Hausdorff clustering on the spec."""
    clusters, rotations = ip.cluster_polygons_by_hausdorff(
        spec["parts"],
        tolerance=polygon_tolerance,
        allow_rotation=True,
        rotation_angles=rotation_angles,
    )
    return clusters, rotations


def select_clusters(
    clusters: list[list[str]],
    limit: int | None,
) -> list[list[str]]:
    """Optionally keep only the highest-saving clusters, preserving original order."""
    if limit is None or limit <= 0 or limit >= len(clusters):
        return clusters
    ranked = sorted(
        enumerate(clusters),
        key=lambda item: (len(item[1]) - 1, -item[0]),
        reverse=True,
    )
    selected_indexes = {index for index, _cluster in ranked[:limit]}
    return [cluster for index, cluster in enumerate(clusters) if index in selected_indexes]


def cache_key(decision: np.ndarray | Sequence[int | bool]) -> tuple[int, ...]:
    return tuple(int(value > 0.5) for value in decision)


def cache_key_text(key: tuple[int, ...]) -> str:
    return "".join(str(value) for value in key)


def part_source_count(part_def: dict) -> int:
    return len(part_def.get("source_primitives", [])) + len(part_def.get("source_parts", []))


def load_score_cache(path: Path, spec_hash: str, cluster_hash: str) -> dict[tuple[int, ...], tuple[float, float]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "visit.optimizer-score-cache.v1":
        return {}
    if data.get("spec_hash") != spec_hash or data.get("cluster_hash") != cluster_hash:
        return {}
    entries = {}
    for key_text, value in data.get("entries", {}).items():
        entries[tuple(int(ch) for ch in key_text)] = (float(value[0]), float(value[1]))
    return entries


def write_score_cache(
    path: Path,
    spec_hash: str,
    cluster_hash: str,
    entries: dict[tuple[int, ...], tuple[float, float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": "visit.optimizer-score-cache.v1",
        "spec_hash": spec_hash,
        "cluster_hash": cluster_hash,
        "entries": {
            cache_key_text(key): [value[0], value[1]]
            for key, value in sorted(entries.items())
        },
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    def __init__(
        self,
        spec: dict,
        refs: dict,
        clusters: list[list[str]],
        rotations: dict[str, float],
        cache_enabled: bool = True,
        initial_cache: dict[tuple[int, ...], tuple[float, float]] | None = None,
    ):
        self._spec = spec
        self._refs = refs
        self._clusters = clusters
        self._rotations = rotations
        self._cache_enabled = cache_enabled
        self._cache: dict[tuple[int, ...], tuple[float, float]] = dict(initial_cache or {})
        self.cache_hits = 0
        self.cache_misses = 0

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
            key = cache_key(x[i])
            if self._cache_enabled and key in self._cache:
                F[i] = self._cache[key]
                self.cache_hits += 1
                continue

            merged_spec = _spec_for_decision(
                self._spec, self._clusters, self._rotations, x[i]
            )
            result = ip.score_spec(merged_spec, self._refs)
            unique = result["unique_parts"]
            area_err = result["overall_area_error_ratio"]
            hausdorff = result["worst_hausdorff"]
            value = (float(unique), float(area_err + hausdorff * 0.01))
            F[i] = value
            if self._cache_enabled:
                self._cache[key] = value
            self.cache_misses += 1

        out["F"] = F


def nondominated_indexes(F: np.ndarray) -> list[int]:
    """Return indexes on the minimization Pareto front."""
    keep = []
    for i in range(len(F)):
        dominated = False
        for j in range(len(F)):
            if i == j:
                continue
            if np.all(F[j] <= F[i]) and np.any(F[j] < F[i]):
                dominated = True
                break
        if not dominated:
            keep.append(i)
    return keep


def exhaustive_front(problem: ClusterMergeProblem, n_var: int, max_decisions: int) -> tuple[np.ndarray, np.ndarray]:
    decision_count = 2 ** n_var
    if decision_count > max_decisions:
        raise SystemExit(
            f"Exhaustive search would evaluate {decision_count} decisions; "
            f"increase --max-exhaustive-decisions or lower --cluster-limit"
        )

    X = np.array(list(product([0, 1], repeat=n_var)), dtype=int)
    out: dict[str, np.ndarray] = {}
    problem._evaluate(X, out)
    F = out["F"]
    keep = nondominated_indexes(F)
    keep.sort(key=lambda index: (F[index][0], F[index][1]))
    return X[keep], F[keep]


def optimize_command(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        raise SystemExit(f"Part spec not found: {spec_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    ref_dir = Path(args.references)
    refs = {r[0]: r for r in ip.load_references(ref_dir)}

    rotation_angles = args.rotation_angles or list(ip.DEFAULT_ROTATION_ANGLES)
    clusters, rotations = _get_clusters(spec, args.polygon_tolerance, rotation_angles)
    original_cluster_count = len(clusters)
    clusters = select_clusters(clusters, args.cluster_limit)
    spec_hash = stable_hash(spec)
    cluster_hash = stable_hash(clusters)

    initial_cache = {}
    cache_path = Path(args.cache_path) if args.cache_path else None
    if cache_path and not args.no_cache:
        initial_cache = load_score_cache(cache_path, spec_hash, cluster_hash)
        print(f"Loaded {len(initial_cache)} cached decisions from {cache_path}")

    print(f"Clusters from greedy pass: {original_cluster_count}")
    if len(clusters) != original_cluster_count:
        print(f"Using top {len(clusters)} clusters by part-count savings")
    for i, cl in enumerate(clusters):
        sizes = [part_source_count(spec["parts"][p]) for p in cl]
        print(f"  [{i}] {len(cl)} parts: {cl[:3]}{'...' if len(cl)>3 else ''}  sources: {sizes}")

    problem = ClusterMergeProblem(
        spec,
        refs,
        clusters,
        rotations,
        cache_enabled=not args.no_cache,
        initial_cache=initial_cache,
    )

    start_time = time.perf_counter()
    if args.exhaustive:
        print(f"\nRunning exhaustive Pareto search: vars={len(clusters)}")
        pareto_X, pareto_F = exhaustive_front(
            problem,
            len(clusters),
            args.max_exhaustive_decisions,
        )
    else:
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
        pareto_F = result.algorithm.opt.get("F")
        pareto_X = result.algorithm.opt.get("X")
    elapsed = time.perf_counter() - start_time

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pareto_rows = []
    for i in range(len(pareto_F)):
        parts = int(pareto_F[i][0])
        score = float(pareto_F[i][1])
        merged_count = int(sum(pareto_X[i] > 0.5))
        merged_spec = _spec_for_decision(spec, clusters, rotations, pareto_X[i])
        result = ip.score_spec(merged_spec, refs)
        spec_path_out = out_dir / f"part-spec.pareto_{i:02d}_parts_{parts}.v1.json"
        spec_path_out.write_text(
            json.dumps(merged_spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"  parts={parts:3d}  score={score:.6g}  "
            f"area_err={result['overall_area_error_ratio']:.6g}  "
            f"hausdorff={result['worst_hausdorff']:.4f}  "
            f"merged_clusters={merged_count}"
        )
        pareto_rows.append({
            "unique_parts": parts,
            "score": score,
            "area_error_ratio": result["overall_area_error_ratio"],
            "total_area_error": round(result["total_area_error"], 6),
            "worst_hausdorff": result["worst_hausdorff"],
            "merged_clusters": merged_count,
            "decision": pareto_X[i].tolist(),
            "spec": spec_path_out.as_posix(),
        })

    pareto_path = out_dir / "pareto_nsga2.json"
    pareto_path.write_text(json.dumps(pareto_rows, indent=2) + "\n", encoding="utf-8")
    print(f"\nPareto front ({len(pareto_rows)} points) -> {pareto_path}")
    print(
        "Cache: "
        f"{problem.cache_hits} hits, {problem.cache_misses} misses, "
        f"{len(problem._cache)} stored decisions, elapsed={elapsed:.2f}s"
    )
    if cache_path and not args.no_cache:
        write_score_cache(cache_path, spec_hash, cluster_hash, problem._cache)
        print(f"Cache written to {cache_path}")

    metadata = {
        "schema": "visit.optimizer-run.v1",
        "spec": spec_path.as_posix(),
        "references": ref_dir.as_posix(),
        "mode": "exhaustive" if args.exhaustive else "nsga2",
        "polygon_tolerance": args.polygon_tolerance,
        "rotation_angles": rotation_angles,
        "original_cluster_count": original_cluster_count,
        "used_cluster_count": len(clusters),
        "cluster_limit": args.cluster_limit,
        "selected_clusters": clusters,
        "cluster_hash": cluster_hash,
        "spec_hash": spec_hash,
        "population": args.population,
        "generations": args.generations,
        "seed": args.seed,
        "max_exhaustive_decisions": args.max_exhaustive_decisions,
    }
    metadata_path = out_dir / "run_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Run metadata written to {metadata_path}")

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
    parser.add_argument("--polygon-tolerance", type=float, default=0.5, help="Hausdorff tolerance for polygon merge clusters")
    parser.add_argument(
        "--rotation-angles",
        nargs="*",
        type=float,
        help="Allowed polygon reuse rotations in degrees, default: 0 45 90 135 180 225 270 315",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable decision-level score cache")
    parser.add_argument("--cache-path", help="Optional persistent score cache JSON")
    parser.add_argument("--cluster-limit", type=int, help="Use only the highest-saving N clusters")
    parser.add_argument("--exhaustive", action="store_true", help="Evaluate every decision for the selected clusters")
    parser.add_argument("--max-exhaustive-decisions", type=int, default=65536)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return optimize_command(args)


if __name__ == "__main__":
    raise SystemExit(main())
