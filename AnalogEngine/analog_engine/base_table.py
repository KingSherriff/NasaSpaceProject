"""The 'Cells filtering' base table as an engine recipe: which files become which columns.

One builder function per data source, so a source can be added, removed or swapped in one place.
Each builder returns the layers for that source, or [] when its files are not on disk.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ETOPO_KIND, POLAR_LAT
from .engine import AnalogEngine
from .layers import DerivedLayer, Layer, RasterLayer, TerrainLayer

WORLDCLIM_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
MODIS_LC_URL = "https://doi.org/10.5067/MODIS/MCD12C1.061"
GEDI_URL = "https://doi.org/10.3334/ORNLDAAC/2339"
ETOPO_URL = "https://www.ngdc.noaa.gov/products/etopo-global-relief-model"

BIOCLIM: dict[str, int] = {"temp_min": 6, "temp_range": 7, "precip": 12}
"""Extra WorldClim bioclim columns -> BIO number (BIO1 'temp' is the land layer)."""

IGBP_BANDS: dict[str, int | list[int]] = {  # band = IGBP class + 1
    "water_pct": 1,
    "forest_pct": [2, 3, 4, 5, 6],
    "urban_pct": 14,
    "snow_pct": 16,
    "barren_pct": 17,
}


# ----------------------------------------------------------------------------- one builder per source
def land_layer(raw: Path) -> RasterLayer:
    """WorldClim BIO1 annual mean temperature; defines which cells are land."""
    return RasterLayer(
        "worldclim_bio1",
        raw / "worldclim" / "wc2.1_10m_bio_1.tif",
        {"temp": 1},
        source=WORLDCLIM_URL,
        percentiles=True,
    )


def worldclim_layers(raw: Path) -> list[Layer]:
    return [
        RasterLayer(
            f"worldclim_bio{n}",
            raw / "worldclim" / f"wc2.1_10m_bio_{n}.tif",
            {col: 1},
            source=WORLDCLIM_URL,
            percentiles=True,
        )
        for col, n in BIOCLIM.items()
    ]


def modis_layers(raw: Path) -> list[Layer]:
    lc = sorted((raw / "modis_lc").glob("MCD12C1*.hdf"))
    if not lc:
        return []
    return [
        RasterLayer(
            "modis_lc",
            lc[-1],
            subdataset="Land_Cover_Type_1_Percent",
            nodata=255,
            columns=IGBP_BANDS,
            source=MODIS_LC_URL,
        ),
        DerivedLayer("barren", {"barren": lambda df: df["barren_pct"].fillna(0) / 100}),
    ]


def _bare(df: pd.DataFrame) -> pd.Series[bool]:
    """Mostly barren or ice: outside GEDI coverage these get biomass 0."""
    return (df["barren_pct"].fillna(0) + df["snow_pct"].fillna(0)) > 80


def gedi_layers(raw: Path, with_gapfill: bool) -> list[Layer]:
    """GEDI biomass; the bare-ground gap fill needs MODIS land cover (with_gapfill)."""
    gedi = sorted((raw / "gedi").glob("*agbd*20230316*12000m.tif"))
    if not gedi:
        return []
    layers: list[Layer] = [
        RasterLayer("gedi_agbd", gedi[0], {"biomass": 1}, source=GEDI_URL)
    ]
    if with_gapfill:
        layers.append(
            DerivedLayer(
                "biomass_gapfill",
                {"biomass": lambda df: df["biomass"].mask(df["biomass"].isna() & _bare(df), 0.0)},
                overwrite=True,
                percentiles=True,
            )
        )
    return layers


def etopo_layers(raw: Path, kind: str = ETOPO_KIND) -> list[Layer]:
    tiles = sorted((raw / "etopo").glob(f"ETOPO_2022_v1_15s_*_{kind}.tif"))
    if not tiles:
        return []
    return [
        TerrainLayer("etopo2022", tiles, source=ETOPO_URL),
        # coastal cells average in sea floor: clip at the lowest real land (Dead Sea shore, ~-430 m)
        DerivedLayer(
            "elevation",
            {
                "elevation": lambda df: df["elev_mean"].clip(lower=-430),
                "elev_p": lambda df: df["elevation"].rank(pct=True),
            },
        ),
    ]


def polar_layer() -> DerivedLayer:
    return DerivedLayer("polar", {"polar": lambda df: df["lat"].abs() > POLAR_LAT})


# ----------------------------------------------------------------------------- recipe
def build_base_engine(raw: Path) -> AnalogEngine:
    """The 'Cells filtering' base table from the files under data/raw (only the ones present)."""
    modis = modis_layers(raw)
    return AnalogEngine(land=land_layer(raw)).addLayers(
        *worldclim_layers(raw),
        *modis,
        *gedi_layers(raw, with_gapfill=bool(modis)),
        *etopo_layers(raw),
        polar_layer(),
    )
