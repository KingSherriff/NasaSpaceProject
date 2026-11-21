"""The fixed global grid: cell ids, cell centres and regridding of rasters onto it."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pandas as pd
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from rasterio.enums import Resampling

from .common import FloatArray, IntArray


class Grid:
    """Global EPSG:4326 grid, cell centres at cell_size / 2 offsets, row 0 = north, col 0 = lon -180."""

    cell_size: float
    ncols: int
    nrows: int
    lats: FloatArray
    lons: FloatArray

    def __init__(self, cell_size: float = 0.5) -> None:
        self.cell_size = cell_size
        self.ncols = round(360 / cell_size)
        self.nrows = round(180 / cell_size)
        self.lats = 90 - cell_size * (np.arange(self.nrows, dtype=np.float64) + 0.5)
        self.lons = -180 + cell_size * (np.arange(self.ncols, dtype=np.float64) + 0.5)

    @property
    def size(self) -> int:
        return self.nrows * self.ncols

    def cell_id(self, lat: npt.ArrayLike, lon: npt.ArrayLike) -> IntArray:
        lat_a = np.asarray(lat, dtype=np.float64)
        lon_a = np.asarray(lon, dtype=np.float64)
        row = ((90 - lat_a) // self.cell_size).astype(np.int64)
        col = ((lon_a + 180) // self.cell_size).astype(np.int64)
        return row * self.ncols + col

    def frame(self) -> pd.DataFrame:
        """Every cell of the grid: cell_id, lat, lon (cell_id equals the row-major flat index)."""
        lon2d, lat2d = np.meshgrid(self.lons, self.lats)
        return pd.DataFrame(
            {
                "cell_id": np.arange(self.size, dtype=np.int64),
                "lat": lat2d.ravel(),
                "lon": lon2d.ravel(),
            }
        )

    def template(self) -> xr.DataArray:
        """Empty DataArray on this grid, the target for rio.reproject_match."""
        da = xr.DataArray(
            np.zeros((self.nrows, self.ncols), dtype="float32"),
            dims=("y", "x"),
            coords={"y": self.lats, "x": self.lons},
        )
        return da.rio.write_crs(4326)

    def to_grid(self, cell_ids: npt.ArrayLike, values: npt.ArrayLike) -> FloatArray:
        """Per-cell values back onto the (nrows, ncols) array, NaN elsewhere."""
        grid = np.full((self.nrows, self.ncols), np.nan)
        grid.flat[np.asarray(cell_ids)] = values
        return grid

    def regrid(
        self, da: xr.DataArray, resampling: Resampling = Resampling.average
    ) -> FloatArray:
        """Any georeferenced 2-D raster -> (nrows, ncols) float array on this grid.

        Exact multiples of the cell size that line up with the grid edges are block-averaged
        with coarsen; everything else (other CRS, odd resolutions) goes through reproject_match.
        """
        da = da.squeeze(drop=True).astype("float64")
        if da.rio.crs is None:
            da = da.rio.write_crs(4326)
        is_geographic: bool = da.rio.crs.to_epsg() == 4326
        if is_geographic and float(da.x.max()) > 180:  # 0..360 longitudes
            da = da.assign_coords(x=((da.x + 180) % 360) - 180).sortby("x")

        if resampling == Resampling.average and is_geographic:
            factor = self._coarsen_factor(da)
            if factor:
                da = da.coarsen(x=factor, y=factor, boundary="trim").mean().rio.write_crs(4326)
                resampling = Resampling.nearest  # already on the grid, only align extent

        out = da.rio.reproject_match(self.template(), resampling=resampling)
        return np.asarray(out.values, dtype=np.float64)

    def _coarsen_factor(self, da: xr.DataArray) -> int | None:
        """Block size if da is square pixels, an exact divisor of the cell size and edge-aligned."""
        xres, yres = (abs(float(r)) for r in da.rio.resolution())
        left, _, _, top = (float(b) for b in da.rio.bounds())
        f = self.cell_size / xres
        aligned = (
            bool(np.isclose(xres, yres))
            and bool(np.isclose(f, round(f)))
            and round(f) > 1
            and self._on_edge(left + 180)
            and self._on_edge(90 - top)
        )
        return round(f) if aligned else None

    def _on_edge(self, offset_deg: float) -> bool:
        """True if offset_deg (from the -180 / +90 origin) is a whole number of cells."""
        k = offset_deg / self.cell_size
        return bool(np.isclose(k, round(k)))
