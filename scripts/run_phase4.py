"""Phase 4: sensitivity sweep and site stability.

Every scenario is a single parameter change from the base case, so any movement
in the answer is attributable to one thing.

The scenarios differ in cost, and the runner exploits that rather than rebuilding
everything each time:

  threshold, store count   re-threshold the existing matrix, nearly free
  adoption variant         recompute cell weights, grid and matrix unchanged
  rider speed              rebuild the travel time matrix, the network is reused
  grid resolution          full rebuild of phase 1 and the matrix, handled by
                           scripts/run_grid_sensitivity.py because it is slow

The headline output is not any single scenario. It is site stability: how many
of the recommended sites survive across all of them. A site chosen under every
assumption is a different recommendation from one that appears only in the base
case, and a memo that presents them with equal confidence is misleading.

Run:  python scripts/run_phase4.py
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

from src.config import load_config, paths  # noqa: E402
from src.demand import build_demand_surface  # noqa: E402
from src.network import (  # noqa: E402
    add_travel_times,
    coverage_from_matrix,
    get_road_network,
    network_travel_time_matrix,
    snap_to_nodes,
)
from src.optimise import site_stability, solve_mclp_exact  # noqa: E402


def solve(coverage, weights, n_stores, cfg):
    return solve_mclp_exact(
        coverage,
        weights,
        n_stores,
        int(cfg["optimisation"]["time_limit_s"]),
        float(cfg["optimisation"]["mip_gap"]),
    )


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)
    started = time.time()

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    base_matrix = data["network"]
    base_weights = data["weights"]

    demand = gpd.read_file(
        directories["processed"] / "demand_surface.gpkg", layer="demand"
    )
    candidates = gpd.read_file(directories["processed"] / "candidates.gpkg")

    base_threshold = float(cfg["network"]["delivery_threshold_min"])
    base_speed = float(cfg["network"]["effective_speed_kmph"])
    base_n = int(cfg["optimisation"]["n_stores"])

    scenarios: dict[str, list[int]] = {}
    rows: list[dict] = []

    def record(name, matrix, weights, threshold, n_stores, changed, value):
        cover = coverage_from_matrix(matrix, threshold)
        solution = solve(cover, weights, n_stores, cfg)
        scenarios[name] = solution["selected"]
        row = {
            "scenario": name,
            "parameter_changed": changed,
            "value": value,
            "coverage_share": solution["coverage_share"],
            "proved_optimal": solution["proved_optimal"],
            "n_stores": n_stores,
            "threshold_min": threshold,
            "selected": solution["selected"],
        }
        rows.append(row)
        print(f"  {name:28s} coverage {solution['coverage_share']:.4f}")
        return row

    print("base case")
    record("base", base_matrix, base_weights, base_threshold, base_n, "none", "base")

    print("\ndelivery threshold")
    for threshold in cfg["sensitivity"]["delivery_threshold_min"]:
        if float(threshold) == base_threshold:
            continue
        record(
            f"threshold_{threshold:g}min",
            base_matrix,
            base_weights,
            float(threshold),
            base_n,
            "delivery_threshold_min",
            float(threshold),
        )

    print("\nstore count")
    for n in cfg["sensitivity"]["n_stores"]:
        if int(n) == base_n:
            continue
        record(
            f"n_stores_{n}",
            base_matrix,
            base_weights,
            base_threshold,
            int(n),
            "n_stores",
            int(n),
        )

    print("\nadoption curve shape")
    for variant in cfg["sensitivity"]["adoption_variants"]:
        if variant == "base":
            continue
        surface = build_demand_surface(demand, cfg, variant=variant)
        record(
            f"adoption_{variant}",
            base_matrix,
            surface["orders_per_month"].to_numpy(),
            base_threshold,
            base_n,
            "adoption_variant",
            variant,
        )

    print("\nrider speed, rebuilding the matrix each time")
    graph = get_road_network(cfg)
    candidate_nodes = snap_to_nodes(candidates, graph, cfg)["node_id"].to_numpy()
    demand_nodes = snap_to_nodes(demand, graph, cfg)["node_id"].to_numpy()
    cutoff = float(cfg["network"]["matrix_cutoff_min"])

    for speed in cfg["sensitivity"]["effective_speed_kmph"]:
        if float(speed) == base_speed:
            continue
        graph = add_travel_times(graph, cfg, speed_kmph=float(speed))
        matrix, _ = network_travel_time_matrix(
            graph, candidate_nodes, demand_nodes, cutoff_min=cutoff
        )
        record(
            f"speed_{speed:g}kmph",
            matrix,
            base_weights,
            base_threshold,
            base_n,
            "effective_speed_kmph",
            float(speed),
        )

    # Site stability is only meaningful across scenarios that place the same
    # number of stores. A 5 store and a 40 store solution cannot disagree in a
    # comparable way, so the store count sweep is excluded from the stability
    # calculation and reported separately as the coverage curve.
    comparable = {
        name: sites
        for name, sites in scenarios.items()
        if not name.startswith("n_stores_")
    }
    stability = site_stability(comparable)

    always = stability["always_selected"]
    once = stability["single_scenario_only"]
    print(f"\nsite stability across {stability['n_scenarios']} comparable scenarios")
    print(f"  sites chosen in every scenario : {len(always)} of {base_n}")
    print(f"  sites chosen in only one       : {len(once)}")
    print(f"  distinct sites ever chosen     : {len(stability['site_frequency'])}")

    base_sites = set(scenarios["base"])
    robust = sorted(base_sites.intersection(always))
    fragile = sorted(base_sites.difference(always))
    print(
        f"  of the {base_n} base case sites, {len(robust)} survive every scenario "
        f"and {len(fragile)} do not"
    )

    summary = {
        "base_case": {
            "speed_kmph": base_speed,
            "threshold_min": base_threshold,
            "n_stores": base_n,
        },
        "scenarios": rows,
        "site_stability": stability,
        "base_case_sites_robust": robust,
        "base_case_sites_fragile": fragile,
        "robust_share_of_base_case": len(robust) / base_n if base_n else 0.0,
        "runtime_s": round(time.time() - started, 1),
    }

    path = directories["reports"] / "phase4_sensitivity.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    print(f"  phase 4 done in {summary['runtime_s']}s")
    return summary


if __name__ == "__main__":
    run()
