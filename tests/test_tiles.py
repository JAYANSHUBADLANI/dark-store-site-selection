"""Tile index arithmetic, checked against coordinates with known tiles."""

from src.tiles import ghsl_tile_bounds_m, ghsl_tile_for_point, mollweide


def test_bengaluru_resolves_to_r8_c26():
    assert ghsl_tile_for_point(77.5946, 12.9716) == "R8_C26"


def test_whole_bengaluru_bbox_is_in_one_tile():
    corners = [
        (77.4598797, 12.8334905),
        (77.7840639, 12.8334905),
        (77.4598797, 13.1426196),
        (77.7840639, 13.1426196),
    ]
    tiles = {ghsl_tile_for_point(lon, lat) for lon, lat in corners}
    assert tiles == {"R8_C26"}


def test_tile_bounds_contain_the_point_that_resolved_to_them():
    x, y = mollweide(77.5946, 12.9716)
    minx, miny, maxx, maxy = ghsl_tile_bounds_m("R8_C26")
    assert minx <= x <= maxx
    assert miny <= y <= maxy


def test_tiles_are_one_thousand_km_square():
    minx, miny, maxx, maxy = ghsl_tile_bounds_m("R8_C26")
    assert maxx - minx == 1_000_000.0
    assert maxy - miny == 1_000_000.0


def test_moving_east_one_tile_width_increments_the_column():
    x, y = mollweide(77.5946, 12.9716)
    minx, _, maxx, _ = ghsl_tile_bounds_m("R8_C26")
    assert maxx - minx == 1_000_000.0
    # A point one tile east of the tile's west edge must sit in column 27.
    from src.tiles import ORIGIN_X_M, ORIGIN_Y_M, TILE_SIZE_M

    col = int((x + TILE_SIZE_M - ORIGIN_X_M) // TILE_SIZE_M) + 1
    row = int((ORIGIN_Y_M - y) // TILE_SIZE_M) + 1
    assert (row, col) == (8, 27)
