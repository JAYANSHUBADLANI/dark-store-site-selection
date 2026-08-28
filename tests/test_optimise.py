"""Optimisation tests on instances small enough to reason about by hand."""

import numpy as np
import pytest

from src.optimise import (
    optimality_gap,
    site_stability,
    solve_mclp_exact,
    solve_mclp_greedy,
)


@pytest.fixture
def toy():
    """Four candidates, five cells.

    Candidate 0 covers cells 0,1,2 (weight 3+1+1 = 5)
    Candidate 1 covers cells 3,4     (weight 10+10 = 20)
    Candidate 2 covers cell 0        (weight 3)
    Candidate 3 covers cells 1,2     (weight 2)

    With one store the answer is candidate 1. With two it is 1 and 0.
    """
    coverage = np.array(
        [
            [1, 1, 1, 0, 0],
            [0, 0, 0, 1, 1],
            [1, 0, 0, 0, 0],
            [0, 1, 1, 0, 0],
        ],
        dtype=bool,
    )
    weights = np.array([3.0, 1.0, 1.0, 10.0, 10.0])
    return coverage, weights


def test_greedy_picks_the_heaviest_single_site(toy):
    coverage, weights = toy
    result = solve_mclp_greedy(coverage, weights, n_stores=1)
    assert result["selected"] == [1]
    assert result["covered_demand"] == pytest.approx(20.0)


def test_exact_matches_greedy_on_the_toy_instance(toy):
    coverage, weights = toy
    exact = solve_mclp_exact(coverage, weights, n_stores=2, time_limit_s=30)
    greedy = solve_mclp_greedy(coverage, weights, n_stores=2)
    assert exact["selected"] == [0, 1]
    assert greedy["selected"] == [0, 1]
    assert optimality_gap(exact, greedy) == pytest.approx(0.0)


def test_exact_opens_exactly_p_stores(toy):
    coverage, weights = toy
    result = solve_mclp_exact(coverage, weights, n_stores=3, time_limit_s=30)
    assert len(result["selected"]) == 3


def test_greedy_is_beatable_so_the_exact_solve_is_worth_running():
    """A constructed instance where greedy is provably suboptimal.

    Greedy takes candidate 0 first because it covers 6 cells, more than any
    other single candidate. That choice then leaves only 3 new cells available
    from whichever candidate it takes second, so it finishes at 9. The optimum
    is candidates 1 and 2, which overlap nowhere and cover all 12 between them.
    Greedy loses a quarter of the achievable demand here, which is why the
    exact solve exists and is not decorative.
    """
    coverage = np.array(
        [
            [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
            [1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 0],
            [0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1],
        ],
        dtype=bool,
    )
    weights = np.ones(12)

    greedy = solve_mclp_greedy(coverage, weights, n_stores=2)
    exact = solve_mclp_exact(coverage, weights, n_stores=2, time_limit_s=30)

    assert greedy["covered_demand"] == pytest.approx(9.0)
    assert exact["covered_demand"] == pytest.approx(12.0)
    assert greedy["selected"] == [0, 1]
    assert exact["selected"] == [1, 2]
    assert optimality_gap(exact, greedy) == pytest.approx(0.25)


def test_unreachable_cells_are_reported_not_silently_covered():
    coverage = np.array([[1, 0, 0]], dtype=bool)
    weights = np.array([5.0, 5.0, 5.0])
    result = solve_mclp_exact(coverage, weights, n_stores=1, time_limit_s=30)
    assert result["unreachable_cells"] == 2
    assert result["coverage_share"] == pytest.approx(1 / 3)


def test_site_stability_separates_always_from_once():
    solutions = {
        "base": [1, 2, 3],
        "fast": [1, 2, 9],
        "slow": [1, 2, 3],
    }
    stability = site_stability(solutions)
    assert stability["always_selected"] == [1, 2]
    assert stability["single_scenario_only"] == [9]
    assert stability["n_scenarios"] == 3
