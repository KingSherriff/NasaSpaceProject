"""Known analog sites: do they survive the screening, and do they get a label for their application?"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .grid import Grid

# Sites that should pass the screening filters
SCREENING_SITES: list[tuple[str, float, float]] = [
    ("Atacama Desert", -24.50, -69.25),
    ("Antarctic Dry Valleys", -77.50, 162.00),
    ("Haughton Crater", 75.38, -89.67),
    ("Mauna Kea", 19.82, -155.47),
    ("Black Point Lava Flow", 35.70, -111.40),
    ("Rio Tinto", 37.70, -6.60),
    ("Teide", 28.27, -16.64),
]

# Sites and the application they are used for: each should get a label in "its" column
APPLICATION_SITES: list[tuple[str, str, float, float]] = [
    ("cave", "Craters of the Moon, Idaho", 43.42, -113.52),
    ("cave", "Lava Beds, California", 41.71, -121.51),
    ("cave", "Mauna Loa (HI-SEAS), Hawaii", 19.60, -155.47),
    ("cave", "Cueva de los Verdes, Lanzarote", 29.16, -13.44),
    ("cave", "Undara, Australia", -18.20, 144.60),
    ("cave", "Raufarhólshellir, Iceland", 64.02, -21.40),
    ("rover", "Atacama (Yungay), Chile", -24.08, -69.92),
    ("rover", "MDRS, Utah", 38.41, -110.79),
    ("rover", "Ramon Crater (D-MARS), Negev", 30.61, 34.80),
    ("rover", "Erfoud (Ibn Battuta), Morocco", 31.43, -4.23),
    ("spacewalk", "Black Point Lava Flow, Arizona", 35.70, -111.40),
    ("spacewalk", "Qaidam Basin, China", 38.00, 93.00),
    ("spacewalk", "Mauna Kea, Hawaii", 19.82, -155.47),
    ("craters", "Meteor Crater, Arizona", 35.03, -111.02),
    ("craters", "Haughton, Devon Island", 75.38, -89.67),
    ("craters", "Gosses Bluff, Australia", -23.82, 132.31),
    ("craters", "Roter Kamm, Namibia", -27.77, 16.29),
    ("craters", "Wolfe Creek, Australia", -19.17, 127.80),
]


def screening_sites(grid: Grid | None = None) -> pd.DataFrame:
    df = pd.DataFrame(SCREENING_SITES, columns=["name", "lat", "lon"])
    df["cell_id"] = (grid or Grid()).cell_id(df.lat, df.lon)
    return df


def application_sites(grid: Grid | None = None) -> pd.DataFrame:
    df = pd.DataFrame(APPLICATION_SITES, columns=["used_for", "name", "lat", "lon"])
    df["cell_id"] = (grid or Grid()).cell_id(df.lat, df.lon)
    return df


def check_screening(cells: pd.DataFrame) -> pd.DataFrame:
    cols = ["cell_id", "forest_pct", "urban_pct", "water_pct", "biomass", "slope_p90", "rough_p10",
            "passes_all", "excluded_by"]
    check = screening_sites().merge(cells[[c for c in cols if c in cells]], on="cell_id", how="left")
    check["passes_all"] = check["passes_all"].fillna(False)
    check["excluded_by"] = check["excluded_by"].fillna("not a land cell")
    return check.drop(columns=["cell_id"]).round(1)


def check_applications(cells: pd.DataFrame, apps: Iterable[str]) -> pd.DataFrame:
    apps = list(apps)
    cols = ["cell_id", "barren", "precip_p", "temp_p", "slope_p90", *[f"label_{a}" for a in apps], "excluded_by"]
    check = application_sites().merge(cells[cols], on="cell_id", how="left")
    check["excluded_by"] = check["excluded_by"].fillna("not a land cell")
    check["hit"] = [isinstance(r[f"label_{r.used_for}"], str) and r[f"label_{r.used_for}"] != ""
                    if f"label_{r.used_for}" in check else False
                    for _, r in check.iterrows()]
    print(f"Known sites labelled for their own application: {check.hit.sum()} of {len(check)}")
    return check.drop(columns=["cell_id", "lat", "lon"]).round(2)
