"""Generate every figure used in the README and the memo.

Run:  python scripts/make_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.boundary import get_city_boundary  # noqa: E402
from src.config import load_config, paths  # noqa: E402
from src.viz import (  # noqa: E402
    plot_coverage_curve,
    plot_demand_surface,
    plot_population_distribution,
    plot_reach_comparison,
    plot_selected_sites,
)


def main() -> int:
    cfg = load_config()
    directories = paths(cfg)
    figures = directories["figures"]

    demand = gpd.read_file(
        directories["processed"] / "demand_surface.gpkg", layer="demand"
    )
    candidates = gpd.read_file(directories["processed"] / "candidates.gpkg")
    boundary = get_city_boundary(cfg)

    with open(
        directories["artifacts"] / "selected_sites.json", encoding="utf-8"
    ) as handle:
        sites = json.load(handle)
    with open(
        directories["reports"] / "phase3_summary.json", encoding="utf-8"
    ) as handle:
        phase3 = json.load(handle)

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    threshold = float(cfg["network"]["delivery_threshold_min"])

    print("demand surface")
    plot_demand_surface(demand, boundary, figures / "demand_surface.png")

    print("population distribution")
    plot_population_distribution(demand, figures / "population_distribution.png")

    print("selected sites, network against straight line")
    plot_selected_sites(
        demand,
        boundary,
        candidates,
        sites["network_exact"],
        sites["straight_line"],
        figures / "selected_sites.png",
    )

    print("coverage curve")
    plot_coverage_curve(
        phase3["coverage_curve"], phase3["n_stores"], figures / "coverage_curve.png"
    )

    print("reach comparison")
    plot_reach_comparison(
        data["network"], data["straight"], threshold, figures / "reach_comparison.png"
    )

    written = sorted(p.name for p in figures.glob("*.png"))
    print(f"\nwrote {len(written)} figures to {figures.relative_to(REPO_ROOT)}:")
    for name in written:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
