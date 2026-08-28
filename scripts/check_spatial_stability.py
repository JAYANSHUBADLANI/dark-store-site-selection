"""Is the site recommendation unstable, or is the stability metric too strict.

Phase 4 reports that none of the 20 base case sites appear in every scenario,
which reads as a total failure of robustness. But that metric compares candidate
identifiers, and candidates are only thinned to 400m separation, so a solution
that moves a store from one parcel to its neighbour 450m away scores as complete
disagreement while being the same recommendation to a business.

The question a memo actually has to answer is not "is it the same parcel" but
"is it the same neighbourhood". This measures that: for each base case site, how
far is the nearest chosen site in each scenario. If those distances are small,
the recommendation is stable at the level it is actually made at, and the
identifier based metric was measuring the wrong thing.

Run:  python scripts/check_spatial_stability.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402


def run() -> dict:
    cfg = load_config()
    directories = paths(cfg)

    candidates = gpd.read_file(directories["processed"] / "candidates.gpkg")
    with open(
        directories["reports"] / "phase4_sensitivity.json", encoding="utf-8"
    ) as fh:
        phase4 = json.load(fh)

    coords = {
        int(row.candidate_id): (row.geometry.x, row.geometry.y)
        for row in candidates.itertuples()
    }

    scenarios = {
        row["scenario"]: row["selected"]
        for row in phase4["scenarios"]
        if not row["scenario"].startswith("n_stores_")
    }
    base_sites = scenarios["base"]
    others = {k: v for k, v in scenarios.items() if k != "base"}

    print(
        f"comparing {len(base_sites)} base case sites against "
        f"{len(others)} other scenarios\n"
    )

    per_site_distances: dict[int, list[float]] = {s: [] for s in base_sites}
    per_scenario = {}

    for name, sites in others.items():
        target = np.array([coords[s] for s in sites])
        distances = []
        for site in base_sites:
            point = np.array(coords[site])
            d = float(
                np.min(np.hypot(target[:, 0] - point[0], target[:, 1] - point[1]))
            )
            per_site_distances[site].append(d)
            distances.append(d)
        distances = np.array(distances)
        per_scenario[name] = {
            "median_m": float(np.median(distances)),
            "p90_m": float(np.percentile(distances, 90)),
            "max_m": float(distances.max()),
            "within_500m": int((distances <= 500).sum()),
            "within_1000m": int((distances <= 1000).sum()),
        }
        print(
            f"  {name:26s} median {np.median(distances):6.0f}m  "
            f"within 1km: {int((distances <= 1000).sum()):2d}/{len(base_sites)}"
        )

    worst_case = {site: float(np.max(ds)) for site, ds in per_site_distances.items()}
    median_case = {
        site: float(np.median(ds)) for site, ds in per_site_distances.items()
    }

    worst_values = np.array(list(worst_case.values()))
    median_values = np.array(list(median_case.values()))

    robust_1km = [s for s, d in worst_case.items() if d <= 1000]
    robust_2km = [s for s, d in worst_case.items() if d <= 2000]

    print("\nper base case site, distance to the nearest chosen site")
    print(
        f"  worst case across scenarios : median {np.median(worst_values):.0f}m, "
        f"max {worst_values.max():.0f}m"
    )
    print(f"  typical case                : median {np.median(median_values):.0f}m")
    print(
        f"  sites always within 1 km of a chosen site: "
        f"{len(robust_1km)}/{len(base_sites)}"
    )
    print(
        f"  sites always within 2 km                 : "
        f"{len(robust_2km)}/{len(base_sites)}"
    )

    verdict = (
        "stable at neighbourhood level: the identifier metric was too strict"
        if len(robust_1km) >= 0.7 * len(base_sites)
        else "genuinely unstable: the sites move, not just the parcel labels"
    )
    print(f"\nverdict: {verdict}")

    out = {
        "n_base_sites": len(base_sites),
        "n_scenarios_compared": len(others),
        "per_scenario": per_scenario,
        "worst_case_distance_m": {
            "median": float(np.median(worst_values)),
            "p90": float(np.percentile(worst_values, 90)),
            "max": float(worst_values.max()),
        },
        "typical_distance_m_median": float(np.median(median_values)),
        "sites_always_within_1km": len(robust_1km),
        "sites_always_within_2km": len(robust_2km),
        "robust_1km_share": len(robust_1km) / len(base_sites),
        "verdict": verdict,
    }
    path = directories["reports"] / "spatial_stability_check.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n  wrote {path.relative_to(REPO_ROOT)}")
    return out


if __name__ == "__main__":
    run()
