"""Moon / Mars (/ Earth) DEMs -> terrain table per ~55 km cell, plus reference sites.

Each DEM is a global lat/lon raster. Cells are blocks of PX_PER_CELL x PX_PER_CELL pixels, which is
about 55 km on all three bodies (same as an Earth 0.5° cell). The terrain columns match the Earth
base table, so the likeness step can compare them directly. Formulas: docs/LAYER_MATH.md §12.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import rasterio
import xarray as xr
from rasterio.windows import Window

from . import terrain
from .common import FloatArray, IntArray
from .config import POLAR_LAT

PX_PER_CELL: int = 120
EARTH_R_M: float = 6_371_000  # mean sphere
MOON_R_M: float = 1_737_400  # LOLA reference sphere
MARS_R_M: float = 3_396_190  # MOLA reference sphere

# Base candidates and landing sites, (body, name, lat, lon) east-positive
REFERENCE_SITES: list[tuple[str, str, float, float]] = [
    ("moon", "Shackleton rim (south pole)", -89.7, 129.8),
    ("moon", "Malapert massif", -86.0, 2.9),
    ("moon", "Apollo 11, Mare Tranquillitatis", 0.67, 23.47),
    ("moon", "Apollo 15, Hadley Rille", 26.13, 3.63),
    ("moon", "Apollo 17, Taurus-Littrow", 20.19, 30.77),
    ("moon", "Marius Hills pit", 14.09, -56.77),
    ("moon", "Chang'e 4, Von Karman", -45.44, 177.60),
    ("mars", "Jezero (Perseverance)", 18.44, 77.45),
    ("mars", "Gale (Curiosity)", -4.59, 137.44),
    ("mars", "Elysium Planitia (InSight)", 4.50, 135.62),
    ("mars", "Meridiani (Opportunity)", -1.95, -5.53),
    ("mars", "Gusev (Spirit)", -14.57, 175.47),
    ("mars", "Utopia Planitia (Zhurong)", 25.07, 109.93),
    ("mars", "Arcadia Planitia", 39.8, -158.0),
    ("mars", "Vastitas Borealis (Phoenix)", 68.22, -125.75),
]

SITE_COLUMNS: list[str] = ["slope_mean", "slope_p90", "rough_p10", "elev_min", "elev_max", "elev_range"]


# ----------------------------------------------------------------------------- DEM readers
@dataclass
class DEM:
    """A global DEM read in full-width row strips. Rows run north to south."""

    radius_m: float
    n_cols: int
    row_lat: FloatArray  # latitude of each pixel row
    lon_left: float  # west edge of column 0
    read_rows: Callable[[int, int], FloatArray]  # (y0, y1) -> metres, NaN = nodata

    def cell_deg(self, px: int = PX_PER_CELL) -> float:
        return 360 / self.n_cols * px

    def cell_km(self, px: int = PX_PER_CELL) -> float:
        return self.cell_deg(px) * np.pi * self.radius_m / 180 / 1000

    def cell_id(self, lat: npt.ArrayLike, lon: npt.ArrayLike, px: int = PX_PER_CELL) -> IntArray:
        """cell_id of the cell containing (lat, lon), east-positive longitude."""
        d = self.cell_deg(px)
        lat_a, lon_a = np.asarray(lat), np.asarray(lon)
        row = ((90 - lat_a) // d).astype(np.int64)  # 0 = northernmost row
        col = (((lon_a - self.lon_left) % 360) // d).astype(np.int64)
        return row * (self.n_cols // px) + col


def open_moon(path: Path) -> DEM:
    """LOLA LDEM64 .grd (km) -> DEM in metres. The gridline file repeats lon 360 = 0, dropped here."""
    moon = xr.open_dataset(path)
    if moon.lat[0] < moon.lat[-1]:
        moon = moon.isel(lat=slice(None, None, -1))
    moon = moon.isel(lon=slice(0, -1))
    px = 360 / moon.sizes["lon"]
    return DEM(
        radius_m=MOON_R_M,
        n_cols=moon.sizes["lon"],
        row_lat=moon.lat.values,
        lon_left=float(moon.lon[0]) - px / 2,
        read_rows=lambda y0, y1: moon.z.isel(lat=slice(y0, y1)).values.astype("float64") * 1000,
    )


def open_mars(path: Path) -> DEM:
    """MOLA 463 m GeoTIFF (equirectangular metres, lon -180..180)."""
    src = rasterio.open(path)
    row_lat = 90 - 180 / src.height * (np.arange(src.height) + 0.5)

    def read_rows(y0: int, y1: int) -> FloatArray:
        dem = src.read(1, window=Window(0, y0, src.width, y1 - y0)).astype("float64")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        return dem

    return DEM(radius_m=MARS_R_M, n_cols=src.width, row_lat=row_lat, lon_left=-180.0, read_rows=read_rows)


def open_earth(tiles: Iterable[Path]) -> DEM:
    """All 12 x 24 ETOPO 15° tiles stitched on the fly into one pole-to-pole DEM."""
    srcs = {}
    for p in tiles:
        s = rasterio.open(p)
        srcs[(round((90 - s.bounds.top) / 15), round((s.bounds.left + 180) / 15) % 24)] = s
    tile_px = next(iter(srcs.values())).height
    if len(srcs) != 12 * 24 or not all(s.height == s.width == tile_px for s in srcs.values()):
        raise ValueError(f"Earth DEM needs all 288 square ETOPO tiles, got {len(srcs)}")
    h, w = 12 * tile_px, 24 * tile_px

    def read_rows(y0: int, y1: int) -> FloatArray:
        out = np.empty((y1 - y0, w))
        for tr in range(y0 // tile_px, (y1 - 1) // tile_px + 1):
            a, b = max(y0, tr * tile_px), min(y1, (tr + 1) * tile_px)
            for tc in range(24):
                s = srcs[(tr, tc)]
                block = s.read(1, window=Window(0, a - tr * tile_px, tile_px, b - a)).astype("float64")
                if s.nodata is not None:
                    block[block == s.nodata] = np.nan
                out[a - y0 : b - y0, tc * tile_px : (tc + 1) * tile_px] = block
        return out

    return DEM(radius_m=EARTH_R_M, n_cols=w, row_lat=90 - 180 / h * (np.arange(h) + 0.5),
               lon_left=-180.0, read_rows=read_rows)


# ----------------------------------------------------------------------------- terrain table
def terrain_table(dem: DEM, px: int = PX_PER_CELL) -> pd.DataFrame:
    """One row per cell: cell_id, lat, lon, the Earth terrain columns, polar."""
    px_deg = 360 / dem.n_cols
    dy_m = px_deg * np.pi * dem.radius_m / 180
    n_rows = len(dem.row_lat)
    nb_y, nb_x = n_rows // px, dem.n_cols // px
    blocks = {k: np.full((nb_y, nb_x), np.nan) for k in terrain.STAT_COLUMNS}

    for b in range(nb_y):  # one row of cells at a time
        y0, y1 = b * px, (b + 1) * px
        r0, r1 = max(y0 - 1, 0), min(y1 + 1, n_rows)  # 1-row halo so cell edges see their neighbours
        z = dem.read_rows(r0, r1)
        dx_m = (dy_m * np.cos(np.radians(dem.row_lat[r0:r1])))[:, None]
        dx_m[dx_m < 1] = np.nan  # the pole itself has no E-W direction
        slope = terrain.slope_deg(z, dx_m, dy_m, wrap_x=True)  # longitude wraps around the globe
        rough = terrain.tri(z)
        keep = slice(y0 - r0, y0 - r0 + px)  # drop the halo rows again
        for k, v in terrain.cell_stats(z[keep], slope[keep], rough[keep], px).items():
            blocks[k][b] = v[0]
    terrain.add_relief(blocks)

    cell_deg = px_deg * px
    lat = dem.row_lat[: nb_y * px].reshape(nb_y, px).mean(axis=1)
    lon = (dem.lon_left + cell_deg * (np.arange(nb_x) + 0.5) + 180) % 360 - 180
    lon2d, lat2d = np.meshgrid(lon, lat)
    cells = pd.DataFrame({"cell_id": np.arange(nb_y * nb_x), "lat": lat2d.ravel(), "lon": lon2d.ravel()})
    for name, arr in blocks.items():
        cells[name] = arr.ravel()
    cells["polar"] = cells.lat.abs() > POLAR_LAT  # wedge-shaped cells, lower confidence
    return cells


def reference_sites(tables: dict[str, pd.DataFrame], dems: dict[str, DEM]) -> pd.DataFrame:
    """REFERENCE_SITES with their cell_id and terrain values (bodies without a table are skipped)."""
    sites = pd.DataFrame(REFERENCE_SITES, columns=["body", "name", "lat", "lon"])
    sites = sites[sites.body.isin(list(tables))]
    sites["cell_id"] = [int(dems[s.body].cell_id(s.lat, s.lon)) for s in sites.itertuples()]
    cols = ["cell_id", *SITE_COLUMNS]
    return pd.concat(
        [sites[sites.body == body].merge(cells[cols], on="cell_id", how="left")
         for body, cells in tables.items()],
        ignore_index=True,
    )


def open_dems(raw: Path, bodies: Iterable[str], etopo_tiles: Iterable[Path] = ()) -> dict[str, DEM]:
    openers: dict[str, Callable[[], DEM]] = {
        "moon": lambda: open_moon(raw / "moon" / "LDEM64_PA_gridline_202405.grd"),
        "mars": lambda: open_mars(raw / "mars" / "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"),
        "earth": lambda: open_earth(etopo_tiles),
    }
    return {b: openers[b]() for b in bodies}


def build_planets(
    raw: Path, bodies: Iterable[str] = ("moon", "mars"), etopo_tiles: Iterable[Path] = ()
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, DEM]]:
    """Terrain table per body and the reference sites. 'earth' (all ETOPO tiles) is optional:
    the Earth side of the likeness uses the 0.5° base table instead."""
    dems = open_dems(raw, bodies, etopo_tiles)
    tables = {}
    for body, dem in dems.items():
        tables[body] = terrain_table(dem)
        print(f"{body}: {len(tables[body]):,} cells of {dem.cell_km():.1f} km ({dem.cell_deg():.4f}°)")
    return tables, reference_sites(tables, dems), dems
