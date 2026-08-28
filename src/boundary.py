"""City boundary retrieval.

The boundary is pulled once from OSM Nominatim and cached as GeoJSON, so a
rerun does not depend on a geocoding service being up, and so the analysis
extent is fixed rather than silently changing if OSM data is edited.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from .config import Config, load_config, paths


def _configure_osmnx_cache(interim_dir: Path) -> None:
    import osmnx as ox

    cache_dir = interim_dir / "osm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_console = False


def get_city_boundary(
    cfg: Config | None = None, refresh: bool = False
) -> gpd.GeoDataFrame:
    """Return the city boundary polygon in the projected CRS.

    Cached to data/interim/city_boundary.geojson in geographic coordinates, then
    projected on read, so the cached artefact stays human inspectable.
    """
    cfg = cfg or load_config()
    directories = paths(cfg)
    cache_file = directories["interim"] / "city_boundary.geojson"

    if refresh or not cache_file.exists():
        import osmnx as ox

        _configure_osmnx_cache(directories["interim"])
        gdf = ox.geocode_to_gdf(cfg["city"]["osm_query"])
        gdf = gdf[["geometry"]].copy()
        gdf.to_file(cache_file, driver="GeoJSON")

    boundary = gpd.read_file(cache_file)
    if boundary.crs is None:
        boundary = boundary.set_crs(cfg["city"]["geographic_crs"])
    return boundary.to_crs(cfg["city"]["projected_crs"])


def boundary_area_km2(boundary: gpd.GeoDataFrame) -> float:
    """Area of the boundary in square kilometres, computed in a metric CRS."""
    return float(boundary.geometry.area.sum() / 1e6)
