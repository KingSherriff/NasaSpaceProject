"""Small columnar JSON exports to public/data (one array per column, same index = same cell).

The main frontend file (frontend_cells.json) is built in frontend.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .likeness import BODIES, TOPO_FEATURES, Likeness

SCREENING_FEATURES: list[str] = ["temp_p", "slope_p90", "rough_p10", "elev_range"]
PLANET_FEATURES: list[str] = ["slope_p90", "rough_p10", "elev_range"]  # what cells.json has for Earth


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"), allow_nan=False)


def screening(cells: pd.DataFrame, front: Path) -> None:
    """cells.json (cells that pass everything) and excluded.json (the rest, with the reason)."""
    ok = cells[cells.passes_all]
    data: dict[str, list[Any]] = {"cell_id": ok.cell_id.tolist(), "lat": ok.lat.round(2).tolist(),
                                  "lon": ok.lon.round(2).tolist()}
    for f in SCREENING_FEATURES:
        data[f] = ok[f].round(3).tolist()
    _write_nan_ok(front / "cells.json", data)
    bad = cells[~cells.passes_all]
    _write(front / "excluded.json", {"cell_id": bad.cell_id.tolist(), "excluded_by": bad.excluded_by.tolist()})
    print(f"Exported cells.json ({len(ok):,} cells) and excluded.json ({len(bad):,} cells)")


def _write_nan_ok(path: Path, obj: Any) -> None:
    """cells.json was always written with NaN allowed (cells without terrain data)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"))


def planets(tables: dict[str, pd.DataFrame], sites: pd.DataFrame, front: Path) -> None:
    """<body>_cells.json for Moon / Mars and planet_sites.json."""
    for body, cells in tables.items():
        if body == "earth":
            continue
        data: dict[str, list[Any]] = {"cell_id": cells.cell_id.tolist(), "lat": cells.lat.round(2).tolist(),
                                      "lon": cells.lon.round(2).tolist()}
        for f in PLANET_FEATURES:
            data[f] = cells[f].round(3).tolist()
        _write(front / f"{body}_cells.json", data)
        print(f"Exported {body}_cells.json ({len(cells):,} cells)")
    _write(front / "planet_sites.json", sites.round(3).to_dict("records"))
    print(f"Exported planet_sites.json ({len(sites)} sites)")


def likeness(lk: Likeness, front: Path) -> None:
    """site_matches.json, earth_analog_scores.json, <body>_earth_match.json."""
    out_sites = []
    for (body, site), g in lk.matches.groupby(["body", "site"], sort=False):
        out_sites.append({
            "body": body, "site": site, "site_cell_id": int(g.site_cell_id.iloc[0]),
            "site_features": {f: round(float(g[f"site_{f}"].iloc[0]), 3) for f in TOPO_FEATURES},
            "matches": [{"rank": int(r["rank"]), "cell_id": int(r["earth_cell_id"]),
                         "lat": round(float(r["earth_lat"]), 2), "lon": round(float(r["earth_lon"]), 2),
                         "distance": round(float(r["distance"]), 4), "similarity": round(float(r["similarity"]), 4),
                         "features": {f: round(float(r[f"earth_{f}"]), 3) for f in TOPO_FEATURES},
                         "dz": {f: round(float(r[f"dz_{f}"]), 3) for f in TOPO_FEATURES}}
                        for _, r in g.iterrows()],
        })
    _write(front / "site_matches.json", {
        "features": TOPO_FEATURES,
        "scale": {"log_mean": lk.space.mu.round(5).tolist(), "log_sd": lk.space.sd.round(5).tolist()},
        "sites": out_sites,
    })
    e = lk.earth
    _write(front / "earth_analog_scores.json", {
        "cell_id": e.cell_id.tolist(),
        **{f"{b}_like": e[f"{b}_like"].round(4).tolist() for b in BODIES},
        **{f"{b}_match_id": e[f"{b}_match_id"].tolist() for b in BODIES},
    })
    for body in BODIES:
        df = lk.bodies[body]
        _write(front / f"{body}_earth_match.json", {
            "cell_id": df.cell_id.tolist(), "earth_match_id": df.earth_match_id.tolist(),
            "earth_match_sim": df.earth_match_sim.round(4).tolist(),
        })
    print("Exported site_matches.json, earth_analog_scores.json, moon_earth_match.json, mars_earth_match.json")
