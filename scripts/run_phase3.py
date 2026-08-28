"""Phase 3: solve the site selection, and price the straight line error.

Three questions get answered here, in order of how much they matter:

1. Where do the stores go, and how much demand do they cover.
2. Is the exact solve worth running, or does greedy already find it.
3. If the sites had been chosen using straight line distance, what would their
   real coverage have been. This is the one that turns a methodological point
   into a business number: not "straight line is wrong" but "straight line
   would have cost you this much coverage".

Run:  python scripts/run_phase3.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import coverage_from_matrix  # noqa: E402
from src.optimise import (
    optimality_gap,
    solve_mclp_exact,
    solve_mclp_greedy,
)  # noqa: E402


def evaluate_under(
    coverage: np.ndarray, weights: np.ndarray, selected: list[int]
) -> dict:
    """Coverage a given set of sites actually achieves under a given matrix."""
    if not selected:
        return {"covered_demand": 0.0, "coverage_share": 0.0, "covered_cells": 0}
    covered = np.zeros(coverage.shape[1], dtype=bool)
    for j in selected:
        covered |= coverage[j]
    total = float(weights.sum())
    return {
        "covered_demand": float(weights[covered].sum()),
        "coverage_share": float(weights[covered].sum() / total) if total else 0.0,
        "covered_cells": int(covered.sum()),
    }


def run(n_stores: int | None = None) -> dict:
    cfg = load_config()
    directories = paths(cfg)
    started = time.time()

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    network_matrix = data["network"]
    straight_matrix = data["straight"]
    weights = data["weights"]

    threshold = float(cfg["network"]["delivery_threshold_min"])
    n_stores = int(n_stores or cfg["optimisation"]["n_stores"])
    time_limit = int(cfg["optimisation"]["time_limit_s"])
    mip_gap = float(cfg["optimisation"]["mip_gap"])

    network_cover = coverage_from_matrix(network_matrix, threshold)
    straight_cover = coverage_from_matrix(straight_matrix, threshold)

    print(
        f"candidates {network_cover.shape[0]}, cells {network_cover.shape[1]}, "
        f"placing {n_stores} stores at a {threshold:.0f} minute promise"
    )

    print("\nsolving on the network matrix")
    exact = solve_mclp_exact(network_cover, weights, n_stores, time_limit, mip_gap)
    greedy = solve_mclp_greedy(network_cover, weights, n_stores)
    gap = optimality_gap(exact, greedy)
    print(
        f"  exact  : {exact['coverage_share']:.4f} of demand, "
        f"status {exact['status']}, {exact['runtime_s']}s, "
        f"proved optimal: {exact['proved_optimal']}"
    )
    print(
        f"  greedy : {greedy['coverage_share']:.4f} of demand, {greedy['runtime_s']}s"
    )
    print(f"  greedy leaves {gap:.4%} of the exact solution's demand on the table")

    print("\nsolving on the straight line matrix, then scoring it on the network")
    straight_solution = solve_mclp_exact(
        straight_cover, weights, n_stores, time_limit, mip_gap
    )
    straight_claimed = straight_solution["coverage_share"]
    straight_actual = evaluate_under(
        network_cover, weights, straight_solution["selected"]
    )
    penalty = exact["coverage_share"] - straight_actual["coverage_share"]

    overlap = sorted(set(exact["selected"]) & set(straight_solution["selected"]))
    print(f"  straight line claims  : {straight_claimed:.4f} of demand")
    print(f"  its real coverage is  : {straight_actual['coverage_share']:.4f}")
    print(
        f"  overstatement         : {straight_claimed - straight_actual['coverage_share']:.4f}"
    )
    print(f"  network optimum       : {exact['coverage_share']:.4f}")
    print(
        f"  cost of the shortcut  : {penalty:.4f} of demand "
        f"({penalty * float(weights.sum()):,.0f} orders per month)"
    )
    print(f"  sites in common       : {len(overlap)} of {n_stores}")

    print("\ncoverage curve across store counts")
    curve = []
    for n in cfg["sensitivity"]["n_stores"]:
        point = solve_mclp_greedy(network_cover, weights, int(n))
        curve.append({"n_stores": int(n), "coverage_share": point["coverage_share"]})
        print(f"  {n:3d} stores: {point['coverage_share']:.4f}")

    summary = {
        "n_stores": n_stores,
        "threshold_min": threshold,
        "total_demand_orders_per_month": float(weights.sum()),
        "network_exact": {k: v for k, v in exact.items() if k != "trace"},
        "network_greedy": {k: v for k, v in greedy.items() if k != "trace"},
        "greedy_optimality_gap": gap,
        "straight_line_solution": {
            "selected": straight_solution["selected"],
            "claimed_coverage_share": straight_claimed,
            "actual_coverage_share": straight_actual["coverage_share"],
            "overstatement": straight_claimed - straight_actual["coverage_share"],
            "coverage_lost_vs_network_optimum": penalty,
            "orders_per_month_lost": penalty * float(weights.sum()),
            "sites_in_common_with_network_optimum": overlap,
            "n_sites_in_common": len(overlap),
        },
        "coverage_curve": curve,
        "runtime_s": round(time.time() - started, 1),
    }

    report_path = directories["reports"] / "phase3_summary.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    with open(
        directories["artifacts"] / "selected_sites.json", "w", encoding="utf-8"
    ) as handle:
        json.dump(
            {
                "network_exact": exact["selected"],
                "network_greedy": greedy["selected"],
                "straight_line": straight_solution["selected"],
            },
            handle,
            indent=2,
        )

    print(f"\n  wrote {report_path.relative_to(REPO_ROOT)}")
    print(f"  phase 3 done in {summary['runtime_s']}s")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-stores", type=int, default=None)
    args = parser.parse_args()
    run(n_stores=args.n_stores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
