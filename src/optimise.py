"""Maximal Covering Location Problem, solved exactly and greedily.

The formulation, written out so it can be checked rather than trusted:

    sets
        I   demand cells, each with weight w_i
        J   candidate sites
        N_i subset of J that can reach cell i within the delivery threshold

    variables
        x_j in {0,1}   open a store at candidate j
        y_i in {0,1}   cell i is covered

    maximise    sum_i w_i * y_i
    subject to  y_i <= sum_{j in N_i} x_j     for all i
                sum_j x_j = p
                x, y binary

The coverage constraint is one directional on purpose. Nothing forces y_i to 1
when a cell is reachable, but since w_i is positive and the objective is a
maximisation, the solver sets it anyway. Writing it as an equality would be
redundant and would slow the solve.

This is the classic Church and ReVelle 1974 MCLP. It is NP-hard, which is why
the greedy heuristic is here too: not as a fallback, but as a baseline, so the
value of doing the exact solve can be stated as a number instead of assumed.
"""

from __future__ import annotations

import time

import numpy as np


def solve_mclp_greedy(coverage: np.ndarray, weights: np.ndarray, n_stores: int) -> dict:
    """Greedy maximal coverage: repeatedly take the best marginal candidate.

    The greedy algorithm for maximum coverage has a known guarantee of
    1 - 1/e, roughly 63 percent of the optimum, and in practice on this kind of
    instance it lands far closer than that. Reporting the realised gap against
    the exact solve is more informative than quoting the worst case bound.
    """
    started = time.time()
    n_candidates, n_cells = coverage.shape

    selected: list[int] = []
    covered = np.zeros(n_cells, dtype=bool)
    trace: list[dict] = []

    for _ in range(min(n_stores, n_candidates)):
        marginal = (coverage & ~covered) @ weights
        if selected:
            marginal[np.array(selected)] = -np.inf
        best = int(np.argmax(marginal))
        if marginal[best] <= 0:
            break
        selected.append(best)
        covered |= coverage[best]
        trace.append(
            {
                "store": len(selected),
                "candidate_id": best,
                "marginal_demand": float(marginal[best]),
                "cumulative_demand": float(weights[covered].sum()),
            }
        )

    total = float(weights.sum())
    return {
        "method": "greedy",
        "selected": sorted(selected),
        "covered_demand": float(weights[covered].sum()),
        "total_demand": total,
        "coverage_share": float(weights[covered].sum() / total) if total else 0.0,
        "covered_cells": int(covered.sum()),
        "trace": trace,
        "runtime_s": round(time.time() - started, 2),
    }


def solve_mclp_exact(
    coverage: np.ndarray,
    weights: np.ndarray,
    n_stores: int,
    time_limit_s: int = 300,
    mip_gap: float = 0.01,
) -> dict:
    """Solve the MCLP with CBC through PuLP.

    Reports whether optimality was actually proven. A solve that hit the time
    limit returns an incumbent, and presenting an incumbent as an optimum is the
    kind of quiet overclaim this project is trying to avoid.
    """
    import pulp

    started = time.time()
    n_candidates, n_cells = coverage.shape

    problem = pulp.LpProblem("mclp", pulp.LpMaximize)

    x = [pulp.LpVariable(f"x_{j}", cat="Binary") for j in range(n_candidates)]
    y = [pulp.LpVariable(f"y_{i}", cat="Binary") for i in range(n_cells)]

    problem += pulp.lpSum(float(weights[i]) * y[i] for i in range(n_cells))

    # Only cells that at least one candidate can reach get a constraint. A cell
    # nothing reaches is fixed to zero instead, which keeps the model smaller.
    reachable_by = [np.nonzero(coverage[:, i])[0] for i in range(n_cells)]
    unreachable = 0
    for i in range(n_cells):
        js = reachable_by[i]
        if len(js) == 0:
            problem += y[i] == 0
            unreachable += 1
        else:
            problem += y[i] <= pulp.lpSum(x[int(j)] for j in js)

    problem += pulp.lpSum(x) == int(n_stores)

    solver = pulp.PULP_CBC_CMD(
        msg=False, timeLimit=int(time_limit_s), gapRel=float(mip_gap)
    )
    problem.solve(solver)

    status = pulp.LpStatus[problem.status]
    selected = [j for j in range(n_candidates) if x[j].value() and x[j].value() > 0.5]
    covered = np.zeros(n_cells, dtype=bool)
    for j in selected:
        covered |= coverage[j]

    total = float(weights.sum())
    runtime = time.time() - started

    return {
        "method": "exact_cbc",
        "status": status,
        "proved_optimal": status == "Optimal" and runtime < time_limit_s * 0.99,
        "hit_time_limit": runtime >= time_limit_s * 0.99,
        "mip_gap_requested": float(mip_gap),
        "selected": sorted(selected),
        "covered_demand": float(weights[covered].sum()),
        "total_demand": total,
        "coverage_share": float(weights[covered].sum() / total) if total else 0.0,
        "covered_cells": int(covered.sum()),
        "unreachable_cells": int(unreachable),
        "objective_value": float(pulp.value(problem.objective) or 0.0),
        "runtime_s": round(runtime, 2),
    }


def optimality_gap(exact: dict, greedy: dict) -> float:
    """How much demand the greedy solution leaves on the table, as a share."""
    if not exact["covered_demand"]:
        return 0.0
    return float(
        (exact["covered_demand"] - greedy["covered_demand"]) / exact["covered_demand"]
    )


def site_stability(solutions: dict[str, list[int]]) -> dict:
    """How often each site appears across a set of scenario solutions.

    A site chosen under every assumption is a materially different
    recommendation from one that only appears in the base case, and the memo
    should not present them as if they carry the same confidence.
    """
    counts: dict[int, int] = {}
    for selected in solutions.values():
        for site in selected:
            counts[site] = counts.get(site, 0) + 1

    n_scenarios = len(solutions)
    return {
        "n_scenarios": n_scenarios,
        "site_frequency": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "always_selected": sorted(s for s, c in counts.items() if c == n_scenarios),
        "single_scenario_only": sorted(s for s, c in counts.items() if c == 1),
    }
