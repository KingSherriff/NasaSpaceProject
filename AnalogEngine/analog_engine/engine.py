"""AnalogEngine: runs the land layer, masks to land cells, then the other layers in order."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .common import BoolArray, SourceRecord
from .grid import Grid
from .layers.base import Layer


class AnalogEngine:
    """Runs the land layer, masks to land cells, then runs the other layers in order."""

    grid: Grid
    cell_size: float
    ncols: int
    land: Layer
    layers: list[Layer]
    cells: pd.DataFrame | None

    def __init__(self, land: Layer, cell_size: float = 0.5) -> None:
        self.grid = Grid(cell_size)
        self.cell_size = cell_size
        self.ncols = self.grid.ncols
        self.land = land
        self.layers = []
        self.cells = None

    # ------------------------------------------------------------------ registry
    def addLayer(self, layer: Layer) -> AnalogEngine:
        if any(l.name == layer.name for l in [self.land, *self.layers]):
            raise ValueError(f"a layer named {layer.name!r} is already registered")
        self.layers.append(layer)
        return self

    def addLayers(self, *layers: Layer) -> AnalogEngine:
        for layer in layers:
            _ = self.addLayer(layer)
        return self

    def source_records(self) -> list[SourceRecord]:
        return [
            {"layer": l.name, "type": type(l).__name__, "source": l.source}
            for l in [self.land, *self.layers]
        ]

    def sources(self) -> pd.DataFrame:
        """Every layer with its type and source URL."""
        return pd.DataFrame(self.source_records())

    # ------------------------------------------------------------------ build
    def compile(self) -> pd.DataFrame:
        """Build the master table: one row per land cell, one column per layer output."""
        cells = self._land_cells()
        for layer in self.layers:
            _ = self._apply(layer, cells)
        cells.attrs["sources"] = self.source_records()
        self.cells = cells
        return cells

    def _land_cells(self) -> pd.DataFrame:
        """Land layer on the full grid; cells where all its columns are defined. Percentiles after masking."""
        full = self.grid.frame()
        values = self.land.compute(self.grid, full)
        land: BoolArray = np.logical_and.reduce(
            [~np.isnan(np.asarray(v, dtype=np.float64)) for v in values.values()]
        )
        cells = pd.DataFrame(full.loc[land]).reset_index(drop=True)
        for col, v in values.items():
            cells[col] = np.asarray(v)[land]
        _add_percentiles(self.land, cells, values)
        print(f"Land cells ({self.land.name}): {len(cells):,} of {self.grid.size:,}")
        return cells

    def _apply(self, layer: Layer, cells: pd.DataFrame) -> list[str]:
        print(f"→ {layer.name} ...", flush=True)
        values = layer.compute(self.grid, cells)
        clash = [c for c in values if c in cells and not layer.overwrite]
        if clash:
            raise ValueError(
                f"{layer.name}: columns {clash} already exist (pass overwrite=True to replace)"
            )
        for col, v in values.items():
            arr = np.asarray(v)
            if arr.shape != (len(cells),):
                raise ValueError(
                    f"{layer.name}.{col}: got shape {arr.shape}, expected ({len(cells)},)"
                )
            cells[col] = arr
        _add_percentiles(layer, cells, values)
        print(f"  + {', '.join(values)}")
        return list(values)


def _add_percentiles(layer: Layer, cells: pd.DataFrame, columns: Iterable[str]) -> None:
    for col in layer.percentile_columns(columns):
        cells[f"{col}_p"] = cells[col].rank(pct=True)  # NaN stays NaN
