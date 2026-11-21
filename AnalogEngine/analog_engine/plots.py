"""Quick-look maps (matplotlib). Each function returns the figure; call plt.show() in a notebook."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from .filters import FILTERS, Rule
from .grid import Grid
from .planets import DEM

EXTENT = [-180, 180, -90, 90]
BODY_COLORS = {1: "#f0a500", 2: "#c1440e", 3: "#7b3fa0"}  # moon / mars / both


def _grid(cells: pd.DataFrame, values) -> np.ndarray:  # noqa: ANN001
    return Grid().to_grid(cells.cell_id.to_numpy(), np.asarray(values))


def screening_map(cells: pd.DataFrame, sites: pd.DataFrame | None = None,
                  filters: Mapping[str, Rule] = FILTERS):
    """Cells coloured by the first filter that rejects them (green = passes)."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    names = list(filters)
    passes = cells[[f"pass_{n}" for n in names]].to_numpy(dtype=bool)
    first_fail = np.where(passes.all(axis=1), 0, (~passes).argmax(axis=1) + 1)
    colors = ["#2ca25f"] + ["#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5"][: len(names)]

    fig, ax = plt.subplots(figsize=(16, 8))
    ax.imshow(_grid(cells, first_fail), extent=EXTENT, cmap=ListedColormap(colors),
              vmin=0, vmax=len(names), interpolation="nearest")
    if sites is not None:
        ax.scatter(sites.lon, sites.lat, c="red", s=40, edgecolor="k", zorder=3)
        for a in sites.itertuples():
            ax.annotate(a.name, (a.lon, a.lat), xytext=(4, 4), textcoords="offset points", fontsize=8)
    legend = [Patch(color=colors[0], label="passes all")] + \
             [Patch(color=colors[i], label=f"rejected: {n}") for i, n in enumerate(names, start=1)]
    ax.legend(handles=legend, loc="lower left")
    ax.set_title("Cells after screening filters")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")
    return fig


def planet_slope_maps(tables: Mapping[str, pd.DataFrame], dems: Mapping[str, DEM],
                      sites: pd.DataFrame | None = None, px: int = 120):
    """90th-percentile slope per ~55 km cell for each body."""
    import matplotlib.pyplot as plt

    bodies = [b for b in tables if b in dems]
    fig, axes = plt.subplots(len(bodies), 1, figsize=(16, 8 * len(bodies)), squeeze=False)
    for ax, body in zip(axes[:, 0], bodies):
        ncols = dems[body].n_cols // px
        grid = tables[body].sort_values("cell_id").slope_p90.values.reshape(-1, ncols)
        grid = np.roll(grid, round((dems[body].lon_left + 180) / 360 * ncols), axis=1)  # start at 180°W
        im = ax.imshow(grid, extent=EXTENT, cmap="magma", vmin=0, vmax=30, interpolation="nearest")
        if sites is not None:
            s = sites[sites.body == body]
            ax.scatter(s.lon, s.lat, c="cyan", s=40, edgecolor="k", zorder=3)
            for a in s.itertuples():
                ax.annotate(a.name, (a.lon, a.lat), xytext=(4, 4), textcoords="offset points",
                            fontsize=8, color="white")
        fig.colorbar(im, ax=ax, label="slope_p90 (deg)", shrink=0.8)
        ax.set_title(f"{body.capitalize()}: 90th-percentile slope per ~55 km cell")
    return fig


def label_maps(cells: pd.DataFrame, apps: Iterable[str], sites: pd.DataFrame | None = None):
    """Moon / Mars / both label per application."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    apps = list(apps)
    land = _grid(cells, np.ones(len(cells)))
    fig, axes = plt.subplots(2, 2, figsize=(22, 11))
    for ax, app in zip(axes.ravel(), apps):
        lab = _grid(cells, cells[f"label_{app}"].map({"moon": 1, "mars": 2, "both": 3}).fillna(0).values)
        lab[lab == 0] = np.nan
        ax.imshow(land, extent=EXTENT, cmap=ListedColormap(["#e6e6e6"]))
        ax.imshow(lab, extent=EXTENT, cmap=ListedColormap(list(BODY_COLORS.values())),
                  vmin=1, vmax=3, interpolation="nearest")
        if sites is not None:
            s = sites[sites.used_for == app]
            ax.scatter(s.lon, s.lat, c="cyan", s=30, edgecolor="k", zorder=3)
        ax.set_title(f"{app}: Moon vs Mars ({(cells[f'label_{app}'] != '').sum():,} cells)")
    axes[0, 0].legend(handles=[Patch(color=BODY_COLORS[1], label="Moon"), Patch(color=BODY_COLORS[2], label="Mars"),
                               Patch(color=BODY_COLORS[3], label="both"), Patch(color="#e6e6e6", label="not a site")],
                      loc="lower left")
    fig.tight_layout()
    return fig


def quality_maps(cells: pd.DataFrame, apps: Iterable[str]):
    """Ranking score (best of Moon / Mars) within the labelled cells."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    land = _grid(cells, np.ones(len(cells)))
    fig, axes = plt.subplots(2, 2, figsize=(22, 11))
    for ax, app in zip(axes.ravel(), apps):
        q = _grid(cells, cells[f"{app}_quality"].values)
        q[q == 0] = np.nan
        ax.imshow(land, extent=EXTENT, cmap=ListedColormap(["#e6e6e6"]))
        im = ax.imshow(q, extent=EXTENT, cmap="magma", vmin=0.4, vmax=1, interpolation="nearest")
        ax.set_title(f"{app}: quality (best of Moon / Mars score)")
        plt.colorbar(im, ax=ax, fraction=0.025)
    fig.tight_layout()
    return fig
