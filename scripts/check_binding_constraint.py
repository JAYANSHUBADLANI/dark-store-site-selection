"""At what store count does location start to matter.

Phase 5 finds that at 20 stores every store runs at exactly its capacity, so
served demand equals capacity times store count regardless of where the stores
go. Siting is irrelevant in that regime. It cannot stay irrelevant forever: add
enough stores and there is no longer enough reachable demand to fill them all,
at which point reach binds and location decides the answer again.

That crossover is the number that reconciles the whole project. Below it, the
question is "how many stores", and this repository's covering machinery is
answering something nobody asked. Above it, the covering machinery is the right
tool.

Run:  python scripts/check_binding_constraint.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import coverage_from_matrix  # noqa: E402
from src.optimise import solve_capacitated  # noqa: E402


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    cover = coverage_from_matrix(
        data["network"], cfg["network"]["delivery_threshold_min"]
    )
    weights = data["weights"]
    total = float(weights.sum())
    capacity = float(cfg["capacity"]["orders_per_store_per_month"])
    n_candidates = cover.shape[0]

    print(f"capacity {capacity:,.0f} orders per store per month")
    print(f"total demand {total:,.0f}")
    print(
        f"candidate set holds {n_candidates} sites, so that is the ceiling on "
        f"stores this can place\n"
    )

    counts = [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]
    rows = []
    crossover = None

    for n in counts:
        if n > n_candidates:
            break
        solution = solve_capacitated(cover, weights, n, capacity, 600, 0.01)
        ceiling = capacity * n / total
        utilisation = solution["capacity_utilisation"]
        binding = "capacity" if utilisation > 0.98 else "reach"
        if binding == "reach" and crossover is None:
            crossover = n
        rows.append(
            {
                "n_stores": n,
                "served_share": solution["served_share"],
                "capacity_ceiling_share": ceiling,
                "capacity_utilisation": utilisation,
                "binding_constraint": binding,
                "runtime_s": solution["runtime_s"],
            }
        )
        print(
            f"  {n:4d} stores: serves {solution['served_share']:.4f}  "
            f"ceiling {min(ceiling, 1.0):.4f}  utilisation {utilisation:.4f}  "
            f"binding: {binding}"
        )

    if crossover is None:
        message = (
            f"capacity still binds at {counts[-1]} stores, so within any store count "
            "this candidate set can express, siting never becomes the constraint"
        )
    else:
        message = (
            f"reach begins to bind somewhere between {crossover - 20} and "
            f"{crossover} stores. Below that, store count decides the answer and "
            "location barely matters. Above it, the covering model is the right tool."
        )
    print(f"\n{message}")

    out = {
        "capacity_per_store": capacity,
        "total_demand": total,
        "n_candidates": n_candidates,
        "sweep": rows,
        "crossover_n_stores": crossover,
        "message": message,
    }
    path = directories["reports"] / "binding_constraint_check.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    return out


if __name__ == "__main__":
    run()
