"""GHSL tile index arithmetic.

The Global Human Settlement Layer ships its 100m products as 1000km by 1000km
tiles in the Mollweide projection (ESRI:54009), named R{row}_C{col} with row 1
at the top and column 1 at the far west. Computing the tile from a coordinate
keeps this project pointable at another city without hunting through a tile
schema shapefile by hand.
"""

from __future__ import annotations

from functools import lru_cache

# The GHSL Mollweide tiling origin, in projected metres. Row 1 starts at the
# northern edge and column 1 at the western edge of the global grid.
TILE_SIZE_M = 1_000_000.0
ORIGIN_X_M = -18_041_000.0
ORIGIN_Y_M = 9_000_000.0


@lru_cache(maxsize=32)
def _transformer():
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", "ESRI:54009", always_xy=True)


def mollweide(lon: float, lat: float) -> tuple[float, float]:
    """Project a geographic coordinate into the GHSL Mollweide CRS."""
    return _transformer().transform(lon, lat)


def ghsl_tile_for_point(lon: float, lat: float) -> str:
    """Return the GHSL tile name, for example R8_C26, containing a coordinate."""
    x, y = mollweide(lon, lat)
    col = int((x - ORIGIN_X_M) // TILE_SIZE_M) + 1
    row = int((ORIGIN_Y_M - y) // TILE_SIZE_M) + 1
    return f"R{row}_C{col}"


def ghsl_tile_bounds_m(tile: str) -> tuple[float, float, float, float]:
    """Return the tile's Mollweide bounds as minx, miny, maxx, maxy."""
    row_part, col_part = tile.split("_")
    row = int(row_part.lstrip("R"))
    col = int(col_part.lstrip("C"))
    minx = ORIGIN_X_M + (col - 1) * TILE_SIZE_M
    maxy = ORIGIN_Y_M - (row - 1) * TILE_SIZE_M
    return minx, maxy - TILE_SIZE_M, minx + TILE_SIZE_M, maxy


def ghsl_tile_url(tile: str, cfg) -> str:
    """Build the download URL for a GHSL population tile."""
    product = cfg["population"]["ghsl_product"]
    base = cfg["population"]["ghsl_base_url"].rstrip("/")
    return f"{base}/{product}_{tile}.zip"
