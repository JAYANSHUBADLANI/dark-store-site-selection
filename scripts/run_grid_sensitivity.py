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

        # The finest grid has an order of magnitude more binary variables than
        # the base case, so it gets a longer limit and a small gap. Whether it
        # actually proved optimality is reported either way.
        limit = 3600 if cell_size < 250 else 900
        gap = 0.002 if cell_size < 250 else 0.0
        solution = solve_mclp_exact(cover, weights, n_stores, limit, gap)
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

    # Coverage and site selection have to be judged separately, because they can
    # and here do behave differently. An earlier version of this took the
    # minimum shift across the finer grids, which hid exactly that: the 250m run
    # agrees closely with the base case and the 125m run does not, and a minimum
    # reports only the agreeable one.
    separation_m = float(cfg["candidates"]["min_separation_m"])
    by_size = sorted(rows, key=lambda r: -r["cell_size_m"])

    # Coverage convergence: do successive refinements change the answer less
    # each time. This is the property a discretisation is supposed to have.
    coverage_steps = [
        {
            "from_m": by_size[i]["cell_size_m"],
            "to_m": by_size[i + 1]["cell_size_m"],
            "delta": by_size[i + 1]["coverage_share"] - by_size[i]["coverage_share"],
        }
        for i in range(len(by_size) - 1)
    ]
    deltas = [abs(step["delta"]) for step in coverage_steps]
    coverage_converging = all(deltas[i] > deltas[i + 1] for i in range(len(deltas) - 1))
    print("\ncoverage as the grid refines")
    for step in coverage_steps:
        print(
            f"  {step['from_m']:6.0f}m to {step['to_m']:6.0f}m: "
            f"{step['delta']:+.4f}"
        )
    print(f"  successive changes shrinking: {coverage_converging}")

    # Site stability: take the worst finer grid, not the best.
    finer = [r for r in non_base if r["cell_size_m"] < base_cell]
    coarser = [r for r in non_base if r["cell_size_m"] > base_cell]
    worst_finer_shift = max((r["median_shift_m"] for r in finer), default=0.0)
    coarser_shift = max((r["median_shift_m"] for r in coarser), default=0.0)
    sites_stable = worst_finer_shift <= separation_m

    print("\nsite selection as the grid refines")
    for row in sorted(finer, key=lambda r: -r["cell_size_m"]):
        print(
            f"  {row['cell_size_m']:6.0f}m: median shift "
            f"{row['median_shift_m']:.0f}m"
        )
    print(f"  candidate separation floor: {separation_m:.0f}m")
    print(f"  worst shift among finer grids: {worst_finer_shift:.0f}m")
    print(f"  sites stable under refinement: {sites_stable}")

    if coverage_converging and sites_stable:
        verdict = "both the coverage estimate and the site selection are stable under refinement"
    elif coverage_converging and not sites_stable:
        verdict = (
            "the coverage estimate converges but the site selection does not. "
            "Successive refinements change coverage by less each time, so the "
            "optimum value is well determined, while the chosen sites keep moving "
            "by more than the candidate separation, so the optimum argument is "
            "not. Trust the number, not the pins."
        )
    else:
        verdict = (
            "neither coverage nor site selection has settled by the finest grid run"
        )

    print(f"\ncoverage spread across resolutions: {coverage_spread:.4f}")
    print(f"verdict: {verdict}")

    summary = {
        "base_cell_size_m": base_cell,
        "n_stores": n_stores,
        "resolutions": rows,
        "coverage_spread": coverage_spread,
        "worst_median_shift_m": worst_median_shift,
        "candidate_separation_floor_m": separation_m,
        "coverage_steps": coverage_steps,
        "coverage_converging": bool(coverage_converging),
        "worst_shift_among_finer_grids_m": worst_finer_shift,
        "shift_when_coarsening_m": coarser_shift,
        "sites_stable_under_refinement": bool(sites_stable),
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
