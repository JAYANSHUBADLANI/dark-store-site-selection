"""An interactive map for exploring the result, alongside the static figures.

The static figures are what go in the memo, because they survive being
screenshotted. This is for looking at the thing: panning around the city,
checking why a site landed where it did, and seeing which neighbourhoods sit
outside the promise.

Output is not committed. It is a single self contained HTML file of a few
megabytes, regenerable in seconds.

Run:  python scripts/make_interactive_map.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import coverage_from_matrix  # noqa: E402


def main() -> int:
    import folium

    cfg = load_config()
    directories = paths(cfg)
    geographic = cfg["city"]["geographic_crs"]

    demand = gpd.read_file(
        directories["processed"] / "demand_surface.gpkg", layer="demand"
    )
    candidates = gpd.read_file(directories["processed"] / "candidates.gpkg")
    with open(directories["artifacts"] / "selected_sites.json", encoding="utf-8") as fh:
        sites = json.load(fh)

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    threshold = float(cfg["network"]["delivery_threshold_min"])
    cover = coverage_from_matrix(data["network"], threshold)

    chosen = sites["network_exact"]
    covered = np.zeros(cover.shape[1], dtype=bool)
    for j in chosen:
        covered |= cover[j]

    # Take the map centre in the projected CRS, then transform the single
    # resulting point. Averaging centroids computed in degrees is the same
    # mistake this project avoids everywhere else.
    centre_point = (
        demand.geometry.centroid.union_all().centroid
        if hasattr(demand.geometry.centroid.union_all(), "centroid")
        else demand.geometry.centroid.iloc[0]
    )
    centre_geo = (
        gpd.GeoSeries([centre_point], crs=demand.crs).to_crs(geographic).iloc[0]
    )
    centre = [centre_geo.y, centre_geo.x]

    demand = demand.to_crs(geographic)
    candidates_geo = candidates.to_crs(geographic)
    demand["covered"] = covered
    fmap = folium.Map(location=centre, zoom_start=11, tiles="cartodbpositron")

    orders = demand["orders_per_month"].to_numpy()
    upper = float(np.percentile(orders[orders > 0], 95)) or 1.0

    demand_layer = folium.FeatureGroup(name="Modelled demand", show=True)
    for row in demand.itertuples():
        intensity = min(row.orders_per_month / upper, 1.0)
        folium.Rectangle(
            bounds=[
                [row.geometry.bounds[1], row.geometry.bounds[0]],
                [row.geometry.bounds[3], row.geometry.bounds[2]],
            ],
            color=None,
            fill=True,
            fill_color="#7f1d1d",
            fill_opacity=0.06 + 0.55 * intensity,
            weight=0,
            tooltip=(
                f"{row.orders_per_month:,.0f} orders per month, "
                f"{row.population:,.0f} people"
            ),
        ).add_to(demand_layer)
    demand_layer.add_to(fmap)

    uncovered_layer = folium.FeatureGroup(name="Outside the promise", show=True)
    for row in demand[~demand["covered"]].itertuples():
        folium.Rectangle(
            bounds=[
                [row.geometry.bounds[1], row.geometry.bounds[0]],
                [row.geometry.bounds[3], row.geometry.bounds[2]],
            ],
            color="#1d4ed8",
            fill=True,
            fill_color="#1d4ed8",
            fill_opacity=0.25,
            weight=0.3,
            tooltip=f"not reachable in {threshold:.0f} min",
        ).add_to(uncovered_layer)
    uncovered_layer.add_to(fmap)

    sites_layer = folium.FeatureGroup(
        name="Selected sites, network solution", show=True
    )
    selected = candidates_geo[candidates_geo["candidate_id"].isin(chosen)]
    for row in selected.itertuples():
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=7,
            color="white",
            weight=2,
            fill=True,
            fill_color="#b91c1c",
            fill_opacity=1.0,
            tooltip=(
                f"candidate {row.candidate_id}, {row.landuse}, "
                f"{row.local_orders_per_month:,.0f} orders within reach"
            ),
        ).add_to(sites_layer)
    sites_layer.add_to(fmap)

    others_layer = folium.FeatureGroup(name="Candidates not chosen", show=False)
    for row in candidates_geo[
        ~candidates_geo["candidate_id"].isin(chosen)
    ].itertuples():
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=2,
            color="#475569",
            weight=1,
            fill=True,
            fill_opacity=0.5,
            tooltip=f"candidate {row.candidate_id}, {row.landuse}",
        ).add_to(others_layer)
    others_layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    covered_share = float(orders[covered].sum() / orders.sum())
    caption = (
        f"<div style='position:fixed;bottom:18px;left:18px;z-index:9999;"
        f"background:white;padding:10px 14px;border:1px solid #cbd5e1;"
        f"border-radius:6px;font:13px/1.45 system-ui,sans-serif;max-width:330px'>"
        f"<b>Bengaluru dark store siting</b><br>"
        f"{len(chosen)} stores, {threshold:.0f} minute rider travel time<br>"
        f"Coverage: <b>{covered_share:.1%}</b> of modelled demand<br>"
        f"<span style='color:#b45309'>Those stores can physically serve about "
        f"15% of it. Coverage is not throughput, see the README.</span>"
        f"</div>"
    )
    fmap.get_root().html.add_child(folium.Element(caption))

    out = directories["reports"] / "interactive_map.html"
    fmap.save(str(out))
    size_mb = out.stat().st_size / 1e6
    print(f"wrote {out.relative_to(REPO_ROOT)} ({size_mb:.1f} MB)")
    print(f"coverage shown: {covered_share:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
