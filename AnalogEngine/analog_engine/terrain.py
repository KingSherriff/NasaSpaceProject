"""Terrain math on a DEM: slope, TRI and per-cell (block) statistics.

Pure numpy / scipy, no grid or layer logic, so the same functions can serve Earth, Moon and Mars.
See docs/LAYER_MATH.md section 8 for the formulas.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from scipy import ndimage

from .common import FloatArray

M_PER_DEG_LAT: float = 110574.0
M_PER_DEG_LON_EQUATOR: float = 111320.0

NEIGHBOURS: tuple[tuple[int, int], ...] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
)


# ----------------------------------------------------------------------------- per pixel
def slope_deg(
    dem: FloatArray, dx_m: FloatArray, dy_m: float, wrap_x: bool = False
) -> FloatArray:
    """Sobel/Horn slope in degrees. dx_m is the E-W pixel size per row, shape (rows, 1).

    wrap_x  the rows span the whole globe, so the first and last column are neighbours
    """
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]) / 8
    ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]]) / (8 * dy_m)
    dem_f = np.where(np.isnan(dem), np.nanmean(dem), dem)  # fill only for the convolution
    if wrap_x:
        dem_f = np.pad(dem_f, ((0, 0), (1, 1)), mode="wrap")
    dzdx = ndimage.convolve(dem_f, kx, mode="nearest")
    dzdy = ndimage.convolve(dem_f, ky, mode="nearest")
    if wrap_x:
        dzdx, dzdy = dzdx[:, 1:-1], dzdy[:, 1:-1]
    dzdx = dzdx / dx_m
    slope: FloatArray = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    slope[np.isnan(dem)] = np.nan
    return slope


def tri(dem: FloatArray) -> FloatArray:
    """Terrain Ruggedness Index: mean |z - neighbour| over the valid 8 neighbours (m)."""
    total: FloatArray = np.zeros_like(dem)
    count: FloatArray = np.zeros_like(dem)
    for ddy, ddx in NEIGHBOURS:
        d = np.abs(dem - np.roll(np.roll(dem, ddy, 0), ddx, 1))
        v = ~np.isnan(d)
        total[v] += d[v]
        count[v] += 1
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


# ----------------------------------------------------------------------------- per block (cell)
def blocked(arr: FloatArray, px: int) -> FloatArray:
    """(H, W) -> (H//px, px, W//px, px) view; the remainder rows/cols are dropped."""
    hb, wb = arr.shape[0] // px, arr.shape[1] // px
    return arr[: hb * px, : wb * px].reshape(hb, px, wb, px)


def block_stat(arr: FloatArray, px: int, func: Callable[..., FloatArray]) -> FloatArray:
    """func (e.g. np.nanmean) over every px x px block."""
    with np.errstate(all="ignore"):
        return func(blocked(arr, px), axis=(1, 3))


def block_percentiles(arr: FloatArray, px: int, qs: Sequence[float]) -> list[FloatArray]:
    """np.nanpercentile per block (linear), several percentiles from one sort."""
    b = blocked(arr, px)
    flat = b.transpose(0, 2, 1, 3).reshape(b.shape[0], b.shape[2], -1)
    s = np.sort(flat, axis=-1)  # NaN sorts to the end
    n_valid = np.sum(~np.isnan(flat), axis=-1)
    out: list[FloatArray] = []
    for q in qs:
        idx = (n_valid - 1) * (q / 100.0)
        lo = np.clip(np.floor(idx).astype(np.int64), 0, s.shape[-1] - 1)
        hi = np.clip(np.ceil(idx).astype(np.int64), 0, s.shape[-1] - 1)
        v_lo = np.take_along_axis(s, lo[..., None], axis=-1)[..., 0]
        v_hi = np.take_along_axis(s, hi[..., None], axis=-1)[..., 0]
        v = v_lo + (idx - np.floor(idx)) * (v_hi - v_lo)
        v[n_valid == 0] = np.nan
        out.append(v)
    return out


STAT_COLUMNS: tuple[str, ...] = (
    "slope_mean", "slope_p50", "slope_p90", "rough_p10", "rough_p50",
    "elev_min", "elev_max", "elev_mean", "elev_p05", "elev_p95",
)
"""Columns cell_stats returns (add_relief derives elev_range, relief_p90, hyps from them)."""


def cell_stats(dem: FloatArray, slope: FloatArray, rough: FloatArray, px: int) -> dict[str, FloatArray]:
    """Per-block slope, roughness and elevation statistics (the stored terrain columns)."""
    out: dict[str, FloatArray] = {"slope_mean": block_stat(slope, px, np.nanmean)}
    out["slope_p50"], out["slope_p90"] = block_percentiles(slope, px, [50, 90])
    out["rough_p10"], out["rough_p50"] = block_percentiles(rough, px, [10, 50])
    out["elev_min"] = block_stat(dem, px, np.nanmin)
    out["elev_max"] = block_stat(dem, px, np.nanmax)
    out["elev_mean"] = block_stat(dem, px, np.nanmean)
    out["elev_p05"], out["elev_p95"] = block_percentiles(dem, px, [5, 95])
    return out


def add_relief(blocks: dict[str, FloatArray]) -> None:
    """elev_range, relief_p90 and the hypsometric integral from the elevation stats (in place)."""
    blocks["elev_range"] = blocks["elev_max"] - blocks["elev_min"]
    blocks["relief_p90"] = blocks["elev_p95"] - blocks["elev_p05"]  # without the extreme pixels
    with np.errstate(all="ignore"):  # 0 = plain with peaks, 1 = plateau with pits
        blocks["hyps"] = np.where(
            blocks["elev_range"] > 0,
            (blocks["elev_mean"] - blocks["elev_min"]) / blocks["elev_range"],
            0.5,
        )
