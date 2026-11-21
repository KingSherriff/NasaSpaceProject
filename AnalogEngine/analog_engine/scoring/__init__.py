"""Application scoring. One file per application; add a new one to APPLICATIONS.

    cells = add_point_features(cells, RAW)   # volcano / crater distances
    cells = score_all(cells)
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .cave import CAVE
from .core import MARGIN, Application, Profile, apply, score, top
from .craters import CRATERS
from .rover import ROVER
from .sources import add_point_features
from .spacewalk import SPACEWALK

APPLICATIONS: list[Application] = [CAVE, ROVER, SPACEWALK, CRATERS]

REQUIRED: list[str] = ["temp_p", "precip_p", "temp_range_p", "barren", "elev_p",
                       "pass_forest", "pass_urban", "pass_water", "pass_slope", "pass_rough"]


def score_all(cells: pd.DataFrame, apps: Iterable[Application] = APPLICATIONS) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in cells]
    if missing:
        raise ValueError(f"cells table is missing {missing}: rebuild the base step")
    for app in apps:
        apply(cells, app)
    return cells


__all__ = ["APPLICATIONS", "Application", "Profile", "MARGIN", "score", "apply", "top",
           "score_all", "add_point_features", "CAVE", "ROVER", "SPACEWALK", "CRATERS"]
