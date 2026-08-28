"""Figures for the report and the memo.

Static matplotlib only. Interactive maps are useful while exploring but a memo
needs figures that survive being screenshotted into a deck.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

FIGSIZE = (10, 10)
DPI = 150


def _clean_axes(ax, title: str, subtitle: str | None = None):
    ax.set_axis_off()
    ax.set_title(title, fontsize=14, loc="left", pad=14 if subtitle else 8)
    if subtitle:
        ax.text(
            0.0,
            1.005,
            subtitle,
            transform=ax.transAxes,
            fontsize=9,
            color="#555555",
            va="bottom",
        )
    return ax


def plot_demand_surface(demand, boundary, path):
    fig, ax = plt.subplots(figsize=FIGSIZE)
    boundary.boundary.plot(ax=ax, color="#333333", linewidth=0.8)
    demand.plot(
        column="orders_per_month",
        ax=ax,
        cmap="magma",
        scheme="quantiles",
        k=7,
        legend=True,
        legend_kwds={"title": "orders per month", "loc": "lower right", "fontsize": 8},
        linewidth=0,
    )
    _clean_axes(
        ax,
        "Modelled quick commerce demand, Bengaluru",
        "500m cells, GHS-POP 2020 population through a density based adoption curve",
    )
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_population_distribution(demand, path):
    """The skew is real and worth showing rather than hiding behind a median."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    population = demand["population"].to_numpy()

    axes[0].hist(population, bins=60, color="#3b6ea5")
    axes[0].set_title("Population per 500m cell", fontsize=11, loc="left")
    axes[0].set_xlabel("people")
    axes[0].set_ylabel("cells")

    positive = population[population > 0]
    axes[1].hist(np.log10(positive), bins=60, color="#3b6ea5")
    axes[1].set_title("Same distribution, log10 scale", fontsize=11, loc="left")
    axes[1].set_xlabel("log10 people per cell")
    axes[1].set_ylabel("cells")
    axes[1].axvline(
        np.log10(np.median(positive)),
        color="#c0392b",
        linestyle="--",
        label=f"median {np.median(positive):,.0f}",
    )
    axes[1].axvline(
        np.log10(positive.mean()),
        color="#e67e22",
        linestyle="--",
        label=f"mean {positive.mean():,.0f}",
    )
    axes[1].legend(fontsize=8)

    fig.suptitle(
        "Population is heavily skewed, so the mean cell is not a typical cell",
        fontsize=12,
        x=0.05,
        y=0.99,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_selected_sites(
    demand, boundary, candidates, network_sites, straight_sites, path
):
    fig, axes = plt.subplots(1, 2, figsize=(19, 10.2))

    for ax, sites, label in (
        (axes[0], network_sites, "Chosen on road network travel time"),
        (axes[1], straight_sites, "Chosen on straight line distance"),
    ):
        boundary.boundary.plot(ax=ax, color="#333333", linewidth=0.8)
        demand.plot(
            column="orders_per_month",
            ax=ax,
            cmap="Greys",
            scheme="quantiles",
            k=6,
            linewidth=0,
            alpha=0.75,
        )
        chosen = candidates[candidates["candidate_id"].isin(sites)]
        chosen.plot(
            ax=ax,
            color="#c0392b",
            markersize=90,
            marker="o",
            edgecolor="white",
            linewidth=1.2,
            zorder=5,
        )
        _clean_axes(ax, label)

    fig.suptitle(
        "The two methods select disjoint site sets, not neighbouring ones",
        fontsize=15,
        x=0.06,
        y=0.97,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_coverage_curve(curve, chosen_n, path):
    fig, ax = plt.subplots(figsize=(8, 5))
    ns = [c["n_stores"] for c in curve]
    shares = [c["coverage_share"] for c in curve]

    ax.plot(ns, shares, marker="o", color="#3b6ea5", linewidth=2)
    ax.axvline(
        chosen_n,
        color="#c0392b",
        linestyle="--",
        linewidth=1,
        label=f"{chosen_n} stores",
    )
    ax.set_xlabel("dark stores opened")
    ax.set_ylabel("share of modelled demand within the promise")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    ax.set_title(
        "Coverage against store count, greedy solution", fontsize=12, loc="left"
    )
    ax.text(
        0.0,
        1.03,
        "Greedy is a lower bound on what each store count can achieve",
        transform=ax.transAxes,
        fontsize=9,
        color="#555555",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_reach_comparison(network_matrix, straight_matrix, threshold, path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    network_reach = (network_matrix <= threshold).sum(axis=1)
    straight_reach = (straight_matrix <= threshold).sum(axis=1)

    axes[0].scatter(straight_reach, network_reach, s=14, alpha=0.5, color="#3b6ea5")
    limit = max(straight_reach.max(), network_reach.max()) * 1.05
    axes[0].plot(
        [0, limit],
        [0, limit],
        color="#c0392b",
        linestyle="--",
        linewidth=1,
        label="equal reach",
    )
    axes[0].set_xlabel("cells reached, straight line")
    axes[0].set_ylabel("cells reached, road network")
    axes[0].set_title("Every candidate sits below the line", fontsize=11, loc="left")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    finite = np.isfinite(network_matrix) & (straight_matrix > 0)
    ratio = network_matrix[finite] / straight_matrix[finite]

    # A handful of pairs have very large detour factors, where a cell is close
    # in a straight line but far by road: across a lake, a railway line or a
    # limited access corridor. Those are the cases that justify this whole
    # comparison, but plotted raw they compress everything else into one bar.
    # The axis is clipped to the 99th percentile and the tail is counted in the
    # label rather than dropped silently.
    upper = float(np.percentile(ratio, 99))
    beyond = int((ratio > upper).sum())
    axes[1].hist(ratio[ratio <= upper], bins=70, color="#3b6ea5")
    axes[1].axvline(
        float(np.median(ratio)),
        color="#c0392b",
        linestyle="--",
        label=f"median {np.median(ratio):.2f}x",
    )
    axes[1].set_xlabel("network travel time divided by straight line travel time")
    axes[1].set_ylabel("candidate to cell pairs")
    axes[1].set_title(
        f"Detour factor, clipped at the 99th percentile ({upper:.1f}x). "
        f"{beyond:,} pairs beyond, up to {ratio.max():.0f}x",
        fontsize=10,
        loc="left",
    )
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    fig.suptitle(
        "Straight line distance cannot underestimate travel time, only overstate reach",
        fontsize=13,
        x=0.05,
        y=0.99,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
