"""Phase 2: candidate sites, the network travel time matrix, and the comparison.

This is where the project's central claim gets built: coverage measured along
real roads, and the same coverage measured in straight lines, so the difference
between them is a number rather than an assertion.

Run:  python scripts/run_phase2.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.candidates import build_candidates  # noqa: E402
from src.config import load_config, paths  # noqa: E402
from src.network import (  # noqa: E402
    add_travel_times,
    coverage_from_matrix,
    get_road_network,
    haversine_travel_time_matrix,
    network_travel_time_matrix,
    snap_to_nodes,
)


def network_length_km(graph) -> dict:
    """Directed and undirected network length.

    OSMnx returns a MultiDiGraph, so a two way street contributes two edges.
    Summing edge lengths therefore roughly doubles the real centreline length,
    and reporting that number as "road length" would overstate it by a factor of
    two. Both are returned so the right one gets used.
    """
    directed = sum(float(d.get("length", 0.0)) for _, _, d in graph.edges(data=True))
    undirected = sum(
        float(d.get("length", 0.0))
        for _, _, d in graph.to_undirected().edges(data=True)
    )
    return {
        "directed_edge_length_km": round(directed / 1000, 1),
        "undirected_centreline_km": round(undirected / 1000, 1),
    }


def run(speed_kmph: float | None = None) -> dict:
    cfg = load_config()
    directories = paths(cfg)
    started = time.time()

    demand_path = directories["processed"] / "demand_surface.gpkg"
    if not demand_path.exists():
        raise FileNotFoundError("run scripts/run_phase1.py first")
    demand = gpd.read_file(demand_path, layer="demand")
    print(f"demand cells: {len(demand):,}")

    print("loading road network from cache")
    graph = get_road_network(cfg)
    speed = float(speed_kmph or cfg["network"]["effective_speed_kmph"])
    graph = add_travel_times(graph, cfg, speed_kmph=speed)
    lengths = network_length_km(graph)
    print(f"  nodes {graph.number_of_nodes():,}  edges {graph.number_of_edges():,}")
    print(
        f"  centreline {lengths['undirected_centreline_km']:,} km "
        f"(directed edge sum {lengths['directed_edge_length_km']:,} km)"
    )
    print(f"  effective speed: {speed} km/h")

    print("building candidate set")
    candidates, candidate_stats = build_candidates(demand, cfg)
    print(
        f"  parcels fetched {candidate_stats['parcels_fetched']:,}, "
        f"after {candidate_stats['min_separation_m']:.0f}m thinning "
        f"{candidate_stats['after_separation_thinning']:,}, "
        f"final {candidate_stats['final_candidates']:,}"
        + (" (capped)" if candidate_stats["was_capped"] else "")
    )

    print("snapping to network nodes")
    candidate_snap = snap_to_nodes(candidates, graph, cfg)
    demand_snap = snap_to_nodes(demand, graph, cfg)
    print(
        f"  candidate snap distance: median "
        f"{candidate_snap['snap_distance_m'].median():.0f}m, "
        f"p95 {candidate_snap['snap_distance_m'].quantile(0.95):.0f}m, "
        f"max {candidate_snap['snap_distance_m'].max():.0f}m"
    )
    print(
        f"  demand cell snap distance: median "
        f"{demand_snap['snap_distance_m'].median():.0f}m, "
        f"p95 {demand_snap['snap_distance_m'].quantile(0.95):.0f}m, "
        f"max {demand_snap['snap_distance_m'].max():.0f}m"
    )

    cutoff = float(cfg["network"]["matrix_cutoff_min"])
    print(f"building network travel time matrix, cutoff {cutoff} min")
    matrix_started = time.time()
    network_matrix, prune_stats = network_travel_time_matrix(
        graph,
        candidate_snap["node_id"].to_numpy(),
        demand_snap["node_id"].to_numpy(),
        cutoff_min=cutoff,
    )
    matrix_seconds = time.time() - matrix_started
    print(
        f"  {network_matrix.shape[0]} candidates x {network_matrix.shape[1]} cells "
        f"in {matrix_seconds:.0f}s"
    )
    print(
        f"  pruning ratio: {prune_stats['pruning_ratio']:.4f} "
        f"({prune_stats['nodes_expanded']:,} node expansions against "
        f"{prune_stats['nodes_possible']:,} for an uncapped all pairs run)"
    )

    print("building straight line comparison matrix")
    haversine_matrix = haversine_travel_time_matrix(
        candidates, demand, speed_kmph=speed
    )

    threshold = float(cfg["network"]["delivery_threshold_min"])
    network_cover = coverage_from_matrix(network_matrix, threshold)
    straight_cover = coverage_from_matrix(haversine_matrix, threshold)

    weights = demand["orders_per_month"].to_numpy()
    total_weight = float(weights.sum())

    network_reachable = network_cover.any(axis=0)
    straight_reachable = straight_cover.any(axis=0)

    disagreement = network_cover != straight_cover
    optimistic = (straight_cover & ~network_cover).sum()
    pessimistic = (network_cover & ~straight_cover).sum()

    comparison = {
        "threshold_min": threshold,
        "speed_kmph": speed,
        "pairs": int(network_cover.size),
        "pairs_disagreeing": int(disagreement.sum()),
        "pair_disagreement_share": float(disagreement.mean()),
        "straight_line_only_pairs": int(optimistic),
        "network_only_pairs": int(pessimistic),
        "mean_candidate_reach_network": float(network_cover.sum(axis=1).mean()),
        "mean_candidate_reach_straight": float(straight_cover.sum(axis=1).mean()),
        "reach_inflation_factor": float(
            straight_cover.sum() / network_cover.sum() if network_cover.sum() else 0.0
        ),
        "demand_reachable_by_any_network": float(
            weights[network_reachable].sum() / total_weight
        ),
        "demand_reachable_by_any_straight": float(
            weights[straight_reachable].sum() / total_weight
        ),
        "median_network_over_straight_time_ratio": float(
            np.median(
                (
                    network_matrix[np.isfinite(network_matrix) & (haversine_matrix > 0)]
                    / haversine_matrix[
                        np.isfinite(network_matrix) & (haversine_matrix > 0)
                    ]
                )
            )
        ),
    }

    print(
        f"\n  straight line calls {comparison['reach_inflation_factor']:.2f}x "
        f"as many candidate-cell pairs reachable as the network does"
    )
    print(
        f"  the two methods disagree on {comparison['pair_disagreement_share']:.2%} of pairs"
    )
    print(
        f"  median network detour factor: "
        f"{comparison['median_network_over_straight_time_ratio']:.2f}x straight line"
    )

    np.savez_compressed(
        directories["artifacts"] / "travel_time_matrices.npz",
        network=network_matrix,
        straight=haversine_matrix,
        weights=weights,
        candidate_ids=candidates["candidate_id"].to_numpy(),
        cell_ids=demand["cell_id"].to_numpy(),
    )
    candidates_out = candidates.copy()
    candidates_out["node_id"] = candidate_snap["node_id"].to_numpy()
    candidates_out["snap_distance_m"] = candidate_snap["snap_distance_m"].to_numpy()
    candidates_out.to_file(directories["processed"] / "candidates.gpkg", driver="GPKG")

    summary = {
        "network": {
            "nodes": int(graph.number_of_nodes()),
            "edges": int(graph.number_of_edges()),
            **lengths,
            "effective_speed_kmph": speed,
        },
        "candidates": candidate_stats,
        "snapping": {
            "candidate_median_m": float(candidate_snap["snap_distance_m"].median()),
            "candidate_p95_m": float(candidate_snap["snap_distance_m"].quantile(0.95)),
            "candidate_max_m": float(candidate_snap["snap_distance_m"].max()),
            "demand_median_m": float(demand_snap["snap_distance_m"].median()),
            "demand_p95_m": float(demand_snap["snap_distance_m"].quantile(0.95)),
            "demand_max_m": float(demand_snap["snap_distance_m"].max()),
        },
        "matrix": {
            "shape": list(network_matrix.shape),
            "cutoff_min": cutoff,
            "build_seconds": round(matrix_seconds, 1),
            **prune_stats,
        },
        "straight_line_comparison": comparison,
        "runtime_s": round(time.time() - started, 1),
    }

    report_path = directories["reports"] / "phase2_summary.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)
    print(f"\n  wrote {report_path.relative_to(REPO_ROOT)}")
    print(f"  phase 2 done in {summary['runtime_s']}s")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="override the effective rider speed in km/h",
    )
    args = parser.parse_args()
    run(speed_kmph=args.speed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
