"""Road network retrieval and travel time matrices.

This module holds the claim the whole project rests on: that coverage is
measured along real roads rather than in straight lines. Two matrix builders
live here on purpose, the network one and the haversine one, so the comparison
between them is a difference of one function call and not a difference of
codebase.

On cost. The naive formulation is all pairs shortest path between every
candidate and every demand cell, which at 400 candidates and several thousand
cells over a network with 100k plus nodes is far more work than the question
needs. Anything beyond the delivery promise is irrelevant to a covering problem,
so instead this runs one Dijkstra per candidate with a travel time cutoff, which
never expands the far side of the city at all. The pruning ratio is reported,
because it is the justification for the design.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import Config, load_config, paths

EARTH_RADIUS_M = 6_371_008.8


def _configure_osmnx(cfg: Config):
    import osmnx as ox

    cache_dir = paths(cfg)["interim"] / "osm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_console = False
    return ox


def get_road_network(cfg: Config | None = None, refresh: bool = False):
    """Return the drivable road network for the city, projected and cached.

    Cached as GraphML under data/interim/. The pull is the slowest single step
    in the project, so it is done once and reused by every scenario.
    """
    cfg = cfg or load_config()
    ox = _configure_osmnx(cfg)
    cache_file = paths(cfg)["interim"] / "road_network.graphml"

    if refresh or not cache_file.exists():
        from .boundary import get_city_boundary

        boundary = get_city_boundary(cfg).to_crs(cfg["city"]["geographic_crs"])
        polygon = boundary.geometry.union_all()
        graph = ox.graph_from_polygon(
            polygon,
            network_type=cfg["network"]["osm_network_type"],
            simplify=True,
        )
        ox.save_graphml(graph, cache_file)
    else:
        graph = ox.load_graphml(cache_file)

    return ox.project_graph(graph, to_crs=cfg["city"]["projected_crs"])


def add_travel_times(graph, cfg: Config | None = None, speed_kmph: float | None = None):
    """Attach a travel_time attribute in minutes to every edge.

    A single effective speed is used rather than OSM maxspeed tags. Those tags
    are free flow legal limits, most Bengaluru links do not carry one, and a
    two wheeler in city traffic does not travel at either. Using one stated,
    sensitivity tested number is more honest than a per link value that looks
    precise and is not.
    """
    cfg = cfg or load_config()
    speed_kmph = float(speed_kmph or cfg["network"]["effective_speed_kmph"])
    metres_per_minute = speed_kmph * 1000.0 / 60.0

    for _, _, data in graph.edges(data=True):
        length_m = float(data.get("length", 0.0))
        data["travel_time"] = length_m / metres_per_minute

    graph.graph["effective_speed_kmph"] = speed_kmph
    return graph


def snap_to_nodes(
    points: gpd.GeoDataFrame, graph, cfg: Config | None = None
) -> pd.DataFrame:
    """Snap points to their nearest network node.

    Returns the node id and the snap distance. The distance matters: a centroid
    that snaps 400m to reach a road is being modelled as if it sat on that road,
    and the distribution of those distances is reported rather than ignored.
    """
    cfg = cfg or load_config()
    ox = _configure_osmnx(cfg)

    xs = points.geometry.centroid.x.to_numpy()
    ys = points.geometry.centroid.y.to_numpy()
    node_ids, distances = ox.nearest_nodes(graph, xs, ys, return_dist=True)

    return pd.DataFrame(
        {
            "node_id": np.asarray(node_ids),
            "snap_distance_m": np.asarray(distances, dtype="float64"),
        },
        index=points.index,
    )


def network_travel_time_matrix(
    graph,
    origin_nodes: np.ndarray,
    target_nodes: np.ndarray,
    cutoff_min: float,
) -> tuple[np.ndarray, dict]:
    """Travel time in minutes from each origin to each target, capped at cutoff.

    One cutoff bounded Dijkstra per origin. Entries beyond the cutoff are
    returned as infinity, which is what a covering constraint needs: not how far
    away an unreachable cell is, only that it is out of range.
    """
    import networkx as nx

    unique_targets, target_positions = np.unique(target_nodes, return_inverse=True)
    target_index = {node: i for i, node in enumerate(unique_targets)}

    matrix = np.full((len(origin_nodes), len(unique_targets)), np.inf, dtype="float64")
    reached_total = 0

    for row, origin in enumerate(origin_nodes):
        lengths = nx.single_source_dijkstra_path_length(
            graph, origin, cutoff=cutoff_min, weight="travel_time"
        )
        reached_total += len(lengths)
        for node, minutes in lengths.items():
            column = target_index.get(node)
            if column is not None:
                matrix[row, column] = minutes

    expanded = matrix[:, target_positions]
    total_possible = len(origin_nodes) * graph.number_of_nodes()
    expanded_attrs = {
        "nodes_expanded": reached_total,
        "nodes_possible": total_possible,
        "pruning_ratio": (
            1.0 - (reached_total / total_possible) if total_possible else 0.0
        ),
    }
    return expanded, expanded_attrs


def haversine_travel_time_matrix(
    origins: gpd.GeoDataFrame,
    targets: gpd.GeoDataFrame,
    speed_kmph: float,
) -> np.ndarray:
    """Straight line travel time in minutes, the comparison this project exists to make.

    Distances are computed in the projected CRS, so this is a planar straight
    line rather than a great circle one. At city scale in a single UTM zone the
    difference between the two is negligible, and both are wrong in the same
    direction for the same reason: neither of them follows a road.
    """
    ox_ = origins.geometry.centroid.x.to_numpy()[:, None]
    oy = origins.geometry.centroid.y.to_numpy()[:, None]
    tx = targets.geometry.centroid.x.to_numpy()[None, :]
    ty = targets.geometry.centroid.y.to_numpy()[None, :]

    distance_m = np.hypot(ox_ - tx, oy - ty)
    metres_per_minute = speed_kmph * 1000.0 / 60.0
    return distance_m / metres_per_minute


def coverage_from_matrix(matrix: np.ndarray, threshold_min: float) -> np.ndarray:
    """Boolean coverage matrix: True where a candidate reaches a cell in time."""
    return matrix <= threshold_min
