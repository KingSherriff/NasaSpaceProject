"""Point sources for scoring: basaltic volcanoes (caves) and impact structures (craters).

Adds dist_basalt_volc_km / volc_prox and dist_crater_km / crater_prox to the cells table.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..layers.points import nearest_km, proximity_ramp

# Lava tubes form in basalt. The GVP WFS CSV has no rock-type column, so VolcanoType is the proxy:
# shields, volcanic fields, fissure vents and lava cones are mostly effusive basalt,
# while stratovolcanoes, calderas and lava domes are mostly andesitic/explosive.
BASALTIC_TYPES = r"shield|volcanic field|fissure|lava cone|lava field|pyroclastic cone"
RAMP_KM: tuple[float, float] = (25, 100)  # 1 within 25 km (≈ in the cell), 0 at 100 km


def _find_col(df: pd.DataFrame, keys: list[str]) -> str | None:
    for c in df.columns:
        if any(k in c.lower() for k in keys):
            return c
    return None


def load_volcanoes(csv: Path) -> pd.DataFrame:
    """GVP Holocene volcanoes with lat, lon and a basaltic flag."""
    volc = pd.read_csv(csv)
    lat_c, lon_c = _find_col(volc, ["latitude", "lat"]), _find_col(volc, ["longitude", "lon", "long"])
    geom_c = _find_col(volc, ["geom", "shape", "wkt", "location"])
    if lat_c and lon_c:
        volc["lat"] = pd.to_numeric(volc[lat_c], errors="coerce")
        volc["lon"] = pd.to_numeric(volc[lon_c], errors="coerce")
    elif geom_c:
        xy = volc[geom_c].astype(str).str.extract(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)")
        volc["lon"], volc["lat"] = xy[0].astype(float), xy[1].astype(float)
    else:
        raise ValueError(f"No coordinate columns in {csv.name}: {volc.columns.tolist()}")
    volc = volc.dropna(subset=["lat", "lon"])

    type_c = next((c for c in volc.columns if c.lower() == "volcanotype"), None)
    if type_c:
        volc["basaltic"] = volc[type_c].astype(str).str.contains(BASALTIC_TYPES, case=False, regex=True)
    else:
        volc["basaltic"] = True
        print("⚠ No VolcanoType column found; using all volcanoes")
    print(f"Volcanoes: {len(volc):,} total, {volc.basaltic.sum():,} basaltic")
    return volc


def load_craters(csv: Path) -> pd.DataFrame:
    craters = (pd.read_csv(csv)
               .rename(columns={"itemLabel": "name", "diam": "diameter_km"})
               .dropna(subset=["lat", "lon"])
               .drop_duplicates("item")
               .reset_index(drop=True))
    print(f"Impact structures: {len(craters):,} ({craters.diameter_km.notna().sum()} with a diameter)")
    return craters


def add_distance(cells: pd.DataFrame, pts: pd.DataFrame, dist_col: str, prox_col: str) -> None:
    d = nearest_km(cells["lat"], cells["lon"], pts["lat"], pts["lon"])
    cells[dist_col] = d
    cells[prox_col] = proximity_ramp(d, *RAMP_KM)


def add_point_features(cells: pd.DataFrame, raw: Path) -> pd.DataFrame:
    """Volcano and crater distances from the CSVs under raw/ (see downloads.scoring_sources)."""
    volc = load_volcanoes(raw / "gvp" / "holocene_volcanoes.csv")
    add_distance(cells, volc[volc.basaltic], "dist_basalt_volc_km", "volc_prox")
    craters = load_craters(raw / "craters" / "wikidata_impact_craters.csv")
    add_distance(cells, craters, "dist_crater_km", "crater_prox")
    return cells
