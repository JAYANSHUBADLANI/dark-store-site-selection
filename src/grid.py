"""Analysis grid construction.

Demand is modelled on a square grid over the city boundary. The grid is built in
the projected CRS so cells are equal area in square metres, which they would not
be if built in degrees.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from .config import Config, load_config


def build_grid(
    boundary: gpd.GeoDataFrame,
    cfg: Config | None = None,
    cell_size_m: float | None = None,
) -> gpd.GeoDataFrame:
    """Build a square analysis grid clipped to the city boundary.

    Returns one row per cell with a stable integer cell_id, the cell polygon and
    its centroid. Cells are retained if their centroid falls inside the boundary,
    which keeps every cell a full square and avoids slivers along the edge.
    """
    cfg = cfg or load_config()
    cell_size_m = float(cell_size_m or cfg["grid"]["cell_size_m"])

    minx, miny, maxx, maxy = boundary.total_bounds
    xs = np.arange(minx, maxx + cell_size_m, cell_size_m)
    ys = np.arange(miny, maxy + cell_size_m, cell_size_m)

    cells = [box(x, y, x + cell_size_m, y + cell_size_m) for x in xs for y in ys]
    grid = gpd.GeoDataFrame({"geometry": cells}, crs=boundary.crs)

    union = boundary.geometry.union_all()
    inside = grid.geometry.centroid.within(union)
    grid = grid.loc[inside].reset_index(drop=True)

    grid["cell_id"] = np.arange(len(grid), dtype=np.int64)
    centroids = grid.geometry.centroid
    grid["x"] = centroids.x.to_numpy()
    grid["y"] = centroids.y.to_numpy()
    grid["area_km2"] = (cell_size_m**2) / 1e6
    return grid[["cell_id", "x", "y", "area_km2", "geometry"]]
