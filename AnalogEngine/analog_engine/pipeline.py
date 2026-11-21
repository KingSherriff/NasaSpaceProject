"""The whole pipeline as steps. Each step reads the files the step before it wrote.

    download   raw data for every step                       -> data/raw/...
    planets    Moon / Mars terrain tables + reference sites   -> {moon,mars}_cells.parquet, planet_sites.parquet
    base       Earth base table + filters + likeness          -> cells.parquet, site_matches.parquet
    score      application scoring                            -> cells_scored.parquet
    frontend   frontend_cells.json (contract-checked)         -> public/data/frontend_cells.json
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from . import downloads, export, filters, likeness, planets, scoring, validation
from .base_table import build_base_engine
from .config import ETOPO_KIND, FRONT, PROCESSED, RAW, ensure_dirs
from .frontend import build as build_frontend
from .frontend import write as write_frontend

STEPS: tuple[str, ...] = ("download", "planets", "base", "score", "frontend")


def download(raw: Path = RAW) -> None:
    downloads.everything(raw)


def run_planets(raw: Path = RAW, out: Path = PROCESSED, front: Path = FRONT,
                bodies: Iterable[str] = ("moon", "mars")) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    bodies = list(bodies)
    tiles = sorted((raw / "etopo").glob(f"ETOPO_2022_v1_15s_*_{ETOPO_KIND}.tif")) if "earth" in bodies else []
    tables, sites, _ = planets.build_planets(raw, bodies, tiles)
    for body, cells in tables.items():
        cells.to_parquet(out / f"{body}_cells.parquet", index=False)
    sites.to_parquet(out / "planet_sites.parquet", index=False)
    export.planets(tables, sites, front)
    return tables, sites


def run_base(raw: Path = RAW, out: Path = PROCESSED, front: Path = FRONT) -> pd.DataFrame:
    """Base table -> filters -> Moon/Mars likeness (needs the planets step) -> cells.parquet."""
    engine = build_base_engine(raw)
    cells = engine.compile()
    filters.apply_filters(cells)
    print(filters.funnel(cells).to_string(index=False))
    print(validation.check_screening(cells).to_string(index=False))

    lk = likeness.compute(
        cells,
        pd.read_parquet(out / "moon_cells.parquet"),
        pd.read_parquet(out / "mars_cells.parquet"),
        pd.read_parquet(out / "planet_sites.parquet"),
    )
    likeness.report(lk)
    cells = likeness.merge_into(cells, lk)
    cells.attrs["sources"] = engine.source_records()

    lk.matches.to_parquet(out / "site_matches.parquet", index=False)
    for body in likeness.BODIES:
        lk.bodies[body].to_parquet(out / f"{body}_cells_matched.parquet", index=False)
    cells.to_parquet(out / "cells.parquet", index=False)
    print(f"Saved {out / 'cells.parquet'} ({len(cells):,} cells)")
    export.likeness(lk, front)
    export.screening(cells, front)
    return cells


def run_score(raw: Path = RAW, out: Path = PROCESSED) -> pd.DataFrame:
    """cells.parquet -> volcano / crater distances -> every application -> cells_scored.parquet."""
    cells = pd.read_parquet(out / "cells.parquet")
    scoring.add_point_features(cells, raw)
    scoring.score_all(cells)
    apps = [a.name for a in scoring.APPLICATIONS]
    print(validation.check_applications(cells, apps).to_string(index=False))
    cells.to_parquet(out / "cells_scored.parquet", index=False)
    print(f"Saved {out / 'cells_scored.parquet'} with applications {apps}")
    return cells


def run_frontend(out: Path = PROCESSED, front: Path = FRONT) -> Path:
    return write_frontend(build_frontend(pd.read_parquet(out / "cells_scored.parquet")),
                          front / "frontend_cells.json")


def run(steps: Iterable[str] = STEPS) -> None:
    ensure_dirs()
    steps = list(steps)
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise ValueError(f"unknown steps {unknown}; choose from {STEPS}")
    for step in STEPS:  # always in pipeline order
        if step not in steps:
            continue
        print(f"\n===== {step} =====")
        {"download": download, "planets": run_planets, "base": run_base,
         "score": run_score, "frontend": run_frontend}[step]()
