"""Base class every layer derives from."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import override

import pandas as pd

from ..common import Columns, Percentiles
from ..grid import Grid


class Layer(ABC):
    """One source -> one or more columns.

    name         label used in logs and in the sources table
    source       URL / citation of the data (kept for every layer)
    percentiles  True = add <col>_p (Earth percentile over land cells) for every output column,
                 or a list of the columns that get one
    overwrite    allow replacing columns that already exist (e.g. a gap-fill DerivedLayer)
    """

    name: str
    source: str
    percentiles: bool | list[str]
    overwrite: bool

    def __init__(
        self,
        name: str,
        source: str = "",
        percentiles: Percentiles = False,
        overwrite: bool = False,
    ) -> None:
        self.name = name
        self.source = source
        self.percentiles = (
            percentiles if isinstance(percentiles, bool) else list(percentiles)
        )
        self.overwrite = overwrite

    @abstractmethod
    def compute(self, grid: Grid, cells: pd.DataFrame) -> Columns:
        """Return {column: values}, values aligned with the rows of `cells`."""

    def percentile_columns(self, columns: Iterable[str]) -> list[str]:
        if self.percentiles is True:
            return list(columns)
        if self.percentiles is False:
            return []
        return list(self.percentiles)

    @override
    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"
