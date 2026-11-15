"""Final frontend export: data/processed/cells_scored.parquet -> public/data/frontend_cells.json

Run:  mamba run -n spaceapps python scripts/export_frontend.py

REAL vs MOCK is decided automatically per layer, by which columns exist in cells_scored.parquet.
When a teammate's notebook adds the columns below, the mock is replaced with NO code change:

    elevation                                              (m, mean per 0.5 deg cell)
    label_<app>      "moon" | "mars" | "both" | ""         app in spacewalk, rover, craters, cave
    <app>_quality    0..1 (0 where label is "")
    score_<app>_moon, score_<app>_mars   0..1

The file is checked against the contract (validate()) BEFORE it is written; any inconsistency
stops the export. Contract: public/data/frontend_cells.d.ts, standalone check: scripts/validate_frontend.py
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import zoom

ROOT = Path(__file__).resolve().parents[1]          # absolute, independent of working folder
SRC = ROOT / "data" / "processed" / "cells_scored.parquet"
OUT = ROOT / "public" / "data" / "frontend_cells.json"

RES, NCOLS, NROWS = 0.5, 720, 360
MARGIN = 0.03                                       # |moon - mars| < MARGIN -> "both" (as Scoring.ipynb)
MOON, MARS = 1, 2                                   # label bitmask: 0 none, 1 moon, 2 mars, 3 both
APPS = ["spacewalk", "rover", "craters", "cave"]    # order = frontend chip order
LABEL_CODE = {"moon": MOON, "mars": MARS, "both": MOON | MARS}

# Mock settings (used only while the real columns are missing): gate, share of gated cells that become sites
MOCK_CFG = {
    "spacewalk": dict(seed=200, barren_min=30, share=0.35),
    "rover":     dict(seed=100, barren_min=50, share=0.35),
    "craters":   dict(seed=300, barren_min=20, share=0.08),
}


# ----------------------------------------------------------------------------- mock helpers
def smooth_field(seed, coarse=(18, 36)):
    """Spatially smooth random field in [0, 1] on the 360x720 grid (looks like real terrain)."""
    f = zoom(np.random.default_rng(seed).random(coarse),
             (NROWS / coarse[0], NCOLS / coarse[1]), order=3, mode="wrap")[:NROWS, :NCOLS]
    return (f - f.min()) / (f.max() - f.min())


def at_cells(field, cell_ids):
    r, c = np.divmod(cell_ids, NCOLS)
    return field[r, c]


def mock_elevation(cells):
    cold = 1 - cells.temp_p.fillna(0.5).to_numpy()
    noise = at_cells(smooth_field(2026), cells.cell_id.to_numpy())
    return np.clip(-200 + 4200 * noise**2 + 900 * cold, -100, 5500).round(0)


def mock_app(cells, elevation, app):
    cfg = MOCK_CFG[app]
    ids = cells.cell_id.to_numpy()
    barren = cells.barren_pct.fillna(0).to_numpy()
    dry = 1 - cells.precip_p.fillna(0.5).to_numpy()
    trange = cells.temp_range_p.fillna(0.5).to_numpy()
    elev_p = pd.Series(elevation).rank(pct=True).to_numpy()
    base = {"rover": 0.5 * dry + 0.5 * barren / 100,
            "spacewalk": 0.4 * dry + 0.3 * trange + 0.3 * elev_p,
            "craters": 0.6 * dry + 0.4 * barren / 100}[app]

    gate = (cells.pass_forest & cells.pass_urban).to_numpy() & (barren >= cfg["barren_min"])
    moon = np.where(gate, 0.55 * base + 0.45 * at_cells(smooth_field(cfg["seed"]), ids), 0.0)
    mars = np.where(gate, 0.55 * base + 0.45 * at_cells(smooth_field(cfg["seed"] + 1), ids), 0.0)
    quality = np.maximum(moon, mars)
    is_site = gate & (quality >= np.quantile(quality[gate], 1 - cfg["share"]))
    label = np.where(np.abs(moon - mars) < MARGIN, MOON | MARS, np.where(moon > mars, MOON, MARS))
    return np.where(is_site, label, 0), quality, moon, mars


def real_app(cells, app):
    label = cells[f"label_{app}"].fillna("").map(LABEL_CODE).fillna(0).astype(int).to_numpy()
    return (label, cells[f"{app}_quality"].fillna(0).to_numpy(),
            cells[f"score_{app}_moon"].fillna(0).to_numpy(),
            cells[f"score_{app}_mars"].fillna(0).to_numpy())


def has_real(cells, app):
    return all(c in cells for c in (f"label_{app}", f"{app}_quality", f"score_{app}_moon", f"score_{app}_mars"))


# ----------------------------------------------------------------------------- contract check
def validate(out):
    """Raise AssertionError on ANY inconsistency. Same rules as scripts/validate_frontend.py."""
    n = out["meta"]["n_cells"]
    cols = {k: out[k] for k in ("cell_id", "lat", "lon", "passes_all", "temp", "elevation")}
    for name, arr in cols.items():
        assert len(arr) == n, f"{name}: {len(arr)} entries, expected {n}"
        assert all(v is not None for v in arr), f"{name}: contains null"
    ids = np.array(out["cell_id"]); lat = np.array(out["lat"]); lon = np.array(out["lon"])
    assert len(set(ids.tolist())) == n, "cell_id not unique"
    assert ((ids >= 0) & (ids < NROWS * NCOLS)).all(), "cell_id outside grid"
    assert (lat >= -90).all() and (lat <= 90).all() and (lon >= -180).all() and (lon <= 180).all(), "lat/lon out of range"
    recomputed = ((90 - lat) // RES).astype(int) * NCOLS + ((lon + 180) // RES).astype(int)
    assert (recomputed == ids).all(), "cell_id does not match lat/lon"
    assert set(out["passes_all"]) <= {0, 1}, "passes_all must be 0/1"
    for key in ("temp", "elevation"):
        lo, hi = out["meta"]["ranges"][key]
        assert lo <= min(out[key]) and max(out[key]) <= hi, f"meta.ranges.{key} does not cover the data"

    assert list(out["apps"]) == APPS, f"apps must be exactly {APPS} in this order"
    for app, a in out["apps"].items():
        assert set(a) == {"label", "quality", "score_moon", "score_mars"}, f"{app}: wrong keys"
        for k, arr in a.items():
            assert len(arr) == n, f"{app}.{k}: {len(arr)} entries, expected {n}"
            assert all(v is not None for v in arr), f"{app}.{k}: contains null"
        label = np.array(a["label"])
        q, sm, sr = (np.array(a[k]) for k in ("quality", "score_moon", "score_mars"))
        assert set(label.tolist()) <= {0, 1, 2, 3}, f"{app}: label outside 0..3"
        for k, arr in (("quality", q), ("score_moon", sm), ("score_mars", sr)):
            assert (arr >= 0).all() and (arr <= 1).all(), f"{app}.{k} outside 0..1"
        site = label > 0
        assert (q[~site] == 0).all() and (sm[~site] == 0).all() and (sr[~site] == 0).all(), \
            f"{app}: non-zero quality/score on a cell that is not a site"
        assert (q[site] > 0).all(), f"{app}: site with quality 0"
        # label must agree with the two scores (same rule as Scoring.ipynb), up to rounding
        tie = np.abs(sm - sr) < MARGIN - 0.011
        far = np.abs(sm - sr) > MARGIN + 0.011
        assert (label[site & tie] == 3).all(), f"{app}: label 'both' expected inside the tie margin"
        assert (label[site & far & (sm > sr)] == MOON).all(), f"{app}: label should be moon"
        assert (label[site & far & (sr > sm)] == MARS).all(), f"{app}: label should be mars"
        assert site.any(), f"{app}: no site at all (empty layer)"
    assert out["meta"]["mocked"] == sorted(out["meta"]["mocked"]), "meta.mocked must be sorted"


# ----------------------------------------------------------------------------- build
def build():
    cells = pd.read_parquet(SRC)
    cells = cells.dropna(subset=["temp"]).sort_values("cell_id").reset_index(drop=True)
    mocked = []

    if "elevation" in cells:
        elevation = cells.elevation.fillna(cells.elevation.median()).round(0).to_numpy()
    else:
        elevation, _ = mock_elevation(cells), mocked.append("elevation")

    apps = {}
    for app in APPS:
        if has_real(cells, app):
            label, q, sm, sr = real_app(cells, app)
        else:
            label, q, sm, sr = mock_app(cells, elevation, app)
            mocked.append(app)
        site = label > 0                      # contract: quality/scores are 0 on non-sites
        apps[app] = {
            "label": label.astype(int).tolist(),
            "quality": np.where(site, np.clip(q, 0.01, 1), 0).round(2).tolist(),
            "score_moon": np.where(site, np.clip(sm, 0, 1), 0).round(2).tolist(),
            "score_mars": np.where(site, np.clip(sr, 0, 1), 0).round(2).tolist(),
        }

    out = {
        "meta": {
            "generated": date.today().isoformat(),
            "n_cells": int(len(cells)),
            "grid": {"res_deg": RES, "ncols": NCOLS, "nrows": NROWS, "crs": "EPSG:4326",
                     "cell_id": "row * 720 + col; row = floor((90 - lat) / 0.5); col = floor((lon + 180) / 0.5)",
                     "lat_lon": "cell centre; cell spans lat +-0.25, lon +-0.25"},
            "layout": "columnar: every array has n_cells entries, same index = same cell",
            "mocked": sorted(mocked),
            "label_codes": {"0": "not a site", "1": "moon", "2": "mars", "3": "both"},
            "filter_semantics": {
                "target moon": "label & 1", "target mars": "label & 2", "target both": "label == 3",
                "several targets": "any of the selected",
                "several applications": "all selected applications must match",
                "quality / scores": "0 on cells that are not a site for that application"},
            "ranges": {"temp": [round(float(cells.temp.min()), 1), round(float(cells.temp.max()), 1)],
                       "elevation": [float(elevation.min()), float(elevation.max())]},
            "units": {"temp": "deg C, annual mean (WorldClim BIO1)", "elevation": "m"},
        },
        "cell_id": cells.cell_id.astype(int).tolist(),
        "lat": cells.lat.round(2).tolist(),
        "lon": cells.lon.round(2).tolist(),
        "passes_all": cells.passes_all.astype(int).tolist(),   # forest/urban/water screening
        "temp": cells.temp.astype(float).round(1).tolist(),
        "elevation": elevation.astype(int).tolist(),
        "apps": apps,
    }
    return out


if __name__ == "__main__":
    data = build()
    validate(data)                                              # stops here if anything is inconsistent
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))
    print(f"OK  wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB), {data['meta']['n_cells']:,} cells")
    print(f"    mocked layers: {data['meta']['mocked'] or 'none'}")
    for app, a in data["apps"].items():
        lab = pd.Series(a["label"]).map({0: "none", 1: "moon", 2: "mars", 3: "both"}).value_counts().to_dict()
        print(f"    {app:<10}{lab}")
