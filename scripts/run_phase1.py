"""Phase 1: city boundary, analysis grid, population, demand surface.

Writes the demand surface to data/processed/ and a summary to reports/, so
every later phase reads a fixed artefact rather than recomputing this one.

Run:  python scripts/run_phase1.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.boundary import boundary_area_km2, get_city_boundary  # noqa: E402
from src.config import load_config, paths  # noqa: E402
from src.demand import (
    build_demand_surface,
    demand_summary,
    filter_low_demand,
)  # noqa: E402
from src.grid import build_grid  # noqa: E402
from src.population import attach_population, population_summary  # noqa: E402


def run(cell_size_m: float | None = None, variant: str = "base") -> dict:
    cfg = load_config()
    directories = paths(cfg)
    started = time.time()

    print(f"City: {cfg['city']['name']}  CRS: {cfg['city']['projected_crs']}")

    boundary = get_city_boundary(cfg)
    area = boundary_area_km2(boundary)
    print(f"  boundary area: {area:,.1f} sq km")

    cell_size = float(cell_size_m or cfg["grid"]["cell_size_m"])
    grid = build_grid(boundary, cfg, cell_size_m=cell_size)
    print(f"  grid: {len(grid):,} cells at {cell_size:.0f}m")

    grid = attach_population(grid, cfg)
    pop = population_summary(grid)
    print(
        f"  population: {pop['total_population']:,.0f} across "
        f"{pop['populated_cells']:,} populated cells"
    )
    print(
        f"  raster pixels used: {pop['raster_pixels_used']:,}, "
        f"capture ratio vs window: {pop['capture_ratio_vs_window']:.4f}"
    )

    grid = build_demand_surface(grid, cfg, variant=variant)
    grid, dropped = filter_low_demand(grid, cfg)
    print(
        f"  low demand filter: kept {dropped['cells_after']:,} of "
        f"{dropped['cells_before']:,} cells, dropping "
        f"{dropped['population_share_dropped']:.2%} of population and "
        f"{dropped['orders_share_dropped']:.2%} of orders"
    )

    dem = demand_summary(grid)
    print(
        f"  demand: {dem['total_orders_per_month']:,.0f} orders per month, "
        f"population weighted adoption {dem['mean_adoption_rate_pop_weighted']:.3f}"
    )

    suffix = "" if variant == "base" else f"_{variant}"
    if cell_size != float(cfg["grid"]["cell_size_m"]):
        suffix += f"_{int(cell_size)}m"

    out_path = directories["processed"] / f"demand_surface{suffix}.gpkg"
    grid.to_file(out_path, driver="GPKG", layer="demand")

    summary = {
        "city": cfg["city"]["name"],
        "boundary_area_km2": area,
        "cell_size_m": cell_size,
        "adoption_variant": variant,
        "population_source": cfg["population"]["raster_filename"],
        "population_vintage": cfg["population"]["vintage_year"],
        "population": {
            k: (v if not hasattr(v, "item") else v.item())
            for k, v in pop.to_dict().items()
        },
        "low_demand_filter": dropped,
        "demand": {
            k: (v if not hasattr(v, "item") else v.item())
            for k, v in dem.to_dict().items()
        },
        "runtime_s": round(time.time() - started, 1),
        "output_file": str(out_path.relative_to(REPO_ROOT)),
    }

    report_path = directories["reports"] / f"phase1_summary{suffix}.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    print(f"\n  wrote {out_path.relative_to(REPO_ROOT)}")
    print(f"  wrote {report_path.relative_to(REPO_ROOT)}")
    print(f"  phase 1 done in {summary['runtime_s']}s")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cell-size",
        type=float,
        default=None,
        help="override the grid cell size in metres",
    )
    parser.add_argument(
        "--variant",
        default="base",
        choices=["flat", "base", "steep"],
        help="adoption curve variant",
    )
    args = parser.parse_args()
    run(cell_size_m=args.cell_size, variant=args.variant)
    return 0


if __name__ == "__main__":
    sys.exit(main())
