"""Candidate dark store sites.

A dark store cannot go on an arbitrary grid point, so candidates are drawn from
OSM land use polygons that plausibly host one: retail, commercial and industrial
parcels. This is a filter on physical plausibility only. It says nothing about
whether a lease is available, what the rent is, whether the landlord will take a
warehouse tenant, whether there is three phase power and backup, or whether
loading a fleet of two wheelers at 7am is going to survive contact with the
neighbours. Those constraints decide real sites and none of them are in OSM.

What this module produces is therefore the set of places a store could go, not
the set it could be opened in. The optimiser answers "where is best given
coverage", and the memo has to say that plainly.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import Config, load_config, paths


def fetch_candidate_parcels(
    cfg: Config | None = None, refresh: bool = False
) -> gpd.GeoDataFrame:
    """Pull land use polygons from OSM and return their centroids, cached."""
    cfg = cfg or load_config()
    from .network import _configure_osmnx

    ox = _configure_osmnx(cfg)
    cache_file = paths(cfg)["interim"] / "candidate_parcels.gpkg"

    if not refresh and cache_file.exists():
        return gpd.read_file(cache_file).to_crs(cfg["city"]["projected_crs"])

    from .boundary import get_city_boundary

    boundary = get_city_boundary(cfg).to_crs(cfg["city"]["geographic_crs"])
    polygon = boundary.geometry.union_all()

    tags = {"landuse": list(cfg["candidates"]["osm_landuse_tags"])}
    features = ox.features_from_polygon(polygon, tags)

    features = features[features.geometry.notna()].copy()
    features = features[features.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    features = features.to_crs(cfg["city"]["projected_crs"])
    # OSM features come back on a (element_type, osmid) MultiIndex. Everything
    # below builds plain arrays, so flatten the index first rather than letting
    # pandas try to align a MultiIndex against a RangeIndex.
    features = features.reset_index(drop=True)

    parcels = gpd.GeoDataFrame(
        {
            "landuse": features["landuse"].astype(str).to_numpy(),
            "parcel_area_m2": features.geometry.area.to_numpy(),
        },
        geometry=features.geometry.centroid,
        crs=cfg["city"]["projected_crs"],
    ).reset_index(drop=True)

    parcels.to_file(cache_file, driver="GPKG")
    return parcels


def _local_demand(
    parcels: gpd.GeoDataFrame, demand: gpd.GeoDataFrame, radius_m: float
) -> np.ndarray:
    """Total monthly orders within a radius of each parcel centroid.

    Used only to rank candidates when the set has to be capped, so the cap drops
    parcels sitting in empty land rather than dropping them arbitrarily.
    """
    buffered = parcels.copy()
    buffered["geometry"] = buffered.geometry.buffer(radius_m)
    joined = gpd.sjoin(
        demand[["orders_per_month", "geometry"]],
        buffered[["geometry"]],
        how="inner",
        predicate="within",
    )
    totals = joined.groupby("index_right")["orders_per_month"].sum()
    return parcels.index.map(totals).to_numpy(dtype="float64", na_value=0.0)


def thin_by_separation(
    parcels: gpd.GeoDataFrame, min_separation_m: float, priority: np.ndarray
) -> gpd.GeoDataFrame:
    """Greedily keep the highest priority parcel in each separation radius.

    Without this the candidate set piles up along a few commercial strips, and
    the optimiser spends its budget distinguishing between sites 30m apart that
    cover almost identical demand.
    """
    order = np.argsort(-priority)
    coordinates = np.column_stack(
        [parcels.geometry.x.to_numpy(), parcels.geometry.y.to_numpy()]
    )

    from scipy.spatial import cKDTree

    tree = cKDTree(coordinates)
    blocked = np.zeros(len(parcels), dtype=bool)
    kept: list[int] = []

    for idx in order:
        if blocked[idx]:
            continue
        kept.append(int(idx))
        neighbours = tree.query_ball_point(coordinates[idx], r=min_separation_m)
        blocked[neighbours] = True

    return parcels.iloc[sorted(kept)].reset_index(drop=True)


def build_candidates(
    demand: gpd.GeoDataFrame, cfg: Config | None = None, refresh: bool = False
) -> tuple[gpd.GeoDataFrame, dict]:
    """Fetch, thin and cap the candidate site set."""
    cfg = cfg or load_config()
    candidates_cfg = cfg["candidates"]

    parcels = fetch_candidate_parcels(cfg, refresh=refresh)
    fetched = len(parcels)

    radius_m = float(cfg["network"]["delivery_threshold_min"]) * (
        float(cfg["network"]["effective_speed_kmph"]) * 1000.0 / 60.0
    )
    priority = _local_demand(parcels, demand, radius_m)

    thinned = thin_by_separation(
        parcels, float(candidates_cfg["min_separation_m"]), priority
    )
    after_thinning = len(thinned)

    thinned_priority = _local_demand(thinned, demand, radius_m)
    thinned = thinned.assign(local_orders_per_month=thinned_priority)

    max_candidates = int(candidates_cfg["max_candidates"])
    if len(thinned) > max_candidates:
        thinned = (
            thinned.sort_values("local_orders_per_month", ascending=False)
            .head(max_candidates)
            .reset_index(drop=True)
        )

    thinned["candidate_id"] = np.arange(len(thinned), dtype=np.int64)
    thinned = thinned[
        [
            "candidate_id",
            "landuse",
            "parcel_area_m2",
            "local_orders_per_month",
            "geometry",
        ]
    ]

    stats = {
        "parcels_fetched": fetched,
        "after_separation_thinning": after_thinning,
        "min_separation_m": float(candidates_cfg["min_separation_m"]),
        "final_candidates": int(len(thinned)),
        "capped_at": max_candidates,
        "was_capped": after_thinning > max_candidates,
        "landuse_mix": thinned["landuse"].value_counts().to_dict(),
    }
    return thinned, stats


def candidate_summary(candidates: gpd.GeoDataFrame) -> pd.Series:
    return pd.Series(
        {
            "candidates": int(len(candidates)),
            "median_parcel_area_m2": float(candidates["parcel_area_m2"].median()),
            "median_local_orders": float(candidates["local_orders_per_month"].median()),
        }
    )
