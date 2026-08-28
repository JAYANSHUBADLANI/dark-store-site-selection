"""Is the straight line penalty a real finding, or one unlucky solution.

The phase 3 headline is that a site set chosen on straight line distance covers
far less demand than the network optimum. That comparison rests on one straight
line solution returned by the solver, and the maximal covering problem is known
to have many alternate optima: when 400 candidates can cover 98 percent of
demand, a great many different sets of 20 reach the same objective, and the
solver returns whichever one it happens to reach first.

So the penalty could be an artefact of an unlucky pick rather than a property of
the method. This resamples the straight line optimum by perturbing the demand
weights by a fraction of a percent, which breaks ties differently each time
without meaningfully changing the problem, and scores every resulting site set
under the network truth. If the penalty is real, the whole distribution sits far
below the network optimum. If it is an artefact, the spread will reach up to it.

Run:  python scripts/check_alternate_optima.py --trials 25
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import coverage_from_matrix  # noqa: E402
from src.optimise import solve_mclp_exact  # noqa: E402


def run(trials: int = 25, perturbation: float = 0.001) -> dict:
    cfg = load_config()
    directories = paths(cfg)

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    network_cover = coverage_from_matrix(
        data["network"], cfg["network"]["delivery_threshold_min"]
    )
    straight_cover = coverage_from_matrix(
        data["straight"], cfg["network"]["delivery_threshold_min"]
    )
    weights = data["weights"]
    total = float(weights.sum())

    n_stores = int(cfg["optimisation"]["n_stores"])
    rng = np.random.default_rng(int(cfg["output"]["random_seed"]))

    reference = solve_mclp_exact(network_cover, weights, n_stores, 300, 0.0)
    network_optimum = reference["coverage_share"]
    print(f"network optimum: {network_optimum:.4f}\n")

    actual_shares = []
    claimed_shares = []
    all_sites: list[set[int]] = []

    for trial in range(trials):
        noise = 1.0 + rng.uniform(-perturbation, perturbation, size=weights.shape)
        perturbed = weights * noise

        solution = solve_mclp_exact(straight_cover, perturbed, n_stores, 120, 0.0)
        selected = solution["selected"]
        all_sites.append(set(selected))

        covered = np.zeros(network_cover.shape[1], dtype=bool)
        for j in selected:
            covered |= network_cover[j]
        actual = float(weights[covered].sum() / total)

        claimed_covered = np.zeros(straight_cover.shape[1], dtype=bool)
        for j in selected:
            claimed_covered |= straight_cover[j]
        claimed = float(weights[claimed_covered].sum() / total)

        actual_shares.append(actual)
        claimed_shares.append(claimed)
        print(f"  trial {trial + 1:2d}: claims {claimed:.4f},actual {actual:.4f}")

    actual_shares = np.array(actual_shares)
    site_union = set().union(*all_sites)
    site_intersection = set.intersection(*all_sites) if all_sites else set()

    result = {
        "trials": trials,
        "perturbation": perturbation,
        "network_optimum_share": network_optimum,
        "straight_line_actual_share": {
            "min": float(actual_shares.min()),
            "median": float(np.median(actual_shares)),
            "max": float(actual_shares.max()),
            "mean": float(actual_shares.mean()),
            "std": float(actual_shares.std()),
        },
        "straight_line_claimed_share_median": float(np.median(claimed_shares)),
        "worst_case_penalty": float(network_optimum - actual_shares.min()),
        "best_case_penalty": float(network_optimum - actual_shares.max()),
        "any_trial_reaches_network_optimum": bool(
            (actual_shares >= network_optimum - 1e-9).any()
        ),
        "distinct_sites_used_across_trials": len(site_union),
        "sites_common_to_every_trial": len(site_intersection),
    }

    print("\nstraight line solutions scored on the network:")
    print(f"  best  {actual_shares.max():.4f}")
    print(f"  median {np.median(actual_shares):.4f}")
    print(f"  worst {actual_shares.min():.4f}")
    print(f"  network optimum {network_optimum:.4f}")
    print(
        f"  even the best straight line solution falls short by "
        f"{network_optimum - actual_shares.max():.4f}"
    )
    print(
        f"  {len(site_union)} distinct sites used across {trials} trials, "
        f"{len(site_intersection)} common to all"
    )

    out = directories["reports"] / "alternate_optima_check.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(f"\n  wrote {out.relative_to(REPO_ROOT)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument("--perturbation", type=float, default=0.001)
    args = parser.parse_args()
    run(trials=args.trials, perturbation=args.perturbation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
