"""DerivedLayer: columns computed from columns already in the table."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Unpack, override

import pandas as pd

from ..common import ColumnFn, Columns, LayerOptions
from ..grid import Grid
from .base import Layer


class DerivedLayer(Layer):
    """Columns computed from columns already in the table: {column: fn(cells) -> values}."""

    columns: dict[str, ColumnFn]

    def __init__(
        self,
        name: str,
        columns: Mapping[str, ColumnFn],
        **kw: Unpack[LayerOptions],
    ) -> None:
        super().__init__(name, **kw)
        self.columns = dict(columns)

    @override
    def compute(self, grid: Grid, cells: pd.DataFrame) -> Columns:
        out: Columns = {}
        view = cells.copy(deep=False)
        for col, fn in self.columns.items():
            view[col] = fn(view)  # later entries may use earlier ones
            out[col] = view[col].to_numpy()
        return out
