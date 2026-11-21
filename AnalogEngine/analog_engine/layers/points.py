"""PointDistanceLayer: distance to the nearest point feature (volcano, crater, ...)."""

from __future__ import annotations

from typing import Unpack, override

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.spatial import KDTree

from ..common import R_EARTH_KM, Columns, FloatArray, LayerOptions, PointSource
from ..grid import Grid
from .base import Layer


def unit_vectors(lat: npt.ArrayLike, lon: npt.ArrayLike) -> FloatArray:
    """Lat/lon in degrees -> unit vectors, so chord distance in a KD-tree ranks like great-circle."""
    la = np.radians(np.asarray(lat, dtype=np.float64))
    lo = np.radians(np.asarray(lon, dtype=np.float64))
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def nearest_km(
    lat: npt.ArrayLike, lon: npt.ArrayLike, pts_lat: npt.ArrayLike, pts_lon: npt.ArrayLike
) -> FloatArray:
    """Great-circle distance (km) from each (lat, lon) to the nearest of the points."""
    tree = KDTree(unit_vectors(pts_lat, pts_lon))
    chord, _ = tree.query(unit_vectors(lat, lon), k=1)
    chord_a = np.asarray(chord, dtype=np.float64)
    return 2 * R_EARTH_KM * np.arcsin(np.clip(chord_a / 2, 0, 1))


def proximity_ramp(dist_km: FloatArray, full: float, zero: float) -> FloatArray:
    """1 up to `full` km, linear down to 0 at `zero` km."""
    return np.clip(1 - (dist_km - full) / (zero - full), 0, 1)


class PointDistanceLayer(Layer):
    """Great-circle distance from each cell centre to the nearest point, plus a 0..1 proximity ramp.

    points      DataFrame with lat/lon columns, or a callable returning one (loaded at compile time)
    column      base name: adds dist_<column>_km and <column>_prox
    ramp_km     (full, zero): proximity is 1 up to `full` km, linear down to 0 at `zero` km
    """

    points: PointSource
    column: str
    lat_col: str
    lon_col: str
    ramp_km: tuple[float, float]

    def __init__(
        self,
        name: str,
        points: PointSource,
        column: str,
        lat_col: str = "lat",
        lon_col: str = "lon",
        ramp_km: tuple[float, float] = (25, 100),
        **kw: Unpack[LayerOptions],
    ) -> None:
        super().__init__(name, **kw)
        self.points = points
        self.column = column
        self.lat_col, self.lon_col = lat_col, lon_col
        self.ramp_km = ramp_km

    @override
    def compute(self, grid: Grid, cells: pd.DataFrame) -> Columns:
        pts = self.points() if callable(self.points) else self.points
        lat = np.asarray(pd.to_numeric(pts[self.lat_col], errors="coerce"), np.float64)
        lon = np.asarray(pd.to_numeric(pts[self.lon_col], errors="coerce"), np.float64)
        ok = ~(np.isnan(lat) | np.isnan(lon))
        if not ok.any():
            raise ValueError(f"{self.name}: no points with coordinates")
        dist = nearest_km(cells["lat"], cells["lon"], lat[ok], lon[ok])
        return {
            f"dist_{self.column}_km": dist,
            f"{self.column}_prox": proximity_ramp(dist, *self.ramp_km),
        }
