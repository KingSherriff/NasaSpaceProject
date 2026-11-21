"""Screening filters: boolean columns added to the cells table, rows are never deleted.

Add a filter by adding one entry to FILTERS. Missing values count as passing (fillna(0)).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pandas as pd

Rule = Callable[[pd.DataFrame], "pd.Series[bool]"]

FILTERS: dict[str, Rule] = {
    "forest": lambda df: df.forest_pct.fillna(0) <= 10,
    "urban": lambda df: df.urban_pct.fillna(0) <= 2,
    "water": lambda df: df.water_pct.fillna(0) <= 25,
    # terrain: only bites where ETOPO covers the cell
    "slope": lambda df: df.slope_p90.fillna(0) <= 15,
    "rough": lambda df: df.rough_p10.fillna(0) <= 15,
    # add later, e.g.: "protected": lambda df: df.protected_share.fillna(0) < 0.5,
}

LANDCOVER: tuple[str, ...] = ("forest", "urban", "water")
"""The land-cover filters (no terrain): used by likeness and the surface applications."""


def apply_filters(df: pd.DataFrame, filters: Mapping[str, Rule] = FILTERS) -> pd.DataFrame:
    """Add pass_<name>, passes_all and excluded_by (comma-separated failed filters). In place."""
    pass_cols = []
    for name, rule in filters.items():
        df[f"pass_{name}"] = rule(df)
        pass_cols.append(f"pass_{name}")
    df["passes_all"] = df[pass_cols].all(axis=1)
    names = [c[5:] for c in pass_cols]
    fails = ~df[pass_cols].to_numpy(dtype=bool)
    df["excluded_by"] = [", ".join(n for n, f in zip(names, row) if f) for row in fails]
    return df


def landcover_ok(df: pd.DataFrame) -> "pd.Series[bool]":
    """Passes the forest, urban and water filters (terrain rules not applied)."""
    return df[[f"pass_{n}" for n in LANDCOVER]].all(axis=1)


def funnel(df: pd.DataFrame, filters: Mapping[str, Rule] = FILTERS) -> pd.DataFrame:
    """Cells left after each filter in order (for the pitch)."""
    rows = [("start", len(df))]
    remaining = pd.Series(True, index=df.index)
    for name in filters:
        remaining &= df[f"pass_{name}"]
        rows.append((f"after {name}", int(remaining.sum())))
    return pd.DataFrame(rows, columns=["step", "cells"])
