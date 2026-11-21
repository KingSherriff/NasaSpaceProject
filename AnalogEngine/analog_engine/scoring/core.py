"""Scoring machinery shared by all applications.

Suitability (gate + hard condition) decides whether a cell gets a label; Moon vs Mars compares two
target profiles; quality = max(moon, mars) ranks cells within a label. docs/LAYER_MATH.md §13.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypedDict

import numpy as np
import pandas as pd

from ..common import FloatArray

MARGIN: float = 0.03  # |moon - mars| below this -> "both"

Direction = Literal["max", "min", "eq"]
"""max: only too high is bad (dryness, cold); min: only too low is bad (proximity, bare ground)."""


class Profile(TypedDict, total=False):
    target: dict[str, float]
    weights: dict[str, float]
    dir: dict[str, Direction]


Mask = Callable[[pd.DataFrame], "pd.Series[bool]"]


@dataclass
class Application:
    """One activity, e.g. cave exploration.

    gate      activity is plausible here -> scores are computed (0 outside)
    site      hard condition on top of the gate -> the cell gets a label
    profiles  {"moon": Profile, "mars": Profile}
    show      extra columns for the top-N table
    """

    name: str
    gate: Mask
    site: Mask
    profiles: dict[str, Profile]
    show: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)


def score(df: pd.DataFrame, spec: Profile, gate: "pd.Series[bool] | np.ndarray") -> FloatArray:
    """1 - weighted RMS of directional differences to the target; 0 outside the gate.

    A NaN feature drops out of both the numerator and the weight sum.
    """
    cols = list(spec["target"])
    w = np.array([spec["weights"][c] for c in cols], dtype=float)
    X = df[cols].to_numpy(dtype=float)
    t = np.array([spec["target"][c] for c in cols], dtype=float)
    dirs = [spec.get("dir", {}).get(c, "eq") for c in cols]

    diff = X - t
    for j, dname in enumerate(dirs):
        if dname == "max":
            diff[:, j] = np.maximum(diff[:, j], 0)
        elif dname == "min":
            diff[:, j] = np.minimum(diff[:, j], 0)

    valid = ~np.isnan(X)
    d = np.sqrt(np.nansum(w * diff**2, axis=1) / (valid * w).sum(axis=1))
    return np.where(gate, 1 - d, 0.0)


def apply(cells: pd.DataFrame, app: Application) -> pd.DataFrame:
    """Add score_<app>_moon, score_<app>_mars, label_<app>, <app>_quality to cells (in place)."""
    missing = [c for c in app.requires if c not in cells]
    if missing:
        raise ValueError(f"{app.name}: missing columns {missing}")
    gate = app.gate(cells)
    is_site = gate & app.site(cells)
    for body, spec in app.profiles.items():
        cells[f"score_{app.name}_{body}"] = score(cells, spec, gate)
    moon, mars = cells[f"score_{app.name}_moon"], cells[f"score_{app.name}_mars"]
    body = np.where((moon - mars).abs() < MARGIN, "both", np.where(moon > mars, "moon", "mars"))
    cells[f"label_{app.name}"] = np.where(is_site, body, "")
    cells[f"{app.name}_quality"] = np.where(is_site, np.maximum(moon, mars), 0.0)
    print(f"{app.name}: gate {gate.sum():,} cells, sites {is_site.sum():,} cells,",
          cells[f"label_{app.name}"].replace("", "none").value_counts().to_dict())
    return cells


def top(cells: pd.DataFrame, app: Application, n: int = 10) -> pd.DataFrame:
    """Best-quality labelled cells of one application."""
    cols = ["cell_id", "lat", "lon", *app.show,
            f"score_{app.name}_moon", f"score_{app.name}_mars", f"label_{app.name}"]
    return cells[cells[f"label_{app.name}"] != ""].nlargest(n, f"{app.name}_quality")[cols].round(2)
