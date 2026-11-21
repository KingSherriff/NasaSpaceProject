"""Analog Engine: builds the per-cell master table from a list of layers.

    engine = AnalogEngine(land=RasterLayer("worldclim_bio1", wc / "wc2.1_10m_bio_1.tif", {"temp": 1}))
    engine.addLayers(
        RasterLayer("modis_lc", lc_path, {"water_pct": 1, "forest_pct": [2, 3, 4, 5, 6]}, nodata=255),
        DerivedLayer("barren", {"barren": lambda df: df["barren_pct"].fillna(0) / 100}),
    )
    cells = engine.compile()

Every layer turns one source into one or more columns on the fixed grid (cell_id = row * ncols + col,
row 0 = north). The land layer runs first and defines which cells exist (non-NaN). The other layers
then run in order, so a DerivedLayer can use any column added before it. Rows are never dropped
after the land mask.

Run the whole pipeline:  python -m analog_engine   (see pipeline.py for the steps)

Package layout
    config.py       paths and shared settings (ETOPO kind, polar latitude)
    common.py       constants and type aliases
    grid.py         Grid: cell ids, centres, regridding
    terrain.py      slope / TRI / block statistics (pure numpy, any body)
    layers/         one file per layer type (base, raster, points, derived, terrain)
    engine.py       AnalogEngine: runs the layers into the cells table
    base_table.py   recipe for the Earth base table, one builder per data source
    downloads.py    every raw-data download (skips files on disk)
    filters.py      screening filter registry
    planets.py      Moon / Mars DEM terrain tables + reference sites
    likeness.py     Moon / Mars terrain likeness of Earth cells
    scoring/        scoring core + one file per application (cave, rover, spacewalk, craters)
    validation.py   known analog sites checks
    export.py       small JSON exports;  frontend.py: frontend_cells.json + contract check
    plots.py        quick-look maps
    pipeline.py     the steps (download, planets, base, score, frontend)
"""

from .base_table import build_base_engine
from .common import R_EARTH_KM
from .engine import AnalogEngine
from .grid import Grid
from .layers import DerivedLayer, Layer, PointDistanceLayer, RasterLayer, TerrainLayer
from .pipeline import run

__all__ = [
    "AnalogEngine",
    "Grid",
    "Layer",
    "RasterLayer",
    "PointDistanceLayer",
    "DerivedLayer",
    "TerrainLayer",
    "build_base_engine",
    "run",
    "R_EARTH_KM",
]
