"""The obvious rebuttal to the phase 3 finding, tested.

Phase 3 compares a network matrix at speed v against a straight line matrix at
the same speed v. That is not what a practitioner does. Straight line distance is
routinely used with a circuity factor: the speed is calibrated downward so that
straight line travel time approximates road travel time on average. On this city
the median detour factor is about 1.32, so the calibrated straight line speed is
roughly v / 1.32.

If the phase 3 result is just the arithmetic consequence of comparing against an
uncalibrated straw man, it should collapse once the straight line method is given
its fair speed. If it survives, the reason has to be that circuity is not
uniform across the city, so no single factor can absorb it, and that is a
genuinely different and much stronger claim.

This script runs both, so the answer is measured rather than argued.

Run:  python scripts/check_circuity_calibration.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.network import coverage_from_matrix  # noqa: E402
from src.optimise import solve_mclp_exact  # noqa: E402


def score_under(coverage: np.ndarray, weights: np.ndarray, selected: list[int]) -> float:
    covered = np.zeros(coverage.shape[1], dtype=bool)
    for j in selected:
        covered |= coverage[j]
    total = float(weights.sum())
    return float(weights[covered].sum() / total) if total else 0.0


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)

    data = np.load(directories["artifacts"] / "travel_time_matrices.npz")
    network_matrix = data["network"]
    straight_matrix = data["straight"]
    weights = data["weights"]

    threshold = float(cfg["network"]["delivery_threshold_min"])
    n_stores = int(cfg["optimisation"]["n_stores"])

    network_cover = coverage_from_matrix(network_matrix, threshold)

    finite = np.isfinite(network_matrix) & (straight_matrix > 0)
    ratios = network_matrix[finite] / straight_matrix[finite]
    median_detour = float(np.median(ratios))
    mean_detour = float(np.mean(ratios))

    print(f"median detour factor: {median_detour:.4f}")
    print(f"mean detour factor:   {mean_detour:.4f}")
    print(f"detour factor spread: p10 {np.percentile(ratios, 10):.2f}, "
          f"p50 {np.percentile(ratios, 50):.2f}, "
          f"p90 {np.percentile(ratios, 90):.2f}, "
          f"p99 {np.percentile(ratios, 99):.2f}")

    reference = solve_mclp_exact(network_cover, weights, n_stores, 300, 0.0)
    network_optimum = reference["coverage_share"]
    network_sites = set(reference["selected"])
    print(f"\nnetwork optimum: {network_optimum:.4f}\n")

    results = []
    # Uncalibrated is the phase 3 comparison. The rest inflate straight line
    # travel time by a constant factor, which is exactly what calibrating the
    # straight line speed downward does.
    for label, factor in [
        ("uncalibrated (phase 3)", 1.0),
        ("calibrated to median detour", median_detour),
        ("calibrated to mean detour", mean_detour),
        ("over-calibrated 1.5x", 1.5),
    ]:
        adjusted = straight_matrix * factor
        cover = coverage_from_matrix(adjusted, threshold)
        solution = solve_mclp_exact(cover, weights, n_stores, 300, 0.0)
        selected = solution["selected"]

        claimed = solution["coverage_share"]
        actual = score_under(network_cover, weights, selected)
        overlap = len(network_sites & set(selected))

        row = {
            "label": label,
            "straight_line_time_multiplier": round(factor, 4),
            "implied_speed_kmph": round(
                float(cfg["network"]["effective_speed_kmph"]) / factor, 2
            ),
            "claimed_coverage": claimed,
            "actual_coverage_on_network": actual,
            "overstatement": claimed - actual,
            "shortfall_vs_network_optimum": network_optimum - actual,
            "sites_shared_with_network_optimum": overlap,
        }
        results.append(row)
        print(f"{label:30s} speed {row['implied_speed_kmph']:5.1f} km/h  "
              f"claims {claimed:.4f}  actual {actual:.4f}  "
              f"shortfall {row['shortfall_vs_network_optimum']:.4f}  "
              f"shared sites {overlap}/{n_stores}")

    best = min(r["shortfall_vs_network_optimum"] for r in results)
    verdict = (
        "survives: even a fairly calibrated straight line method loses real coverage"
        if best > 0.02
        else "collapses: calibration closes the gap, the phase 3 finding was a straw man"
    )
    print(f"\nbest calibrated shortfall: {best:.4f}")
    print(f"verdict: {verdict}")

    out = {
        "median_detour_factor": median_detour,
        "mean_detour_factor": mean_detour,
        "detour_percentiles": {
            "p10": float(np.percentile(ratios, 10)),
            "p50": float(np.percentile(ratios, 50)),
            "p90": float(np.percentile(ratios, 90)),
            "p99": float(np.percentile(ratios, 99)),
            "max": float(ratios.max()),
        },
        "network_optimum": network_optimum,
        "results": results,
        "best_calibrated_shortfall": best,
        "verdict": verdict,
    }
    path = directories["reports"] / "circuity_calibration_check.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    return out


if __name__ == "__main__":
    run()
