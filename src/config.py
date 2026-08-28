"""Configuration loading and path resolution.

Every tunable number in this project comes from config/config.yaml. This module
is the only place that reads it, so there is one definition of what a setting
means and one place to look when a result needs to be traced back to an input.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


class Config(dict):
    """A dict with attribute access on the top level sections."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@lru_cache(maxsize=8)
def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read the YAML config and return it, cached by path."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return Config(raw)


def paths(cfg: Config | None = None) -> dict[str, Path]:
    """Resolve the directories the pipeline writes to, creating them if needed."""
    cfg = cfg or load_config()
    out = cfg["output"]
    resolved = {
        "root": REPO_ROOT,
        "raw": REPO_ROOT / "data" / "raw",
        "interim": REPO_ROOT / "data" / "interim",
        "processed": REPO_ROOT / "data" / "processed",
        "reports": REPO_ROOT / out["reports_dir"],
        "figures": REPO_ROOT / out["figures_dir"],
        "artifacts": REPO_ROOT / out["artifacts_dir"],
    }
    for key, directory in resolved.items():
        if key != "root":
            directory.mkdir(parents=True, exist_ok=True)
    return resolved


def population_raster_path(cfg: Config | None = None) -> Path:
    """Absolute path to the cached WorldPop raster."""
    cfg = cfg or load_config()
    return paths(cfg)["raw"] / cfg["population"]["raster_filename"]
