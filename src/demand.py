"""The demand surface: from people on a raster to orders per month per cell.

Every step here is a proxy, and the chain is short enough to state in one line:

    population -> households -> adopting households -> orders per month

The weakest link by a wide margin is the adoption rate. Quick commerce adoption
is not uniform across a city, it concentrates in dense, younger, higher income
neighbourhoods, and there is no public dataset of it at grid level. Density is
used as the only available proxy. That is a real limitation, not a rounding
detail, and it is why the adoption curve is the first thing the sensitivity
analysis attacks.

The three adoption variants (flat, base, steep) change the *shape* of the curve
while holding the population weighted mean adoption rate fixed at the base case
level. That separation matters: without it, making the curve steeper would also
make the city as a whole more or less adoptive, and the two effects could not be
told apart in the results.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import Config, load_config

VARIANT_EXPONENTS = {"flat": 0.5, "base": 1.0, "steep": 2.0}


def _band_rates(cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """Return the density thresholds and their adoption rates, ascending."""
    bands = sorted(
        cfg["demand"]["adoption_rate_by_density"],
        key=lambda b: b["min_density_per_km2"],
    )
    thresholds = np.array([b["min_density_per_km2"] for b in bands], dtype="float64")
    rates = np.array([b["rate"] for b in bands], dtype="float64")
    return thresholds, rates


def adoption_rate(
    density_per_km2: np.ndarray,
    cfg: Config | None = None,
    variant: str = "base",
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """Map population density to an adoption rate using the configured bands.

    `variant` reshapes the curve while preserving the weighted mean rate of the
    base case, so a sensitivity run isolates curve shape from overall level.
    """
    cfg = cfg or load_config()
    if variant not in VARIANT_EXPONENTS:
        raise ValueError(
            f"unknown adoption variant {variant!r}, "
            f"expected one of {sorted(VARIANT_EXPONENTS)}"
        )

    thresholds, rates = _band_rates(cfg)
    index = np.searchsorted(thresholds, density_per_km2, side="right") - 1
    index = np.clip(index, 0, len(rates) - 1)
    base = rates[index]

    if variant == "base":
        return base

    gamma = VARIANT_EXPONENTS[variant]
    reshaped = np.power(base, gamma)

    # Rescale so the weighted mean adoption rate matches the base case.
    if weights is None:
        weights = np.ones_like(base)
    total_weight = weights.sum()
    if total_weight <= 0 or reshaped.sum() <= 0:
        return base
    base_mean = float((base * weights).sum() / total_weight)
    reshaped_mean = float((reshaped * weights).sum() / total_weight)
    scaled = reshaped * (base_mean / reshaped_mean)
    return np.clip(scaled, 0.0, 1.0)


def build_demand_surface(
    grid: gpd.GeoDataFrame,
    cfg: Config | None = None,
    variant: str = "base",
) -> gpd.GeoDataFrame:
    """Add households, adoption rate and monthly orders to a populated grid."""
    cfg = cfg or load_config()
    demand_cfg = cfg["demand"]

    out = grid.copy()
    out["density_per_km2"] = out["population"] / out["area_km2"]
    out["households"] = out["population"] / float(demand_cfg["household_size"])
    out["adoption_rate"] = adoption_rate(
        out["density_per_km2"].to_numpy(),
        cfg=cfg,
        variant=variant,
        weights=out["population"].to_numpy(),
    )
    out["adopting_households"] = out["households"] * out["adoption_rate"]
    out["orders_per_month"] = out["adopting_households"] * float(
        demand_cfg["orders_per_adopting_household_per_month"]
    )
    # The optimiser only ever needs relative weight. Absolute orders are carried
    # for the memo, where the assumption chain behind them is stated in full.
    total = float(out["orders_per_month"].sum())
    out["demand_weight"] = out["orders_per_month"] / total if total else 0.0
    out.attrs["adoption_variant"] = variant
    return out


def filter_low_demand(
    grid: gpd.GeoDataFrame, cfg: Config | None = None
) -> tuple[gpd.GeoDataFrame, dict]:
    """Drop near empty cells before the travel time matrix is built.

    These cells contribute almost nothing to demand but they dominate the cost
    of the matrix, which is linear in cell count. The share of population and
    orders dropped is returned so it can be reported rather than assumed small.
    """
    cfg = cfg or load_config()
    density_threshold = float(cfg["grid"]["min_population_density_per_km2"])
    # Convert to a per cell count using this grid's own cell area, so the filter
    # means the same thing at every resolution.
    cell_area_km2 = float(grid["area_km2"].iloc[0]) if len(grid) else 0.0
    threshold = density_threshold * cell_area_km2

    keep = grid["population"] >= threshold
    dropped = {
        "threshold_density_per_km2": density_threshold,
        "threshold_population": threshold,
        "cell_area_km2": cell_area_km2,
        "cells_before": int(len(grid)),
        "cells_after": int(keep.sum()),
        "cells_dropped": int((~keep).sum()),
        "population_share_dropped": (
            float(grid.loc[~keep, "population"].sum() / grid["population"].sum())
            if grid["population"].sum()
            else 0.0
        ),
        "orders_share_dropped": (
            float(
                grid.loc[~keep, "orders_per_month"].sum()
                / grid["orders_per_month"].sum()
            )
            if grid["orders_per_month"].sum()
            else 0.0
        ),
    }
    return grid.loc[keep].reset_index(drop=True), dropped


def demand_summary(grid: gpd.GeoDataFrame) -> pd.Series:
    """Headline numbers about the demand layer, for the run report."""
    return pd.Series(
        {
            "adoption_variant": grid.attrs.get("adoption_variant", "base"),
            "cells": int(len(grid)),
            "total_population": float(grid["population"].sum()),
            "total_households": float(grid["households"].sum()),
            "mean_adoption_rate_pop_weighted": (
                float(
                    (grid["adoption_rate"] * grid["population"]).sum()
                    / grid["population"].sum()
                )
                if grid["population"].sum()
                else 0.0
            ),
            "total_orders_per_month": float(grid["orders_per_month"].sum()),
            "max_cell_orders_per_month": float(grid["orders_per_month"].max()),
        }
    )
