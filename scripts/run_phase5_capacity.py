"""Phase 5: what happens when a store cannot serve unlimited demand.

The covering model asks whether a store can reach a cell. It never asks whether
it can fulfil it. If throughput binds before reach does, then coverage was
answering the wrong question all along and the recommendation changes from
"where do 20 stores go" to "20 stores is not the number".

Capacity is swept rather than fixed, because I have no sourced throughput figure
and a single invented number would just relocate the guesswork.

Run:  python scripts/run_phase5_capacity.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import coverage_from_matrix  # noqa: E402
from src.optimise import solve_capacitated, solve_mclp_exact  # noqa: E402


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)
    started = time.time()

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    threshold = float(cfg["network"]["delivery_threshold_min"])
    cover = coverage_from_matrix(data["network"], threshold)
    weights = data["weights"]
    total = float(weights.sum())

    n_stores = int(cfg["optimisation"]["n_stores"])
    headline_capacity = float(cfg["capacity"]["orders_per_store_per_month"])

    print(f"total modelled demand: {total:,.0f} orders per month")
    print(f"placing {n_stores} stores\n")

    uncapped = solve_mclp_exact(cover, weights, n_stores, 300, 0.0)
    print(
        f"uncapacitated coverage: {uncapped['coverage_share']:.4f} "
        f"({uncapped['coverage_share'] * total:,.0f} orders reachable)"
    )

    print("\ncapacity sweep")
    rows = []
    uncapped_sites = set(uncapped["selected"])
    for capacity in cfg["capacity"]["orders_per_store_per_month_sweep"]:
        capacity = float(capacity)
        solution = solve_capacitated(cover, weights, n_stores, capacity, 600, 0.01)
        ceiling = capacity * n_stores / total
        row = {
            "capacity_per_store": capacity,
            "served_share": solution["served_share"],
            "demand_served": solution["demand_served"],
            "hard_ceiling_share": ceiling,
            "capacity_utilisation": solution["capacity_utilisation"],
            "sites_shared_with_uncapacitated": len(
                uncapped_sites & set(solution["selected"])
            ),
            "selected": solution["selected"],
            "runtime_s": solution["runtime_s"],
            "proved_optimal": solution["proved_optimal"],
        }
        rows.append(row)
        print(
            f"  {capacity:7,.0f}/store: serves {solution['served_share']:.4f} "
            f"(ceiling {ceiling:.4f}, utilisation {solution['capacity_utilisation']:.3f}), "
            f"{row['sites_shared_with_uncapacitated']}/{n_stores} sites shared, "
            f"{solution['runtime_s']}s"
        )

    print("\nstores needed to serve a target share, at the headline capacity")
    needed = []
    for target in [0.25, 0.50, 0.75, 0.90]:
        implied = int(np.ceil(target * total / headline_capacity))
        needed.append({"target_share": target, "stores_implied_by_capacity": implied})
        print(
            f"  {target:.0%} of demand needs at least "
            f"{implied:,} stores on throughput alone"
        )

    headline = next(
        (r for r in rows if r["capacity_per_store"] == headline_capacity), rows[0]
    )
    gap = uncapped["coverage_share"] - headline["served_share"]

    print(f"\nat {headline_capacity:,.0f} orders per store per month:")
    print(f"  coverage the covering model reports : {uncapped['coverage_share']:.4f}")
    print(f"  demand 20 stores can actually serve : {headline['served_share']:.4f}")
    print(f"  gap                                 : {gap:.4f}")
    print(
        f"  capacity utilisation                : {headline['capacity_utilisation']:.3f}"
    )

    binding = headline["capacity_utilisation"] > 0.98
    verdict = (
        "throughput binds, not reach: coverage was answering the wrong question"
        if binding
        else "reach binds before throughput at this capacity"
    )
    print(f"\nverdict: {verdict}")

    summary = {
        "total_demand_orders_per_month": total,
        "n_stores": n_stores,
        "uncapacitated_coverage_share": uncapped["coverage_share"],
        "headline_capacity": headline_capacity,
        "headline_served_share": headline["served_share"],
        "coverage_minus_served": gap,
        "capacity_sweep": rows,
        "stores_needed_for_target": needed,
        "verdict": verdict,
        "runtime_s": round(time.time() - started, 1),
    }
    path = directories["reports"] / "phase5_capacity.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    print(f"  phase 5 done in {summary['runtime_s']}s")
    return summary


if __name__ == "__main__":
    run()
