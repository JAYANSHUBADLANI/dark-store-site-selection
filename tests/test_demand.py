"""The demand chain, and specifically the property the variants must preserve."""

import numpy as np
import pytest

from src.config import load_config
from src.demand import VARIANT_EXPONENTS, adoption_rate


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_adoption_rate_is_monotone_in_density(cfg):
    density = np.array([0.0, 1_000.0, 6_000.0, 16_000.0, 31_000.0, 90_000.0])
    rates = adoption_rate(density, cfg=cfg, variant="base")
    assert np.all(np.diff(rates) >= 0)


def test_density_below_the_first_threshold_gets_the_lowest_band(cfg):
    rates = adoption_rate(np.array([0.0]), cfg=cfg, variant="base")
    configured = sorted(
        cfg["demand"]["adoption_rate_by_density"],
        key=lambda b: b["min_density_per_km2"],
    )
    assert rates[0] == pytest.approx(configured[0]["rate"])


@pytest.mark.parametrize("variant", sorted(VARIANT_EXPONENTS))
def test_variants_preserve_the_weighted_mean_adoption_rate(cfg, variant):
    """This is the whole point of the variant design.

    A steeper or flatter curve must change the shape of adoption across the
    city without changing how adoptive the city is overall, otherwise the
    sensitivity run confounds the two effects.
    """
    rng = np.random.default_rng(0)
    density = rng.uniform(0, 60_000, size=5_000)
    weights = rng.uniform(1, 5_000, size=5_000)

    base = adoption_rate(density, cfg=cfg, variant="base", weights=weights)
    other = adoption_rate(density, cfg=cfg, variant=variant, weights=weights)

    base_mean = (base * weights).sum() / weights.sum()
    other_mean = (other * weights).sum() / weights.sum()
    assert other_mean == pytest.approx(base_mean, rel=1e-9)


def test_steep_is_more_dispersed_than_base_and_flat_is_less(cfg):
    rng = np.random.default_rng(1)
    density = rng.uniform(0, 60_000, size=5_000)
    weights = rng.uniform(1, 5_000, size=5_000)

    spreads = {
        variant: adoption_rate(density, cfg=cfg, variant=variant, weights=weights).std()
        for variant in ("flat", "base", "steep")
    }
    assert spreads["flat"] < spreads["base"] < spreads["steep"]


def test_unknown_variant_is_rejected(cfg):
    with pytest.raises(ValueError, match="unknown adoption variant"):
        adoption_rate(np.array([1000.0]), cfg=cfg, variant="aggressive")
