"""Population aggregation from the GHS-POP raster onto the analysis grid.

Two things about this are deliberate and worth stating, because getting either
wrong quietly corrupts every number downstream.

First, GHS-POP values are residential population counts per 100m cell, not a
density. Aggregating therefore means summing the pixels that fall inside each
analysis cell. Averaging or bilinear sampling would both be wrong.

Second, the raster is never reprojected. Reprojecting a count raster resamples
it, and resampling redistributes counts across cells, so the total stops being
conserved and dense pixels bleed into their neighbours. Instead the pixel
centres are transformed as points into the working CRS and joined to the grid.
That is exact: every pixel lands in exactly one cell and nothing is invented or
lost.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

from .config import Config, load_config, paths


def population_raster_path(cfg: Config | None = None) -> Path:
    cfg = cfg or load_config()
    return paths(cfg)["raw"] / cfg["population"]["raster_filename"]


def _window_for_bounds(src, bounds_raster_crs, pad_pixels: int = 2):
    """A rounded, padded raster window covering the given bounds."""
    window = from_bounds(*bounds_raster_crs, src.transform)
    window = window.round_offsets().round_lengths()
    col_off = max(0, int(window.col_off) - pad_pixels)
    row_off = max(0, int(window.row_off) - pad_pixels)
    width = min(src.width - col_off, int(window.width) + 2 * pad_pixels)
    height = min(src.height - row_off, int(window.height) + 2 * pad_pixels)
    return rasterio.windows.Window(col_off, row_off, width, height)


def attach_population(
    grid: gpd.GeoDataFrame,
    cfg: Config | None = None,
    raster_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Add a population column to the grid by summing raster pixels per cell."""
    cfg = cfg or load_config()
    raster_path = Path(raster_path or population_raster_path(cfg))
    if not raster_path.exists():
        raise FileNotFoundError(
            f"population raster not found at {raster_path}. "
            "Run: python scripts/fetch_data.py"
        )

    projected_crs = cfg["city"]["projected_crs"]
    if str(grid.crs) != str(projected_crs):
        raise ValueError(f"expected the grid in {projected_crs}, found {grid.crs}")

    with rasterio.open(raster_path) as src:
        raster_crs = src.crs
        to_raster = Transformer.from_crs(projected_crs, raster_crs, always_xy=True)
        minx, miny, maxx, maxy = grid.total_bounds
        corners_x, corners_y = to_raster.transform(
            [minx, maxx, minx, maxx], [miny, miny, maxy, maxy]
        )
        bounds_raster = (min(corners_x), min(corners_y), max(corners_x), max(corners_y))

        window = _window_for_bounds(src, bounds_raster)
        values = src.read(1, window=window).astype("float64")
        transform = src.window_transform(window)
        nodata = src.nodata

    if nodata is not None:
        values = np.where(values == nodata, 0.0, values)
    values = np.nan_to_num(values, nan=0.0)
    values = np.where(values < 0, 0.0, values)

    rows, cols = np.nonzero(values)
    out = grid.copy()
    if rows.size == 0:
        out["population"] = 0.0
        out.attrs["population_capture_ratio"] = 0.0
        out.attrs["population_in_window"] = 0.0
        return out

    weights = values[rows, cols]
    raster_x, raster_y = rasterio.transform.xy(transform, rows, cols, offset="center")

    to_projected = Transformer.from_crs(raster_crs, projected_crs, always_xy=True)
    px, py = to_projected.transform(np.asarray(raster_x), np.asarray(raster_y))

    pixels = gpd.GeoDataFrame(
        {"population": weights},
        geometry=gpd.points_from_xy(px, py),
        crs=projected_crs,
    )

    joined = gpd.sjoin(
        pixels, grid[["cell_id", "geometry"]], how="inner", predicate="within"
    )
    totals = joined.groupby("cell_id")["population"].sum()

    out["population"] = out["cell_id"].map(totals).fillna(0.0).astype("float64")
    out.attrs["population_in_window"] = float(weights.sum())
    out.attrs["population_capture_ratio"] = (
        float(out["population"].sum()) / float(weights.sum()) if weights.sum() else 0.0
    )
    out.attrs["raster_pixels_used"] = int(rows.size)
    return out


def population_summary(grid: gpd.GeoDataFrame) -> pd.Series:
    """Headline numbers about the population layer, for the run report."""
    population = grid["population"]
    populated = population[population > 0]
    return pd.Series(
        {
            "cells": int(len(grid)),
            "populated_cells": int((population > 0).sum()),
            "total_population": float(population.sum()),
            "median_populated_cell": (
                float(populated.median()) if len(populated) else 0.0
            ),
            "max_cell": float(population.max()),
            "raster_pixels_used": int(grid.attrs.get("raster_pixels_used", 0)),
            "capture_ratio_vs_window": float(
                grid.attrs.get("population_capture_ratio", float("nan"))
            ),
        }
    )
