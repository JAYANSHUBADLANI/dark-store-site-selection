"""Is the conclusion an artefact of the 500m analysis grid.

A 500m cell is 1.67 minutes of travel at 18 km/h, about 17% of the 10 minute
promise, so the coverage boundary is only resolved to within a couple of
minutes. If halving or doubling the cell size moves the recommended sites, then
the grid is doing part of the deciding and nothing downstream of it can be
trusted.

The candidate set is held fixed at the one built for the 500m run, so the only
thing changing between runs is how demand is represented and measured. Letting
candidates regenerate per resolution would confound two changes at once.

Run:  python scripts/run_grid_sensitivity.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.boundary import get_city_boundary  # noqa: E402
from src.config import load_config, paths  # noqa: E402
from src.demand import build_demand_surface, filter_low_demand  # noqa: E402
from src.grid import build_grid  # noqa: E402
from src.network import (  # noqa: E402
    add_travel_times,
    coverage_from_matrix,
    get_road_network,
    network_travel_time_matrix,
    snap_to_nodes,
)
from src.optimise import solve_mclp_exact  # noqa: E402
from src.population import attach_population  # noqa: E402


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)
    started = time.time()

    n_stores = int(cfg["optimisation"]["n_stores"])
    threshold = float(cfg["network"]["delivery_threshold_min"])
    cutoff = float(cfg["network"]["matrix_cutoff_min"])
    base_cell = float(cfg["grid"]["cell_size_m"])

    boundary = get_city_boundary(cfg)
    candidates = gpd.read_file(directories["processed"] / "candidates.gpkg")
    coords = {
        int(row.candidate_id): (row.geometry.x, row.geometry.y)
        for row in candidates.itertuples()
    }

    graph = get_road_network(cfg)
    graph = add_travel_times(graph, cfg)
    candidate_nodes = snap_to_nodes(candidates, graph, cfg)["node_id"].to_numpy()

    rows = []
    selections: dict[float, list[int]] = {}

    for cell_size in cfg["sensitivity"]["grid_resolutions_m"]:
        cell_size = float(cell_size)
        print(f"\ncell size {cell_size:.0f}m")
        step_started = time.time()

        grid = build_grid(boundary, cfg, cell_size_m=cell_size)
        grid = attach_population(grid, cfg)
        surface = build_demand_surface(grid, cfg, variant="base")
        surface, dropped = filter_low_demand(surface, cfg)
        print(
            f"  cells {len(surface):,} (from {dropped['cells_before']:,}), "
            f"population {surface['population'].sum():,.0f}, "
            f"orders {surface['orders_per_month'].sum():,.0f}"
        )

        demand_nodes = snap_to_nodes(surface, graph, cfg)["node_id"].to_numpy()
        matrix, prune = network_travel_time_matrix(
            graph, candidate_nodes, demand_nodes, cutoff_min=cutoff
        )
        cover = coverage_from_matrix(matrix, threshold)
        weights = surface["orders_per_month"].to_numpy()

        solution = solve_mclp_exact(cover, weights, n_stores, 600, 0.0)
        selections[cell_size] = solution["selected"]
        print(
            f"  coverage {solution['coverage_share']:.4f}  "
            f"({solution['runtime_s']}s, proved optimal {solution['proved_optimal']})"
        )

        rows.append(
            {
                "cell_size_m": cell_size,
                "cells": int(len(surface)),
                "total_population": float(surface["population"].sum()),
                "total_orders_per_month": float(weights.sum()),
                "orders_share_dropped_by_filter": dropped["orders_share_dropped"],
                "coverage_share": solution["coverage_share"],
                "proved_optimal": solution["proved_optimal"],
                "solve_runtime_s": solution["runtime_s"],
                "selected": solution["selected"],
                "step_runtime_s": round(time.time() - step_started, 1),
            }
        )

    base_sites = selections[base_cell]
    base_set = set(base_sites)
    base_points = np.array([coords[s] for s in base_sites])

    print(f"\ncomparing against the {base_cell:.0f}m base case")
    for row in rows:
        if row["cell_size_m"] == base_cell:
            row["sites_shared_with_base"] = len(base_set)
            row["median_shift_m"] = 0.0
            row["max_shift_m"] = 0.0
            continue
        other = np.array([coords[s] for s in row["selected"]])
        shifts = [
            float(np.min(np.hypot(other[:, 0] - p[0], other[:, 1] - p[1])))
            for p in base_points
        ]
        row["sites_shared_with_base"] = len(base_set & set(row["selected"]))
        row["median_shift_m"] = float(np.median(shifts))
        row["max_shift_m"] = float(np.max(shifts))
        row["base_sites_within_1km"] = int(np.sum(np.array(shifts) <= 1000))
        print(
            f"  {row['cell_size_m']:6.0f}m: coverage {row['coverage_share']:.4f}, "
            f"{row['sites_shared_with_base']}/{n_stores} identical sites, "
            f"median shift {row['median_shift_m']:.0f}m, "
            f"{row['base_sites_within_1km']}/{n_stores} within 1 km"
        )

    non_base = [r for r in rows if r["cell_size_m"] != base_cell]
    worst_median_shift = max(r["median_shift_m"] for r in non_base)
    coverage_spread = max(r["coverage_share"] for r in rows) - min(
        r["coverage_share"] for r in rows
    )

    # Two reference points make the shift numbers interpretable.
    #
    # First, candidates are thinned to a minimum separation, so a shift smaller
    # than that separation is below the finest distinction the candidate set can
    # express. It is not evidence of instability, it is the resolution floor.
    #
    # Second, refining and coarsening are not symmetric questions. If halving the
    # cell size moves the answer less than doubling it does, the solution is
    # converging and the base case is on the settled side of that.
    separation_m = float(cfg["candidates"]["min_separation_m"])
    finer = [r for r in non_base if r["cell_size_m"] < base_cell]
    coarser = [r for r in non_base if r["cell_size_m"] > base_cell]
    finer_shift = min((r["median_shift_m"] for r in finer), default=float("nan"))
    coarser_shift = max((r["median_shift_m"] for r in coarser), default=float("nan"))
    converging = finer_shift < coarser_shift

    if finer_shift <= separation_m and converging:
        verdict = (
            "adequate at the base resolution: refining moves the answer less than "
            "the candidate separation floor, and less than coarsening does, so the "
            "solution is converging and the coarsest grid is the unreliable one"
        )
    elif coverage_spread <= 0.05 and worst_median_shift <= separation_m:
        verdict = "robust to grid resolution"
    else:
        verdict = "resolution dependent: the grid is doing part of the deciding"

    print(f"\ncoverage spread across resolutions: {coverage_spread:.4f}")
    print(f"candidate separation floor: {separation_m:.0f}m")
    print(f"shift when refining to the finest grid:  {finer_shift:.0f}m")
    print(f"shift when coarsening to the coarsest:   {coarser_shift:.0f}m")
    print(f"converging with resolution: {converging}")
    print(f"verdict: {verdict}")

    summary = {
        "base_cell_size_m": base_cell,
        "n_stores": n_stores,
        "resolutions": rows,
        "coverage_spread": coverage_spread,
        "worst_median_shift_m": worst_median_shift,
        "candidate_separation_floor_m": separation_m,
        "shift_when_refining_m": finer_shift,
        "shift_when_coarsening_m": coarser_shift,
        "converging_with_resolution": bool(converging),
        "verdict": verdict,
        "runtime_s": round(time.time() - started, 1),
    }
    path = directories["reports"] / "grid_sensitivity.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    print(f"  done in {summary['runtime_s']}s")
    return summary


if __name__ == "__main__":
    run()
