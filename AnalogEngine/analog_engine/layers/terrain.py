"""TerrainLayer: ETOPO 2022 tiles -> slope, roughness and elevation statistics per cell."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TypeAlias, Unpack, cast, override

import numpy as np
import pandas as pd
import rasterio
from joblib import Parallel, delayed
from rasterio.windows import Window

from .. import terrain
from ..common import Columns, FloatArray, IntArray, LayerOptions
from ..grid import Grid
from .base import Layer

TileResult: TypeAlias = tuple[float, float, dict[str, FloatArray]]
"""(top, left, {column: (cells_y, cells_x) array}) for one terrain tile."""

STRIP_CELLS: int = 9
"""Rows of cells read at once per tile (memory vs. speed)."""


class TerrainLayer(Layer):
    """ETOPO 2022 tiles -> slope, roughness (TRI) and elevation statistics per cell.

    Each tile's native pixels are blocked into whole grid cells, so the tile edges must fall on cell
    edges (true for the 15° ETOPO tiles and any cell size that divides 15°).
    Columns: elev_min/max/mean/p05/p95/range, relief_p90, hyps, slope_mean/p50/p90, rough_p10/p50.
    """

    COLUMNS: tuple[str, ...] = (
        "elev_min", "elev_max", "elev_mean", "elev_p05", "elev_p95", "elev_range",
        "relief_p90", "hyps",
        "slope_mean", "slope_p50", "slope_p90",
        "rough_p10", "rough_p50",
    )

    tiles: list[Path]
    n_jobs: int

    def __init__(
        self,
        name: str,
        tiles: Iterable[str | Path],
        n_jobs: int = 4,
        **kw: Unpack[LayerOptions],
    ) -> None:
        super().__init__(name, **kw)
        self.tiles = [Path(t) for t in tiles]
        self.n_jobs = n_jobs

    @override
    def compute(self, grid: Grid, cells: pd.DataFrame) -> Columns:
        if not self.tiles:
            raise ValueError(f"{self.name}: no tiles given")
        results = cast(
            list[TileResult],
            Parallel(n_jobs=self.n_jobs, return_as="list")(
                delayed(terrain_tile)(p, grid.cell_size) for p in self.tiles
            ),
        )
        full = self._mosaic(grid, results)
        ids: IntArray = cells["cell_id"].to_numpy(dtype=np.int64)
        return {c: full[c].ravel()[ids] for c in self.COLUMNS}

    def _mosaic(self, grid: Grid, results: list[TileResult]) -> dict[str, FloatArray]:
        """Place every tile's blocks on the global grid (first tile wins where they overlap)."""
        full = {c: np.full((grid.nrows, grid.ncols), np.nan) for c in self.COLUMNS}
        for top, left, blocks in results:
            r0 = round((90 - top) / grid.cell_size)
            c0 = round(((left + 180) % 360) / grid.cell_size)
            for c in self.COLUMNS:
                b = blocks[c]
                target = full[c][r0 : r0 + b.shape[0], c0 : c0 + b.shape[1]]
                np.copyto(target, b[: target.shape[0], : target.shape[1]], where=np.isnan(target))
        return full


def terrain_tile(tif_path: Path, cell_size: float) -> TileResult:
    """One ETOPO tile -> (top, left, {column: (cells_y, cells_x) array}). Module level for joblib."""
    with rasterio.open(tif_path) as src:
        H, W = src.height, src.width
        tr = src.transform
        nodata: float | None = src.nodata
        top: float = src.bounds.top
        left: float = src.bounds.left
        epsg: int | None = src.crs.to_epsg()
    if epsg not in (4326, 9518):
        raise ValueError(f"{tif_path.name}: unexpected CRS EPSG:{epsg}")

    px_x, px_y = abs(tr.a), abs(tr.e)
    px = round(cell_size / px_x)  # native pixels per grid cell (120 at 15")
    dy_m = px_y * terrain.M_PER_DEG_LAT

    blocks: dict[str, FloatArray] = {
        k: np.full((H // px, W // px), np.nan) for k in terrain.STAT_COLUMNS
    }
    strip_h = px * STRIP_CELLS
    with rasterio.open(tif_path) as src:
        for y0 in range(0, H, strip_h):
            window = Window.from_slices((y0, min(y0 + strip_h, H)), (0, W))
            dem: FloatArray = src.read(1, window=window).astype(np.float64)
            if nodata is not None:
                dem[dem == nodata] = np.nan
            if np.isnan(dem).all():
                continue

            lat = top - px_y * (np.arange(y0, y0 + dem.shape[0]) + 0.5)
            dx_m = (px_x * terrain.M_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat)))[:, None]
            stats = terrain.cell_stats(dem, terrain.slope_deg(dem, dx_m, dy_m), terrain.tri(dem), px)

            b0 = y0 // px
            b1 = b0 + dem.shape[0] // px
            for k, v in stats.items():
                blocks[k][b0:b1] = v

    terrain.add_relief(blocks)
    return top, left, blocks
