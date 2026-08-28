"""Do speed and delivery threshold collapse into one parameter.

The phase 4 sensitivity treats rider speed and the delivery threshold as two
separate assumptions. But a covering constraint only ever asks whether a cell is
within `speed * threshold` metres of road distance from a store, so the two
should enter the model only through their product. If that is right, two
scenarios with the same effective radius must select the same sites, and the
sensitivity analysis has one degree of freedom where it appears to have two.

That matters for what the memo can tell someone to do. Arguing about the demand
model when the answer is governed by a single distance is wasted effort.

Run:  python scripts/check_effective_radius.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import (  # noqa: E402
    add_travel_times,
    coverage_from_matrix,
    get_road_network,
    network_travel_time_matrix,
    snap_to_nodes,
)
from src.optimise import solve_mclp_exact  # noqa: E402

import geopandas as gpd  # noqa: E402


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)

    demand = gpd.read_file(
        directories["processed"] / "demand_surface.gpkg", layer="demand"
    )
    candidates = gpd.read_file(directories["processed"] / "candidates.gpkg")
    weights = demand["orders_per_month"].to_numpy()
    n_stores = int(cfg["optimisation"]["n_stores"])

    graph = get_road_network(cfg)
    candidate_nodes = snap_to_nodes(candidates, graph, cfg)["node_id"].to_numpy()
    demand_nodes = snap_to_nodes(demand, graph, cfg)["node_id"].to_numpy()

    # Pairs chosen to hold speed times threshold roughly constant within a pair
    # and to differ between pairs.
    pairs = [
        ("A", [(18.0, 10.0), (12.0, 15.0), (22.5, 8.0)]),
        ("B", [(18.0, 15.0), (27.0, 10.0), (13.5, 20.0)]),
    ]

    results = []
    for group, combos in pairs:
        print(f"\ngroup {group}")
        group_rows = []
        for speed, threshold in combos:
            radius_m = speed * 1000.0 / 60.0 * threshold
            graph = add_travel_times(graph, cfg, speed_kmph=speed)
            matrix, _ = network_travel_time_matrix(
                graph,
                candidate_nodes,
                demand_nodes,
                cutoff_min=threshold * 1.05,
            )
            cover = coverage_from_matrix(matrix, threshold)
            solution = solve_mclp_exact(cover, weights, n_stores, 300, 0.0)
            row = {
                "group": group,
                "speed_kmph": speed,
                "threshold_min": threshold,
                "effective_radius_m": round(radius_m, 1),
                "coverage_share": solution["coverage_share"],
                "selected": solution["selected"],
                "reachable_pairs": int(cover.sum()),
            }
            group_rows.append(row)
            print(
                f"  {speed:5.1f} km/h x {threshold:4.1f} min = "
                f"{radius_m:6.0f}m road   coverage {solution['coverage_share']:.4f}   "
                f"reachable pairs {int(cover.sum()):,}"
            )

        reference = set(group_rows[0]["selected"])
        for row in group_rows[1:]:
            row["sites_shared_with_first"] = len(reference & set(row["selected"]))
            print(
                f"  sites shared with the first combination: "
                f"{row['sites_shared_with_first']}/{n_stores}"
            )
        results.extend(group_rows)

    shares = [
        r.get("sites_shared_with_first")
        for r in results
        if "sites_shared_with_first" in r
    ]
    verdict = (
        "confirmed: speed and threshold act only through their product"
        if all(s >= n_stores - 1 for s in shares)
        else "not exact: the two do not collapse perfectly, see the shares above"
    )
    print(f"\nverdict: {verdict}")

    out = {"n_stores": n_stores, "results": results, "verdict": verdict}
    path = directories["reports"] / "effective_radius_check.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    return out


if __name__ == "__main__":
    run()
