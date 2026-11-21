"""RasterLayer: a raster file (GeoTIFF, HDF subdataset, ...) regridded to the grid."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Unpack, override

import numpy as np
import pandas as pd
import rasterio
import rioxarray
import xarray as xr
from rasterio.enums import Resampling

from ..common import Bands, Columns, IntArray, LayerOptions
from ..grid import Grid
from .base import Layer


class RasterLayer(Layer):
    """A raster file regridded to the grid.

    columns      {column: band} or {column: [bands]}; several bands are summed after regridding
                 (e.g. forest = IGBP classes 1-5). Bands are 1-based as in GDAL.
    subdataset   name suffix of an HDF/NetCDF subdataset, e.g. "Land_Cover_Type_1_Percent"
    nodata       extra fill value to mask (on top of the file's own nodata)
    resampling   rasterio Resampling used when the raster is not an exact multiple of the grid
    """

    path: Path
    columns: dict[str, Bands]
    subdataset: str | None
    nodata: float | None
    resampling: Resampling

    def __init__(
        self,
        name: str,
        path: str | Path,
        columns: Mapping[str, Bands],
        subdataset: str | None = None,
        nodata: float | None = None,
        resampling: Resampling = Resampling.average,
        **kw: Unpack[LayerOptions],
    ) -> None:
        super().__init__(name, **kw)
        self.path = Path(path)
        self.columns = dict(columns)
        self.subdataset = subdataset
        self.nodata = nodata
        self.resampling = resampling

    def _resolve_path(self) -> str:
        """The file path, or the matching subdataset path inside an HDF/NetCDF container."""
        path = str(self.path)
        if not self.subdataset:
            return path
        with rasterio.open(path) as src:
            subdatasets: list[str] = list(src.subdatasets)
        matches = [s for s in subdatasets if s.endswith(self.subdataset)]
        if not matches:
            raise ValueError(
                f"{self.name}: no subdataset ending in {self.subdataset!r} in {path}"
            )
        return matches[0]

    def _open(self) -> xr.DataArray:
        path = self._resolve_path()
        da = rioxarray.open_rasterio(path, masked=True)
        if not isinstance(da, xr.DataArray):
            raise TypeError(
                f"{self.name}: {path} opened as {type(da).__name__}, expected one raster"
            )
        if "band" not in da.dims:
            da = da.expand_dims(band=[1])
        return da

    def _band_sum(self, grid: Grid, da: xr.DataArray, col: str, bands: Bands) -> np.ndarray:
        """Regrid each band and add them up (NaN in any band -> NaN)."""
        band_list = [bands] if isinstance(bands, int) else list(bands)
        if not band_list:
            raise ValueError(f"{self.name}.{col}: no bands given")
        total = np.zeros((grid.nrows, grid.ncols))
        for b in band_list:
            band = da.sel(band=b)
            if self.nodata is not None:
                band = band.where(band != self.nodata)
            total = total + grid.regrid(band, self.resampling)
        return total

    @override
    def compute(self, grid: Grid, cells: pd.DataFrame) -> Columns:
        da = self._open()
        ids: IntArray = cells["cell_id"].to_numpy(dtype=np.int64)
        return {
            col: self._band_sum(grid, da, col, bands).ravel()[ids]
            for col, bands in self.columns.items()
        }
