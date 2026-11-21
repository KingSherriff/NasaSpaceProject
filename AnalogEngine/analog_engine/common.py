"""Constants and type aliases shared by the whole package."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, NotRequired, TypeAlias, TypedDict

import numpy as np
import numpy.typing as npt
import pandas as pd

R_EARTH_KM: float = 6371.0

FloatArray: TypeAlias = npt.NDArray[np.float64]
IntArray: TypeAlias = npt.NDArray[np.int64]
BoolArray: TypeAlias = npt.NDArray[np.bool_]
Columns: TypeAlias = dict[str, npt.NDArray[Any]]
"""Output of a layer: {column: values aligned with the rows of the cells table}."""
Bands: TypeAlias = int | Sequence[int]
"""One 1-based band, or several that are summed."""
ColumnFn: TypeAlias = Callable[[pd.DataFrame], "pd.Series[Any] | npt.NDArray[Any]"]
"""Function of the cells table built so far -> one value per row."""
PointSource: TypeAlias = pd.DataFrame | Callable[[], pd.DataFrame]
Percentiles: TypeAlias = bool | Iterable[str]


class LayerOptions(TypedDict):
    """Keyword options shared by every layer (see Layer)."""

    source: NotRequired[str]
    percentiles: NotRequired[Percentiles]
    overwrite: NotRequired[bool]


class SourceRecord(TypedDict):
    layer: str
    type: str
    source: str
