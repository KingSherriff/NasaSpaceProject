# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.6
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Application scoring: cave exploration, rover testing, spacewalk (EVA), craters
# ## Reads cells.parquet, writes cells_scored.parquet

# %%
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import rioxarray
from sklearn.neighbors import BallTree
import matplotlib.pyplot as plt

RAW = Path("../data/raw")
OUT = Path("../data/processed")
for d in (RAW / "gvp", RAW / "craters"):
    d.mkdir(parents=True, exist_ok=True)

RES, NCOLS, NROWS = 0.5, 720, 360
R_EARTH_KM = 6371.0

def cell_id(lat, lon):
    lat = np.asarray(lat); lon = np.asarray(lon)
    return ((90 - lat) // RES).astype(int) * NCOLS + ((lon + 180) // RES).astype(int)


# %% [markdown]
# ## Load the master table (+ WorldClim climate layers if missing)

# %%
cells = pd.read_parquet(OUT / "cells.parquet")
need = ["temp_p", "barren_pct", "pass_forest", "pass_urban", "pass_water", "passes_all",
        "elev_mean", "slope_p90", "rough_p10", "moon_like", "mars_like"]
missing = [c for c in need if c not in cells]
if missing:
    raise ValueError(f"Missing columns {missing}: rerun 'Cells filtering' (terrain + Moon/Mars likeness cells)")
print(f"Loaded {len(cells):,} cells, {cells.passes_all.sum():,} pass the screening")

# --- WorldClim climate layers. Added here if cells.parquet does not carry them
#     (the wc05 cell was lost from 'Cells filtering' in a merge). Same method: 10' -> 0.5° mean (3x3).
WC = {"temp_min": 6, "temp_range": 7, "precip": 12}       # BIO6 (°C), BIO7 (°C), BIO12 (mm)
for name, n in WC.items():
    if name not in cells:
        a = rioxarray.open_rasterio(RAW / "worldclim" / f"wc2.1_10m_bio_{n}.tif", masked=True).squeeze()
        a = a.coarsen(x=3, y=3, boundary="trim").mean()
        lon2d, lat2d = np.meshgrid(a.x.values, a.y.values)
        by_id = pd.Series(a.values.ravel(), index=cell_id(lat2d, lon2d).ravel())
        cells[name] = cells.cell_id.map(by_id)
        print(f"+ {name} from WorldClim BIO{n} ({cells[name].notna().sum():,} cells)")
    cells[f"{name}_p"] = cells[name].rank(pct=True)

# %% [markdown]
# ## Derived features shared by all applications

# %%
cells["barren"] = cells.barren_pct.fillna(0) / 100

# Elevation (ETOPO 2022 mean per cell). Coastal cells average in sea floor, so clip at the
# lowest real land on Earth (Dead Sea shore, about -430 m). "elevation" is the frontend column.
cells["elevation"] = cells.elev_mean.clip(lower=-430)
cells["elev_p"] = cells.elevation.rank(pct=True)

# Terrain likeness to Moon / Mars (from 'Cells filtering') as Earth percentiles, so the two are comparable:
# raw mars_like is higher than moon_like almost everywhere.
for b in ("moon", "mars"):
    cells[f"{b}_like_p"] = cells[f"{b}_like"].rank(pct=True)

# Land-cover screening used by the surface applications (terrain rules are applied per application)
landcover_ok = cells.pass_forest & cells.pass_urban & cells.pass_water
print(f"Land-cover screening passed: {landcover_ok.sum():,} cells")

# %% [markdown]
# ## Download Smithsonian Holocene volcanoes (WFS → CSV)

# %%
GVP_CSV = RAW / "gvp" / "holocene_volcanoes.csv"
WFS = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs"

# --- Download (skipped if the file already exists) ---
if GVP_CSV.exists():
    print(f"✓ already have {GVP_CSV.name}")
else:
    caps = requests.get(WFS, params={"service": "WFS", "request": "GetCapabilities"}, timeout=60).text
    layer_names = re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", caps)
    holo = [n for n in layer_names if "holocene" in n.lower() and "volcan" in n.lower()]
    print("WFS layers:", layer_names)
    if not holo:
        raise ValueError("No Holocene volcano layer found; pick one from the list above")
    print("Using layer:", holo[0])
    r = requests.get(WFS, params={"service": "WFS", "version": "1.0.0", "request": "GetFeature",
                                  "typeName": holo[0], "outputFormat": "csv"}, timeout=120)
    r.raise_for_status()
    GVP_CSV.write_bytes(r.content)
    print(f"✓ downloaded {GVP_CSV.name}")

# --- Sanity check: did the server return data or an error? ---
head = GVP_CSV.read_text(errors="ignore")[:500]
if head.lstrip().startswith("<"):
    GVP_CSV.unlink()                      # delete the bad file so the next run re-downloads
    raise ValueError("WFS returned XML (an error), not CSV:\n" + head)

volc = pd.read_csv(GVP_CSV)
print("Volcano columns:", volc.columns.tolist())
print(volc.head(3).T)                     # look at the first rows

# --- Coordinates: fuzzy column match ---
def find_col(keys):
    for c in volc.columns:
        cl = c.lower()
        if any(k in cl for k in keys):
            return c
    return None

lat_c = find_col(["latitude", "lat"])
lon_c = find_col(["longitude", "lon", "long"])
geom_c = find_col(["geom", "shape", "wkt", "location"])

if lat_c and lon_c:
    volc["lat"] = pd.to_numeric(volc[lat_c], errors="coerce")
    volc["lon"] = pd.to_numeric(volc[lon_c], errors="coerce")
elif geom_c:
    xy = volc[geom_c].astype(str).str.extract(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)")
    volc["lon"], volc["lat"] = xy[0].astype(float), xy[1].astype(float)
else:
    raise ValueError("No coordinate columns found; see the column list printed above")

volc = volc.dropna(subset=["lat", "lon"])
print(f"Volcanoes with coordinates: {len(volc):,}")

# --- Basaltic volcanoes (lava tubes form in basalt) ---
# The WFS CSV has no rock-type column, so use VolcanoType as a proxy:
# shields, volcanic fields, fissure vents and lava cones are mostly effusive basalt,
# while stratovolcanoes, calderas and lava domes are mostly andesitic/explosive.
BASALTIC_TYPES = r"shield|volcanic field|fissure|lava cone|lava field|pyroclastic cone"
type_c = next((c for c in volc.columns if c.lower() == "volcanotype"), None)
if type_c:
    volc["basaltic"] = volc[type_c].astype(str).str.contains(BASALTIC_TYPES, case=False, regex=True)
    print("Volcano types counted as basaltic:")
    print(volc.loc[volc.basaltic, type_c].value_counts().to_string())
else:
    volc["basaltic"] = True
    print("⚠ No VolcanoType column found; using all volcanoes")
print(f"Volcanoes: {len(volc):,} total, {volc.basaltic.sum():,} basaltic")


# %% [markdown]
# ## Distance from each cell to the nearest basaltic volcano 

# %%
def nearest_km(df, pts):
    tree = BallTree(np.radians(pts[["lat", "lon"]].to_numpy()), metric="haversine")
    d, _ = tree.query(np.radians(df[["lat", "lon"]].to_numpy()), k=1)
    return d[:, 0] * R_EARTH_KM

cells["dist_basalt_volc_km"] = nearest_km(cells, volc[volc.basaltic])
# 1.0 within 25 km (≈ volcano in the cell), linear down to 0 at 100 km
cells["volc_prox"] = np.clip(1 - (cells.dist_basalt_volc_km - 25) / 75, 0, 1)


# %% [markdown]
# ## Scoring functions
# Suitability (gate + hard condition) decides the label; Moon vs Mars compares two target profiles; quality = max(moon, mars) ranks within a label.
#
# Mars profiles for the surface applications (rover, spacewalk, craters) are led by **dryness**: `precip_p` target 0.10 with weight 2, and `temp_p` target 0.40 with weight 1. Hyperarid deserts (Atacama) count as Mars analogs even when they are not cold. Caves keep the v1 profile (cold-led): surface dryness matters less underground.

# %%
def score(df, spec, gate):
    cols = list(spec["target"])
    w = np.array([spec["weights"][c] for c in cols], dtype=float)
    X = df[cols].to_numpy(dtype=float)
    t = np.array([spec["target"][c] for c in cols], dtype=float)
    dirs = [spec.get("dir", {}).get(c, "eq") for c in cols]

    diff = X - t
    for j, dname in enumerate(dirs):
        if dname == "max":              # only too high is bad
            diff[:, j] = np.maximum(diff[:, j], 0)
        elif dname == "min":            # only too low is bad
            diff[:, j] = np.minimum(diff[:, j], 0)

    valid = ~np.isnan(X)
    d = np.sqrt(np.nansum(w * diff ** 2, axis=1) / (valid * w).sum(axis=1))
    return np.where(gate, 1 - d, 0.0)


MARGIN = 0.03                     # |moon - mars| below this -> "both"
APPS = []                         # filled as each application is scored

def label_app(name, spec, gate, is_site):
    """One application: scores per body, label (moon / mars / both / ""), quality for ranking.

    gate     activity is plausible here -> scores are computed (0 outside)
    is_site  gate + hard condition      -> cell gets a label
    Adds: score_<name>_moon, score_<name>_mars, label_<name>, <name>_quality
    """
    for body, s in spec.items():
        cells[f"score_{name}_{body}"] = score(cells, s, gate)
    moon, mars = cells[f"score_{name}_moon"], cells[f"score_{name}_mars"]
    body = np.where((moon - mars).abs() < MARGIN, "both", np.where(moon > mars, "moon", "mars"))
    cells[f"label_{name}"] = np.where(is_site, body, "")
    cells[f"{name}_quality"] = np.where(is_site, np.maximum(moon, mars), 0.0)
    if name not in APPS:
        APPS.append(name)
    print(f"{name}: gate {gate.sum():,} cells, sites {is_site.sum():,} cells,",
          cells[f"label_{name}"].replace("", "none").value_counts().to_dict())

def top(name, extra, n=10):
    cols = ["cell_id", "lat", "lon"] + extra + [f"score_{name}_moon", f"score_{name}_mars", f"label_{name}"]
    display(cells[cells[f"label_{name}"] != ""].nlargest(n, f"{name}_quality")[cols].round(2))


# %% [markdown]
# ## Application 1: cave exploration (lava tubes)

# %%
# Gate: forest + urban screening + basaltic volcano within 100 km.
# Water is ignored for caves: nearby ocean doesn't affect a lava tube underground
# (keeps island sites like Lanzarote). Terrain rules are ignored too: lava fields are rough.
GATE_KM = 100
CAVE_KM = 50                                   # basaltic volcano in or next to the cell
cave_gate = cells.pass_forest & cells.pass_urban & (cells.dist_basalt_volc_km <= GATE_KM)

CAVE = {
    "moon": {"target":  {"volc_prox": 1.0,   "precip_p": 0.20,  "barren": 1.0},
             "weights": {"volc_prox": 3,     "precip_p": 1,     "barren": 0.5},
             "dir":     {"volc_prox": "min", "precip_p": "max", "barren": "min"}},
    "mars": {"target":  {"volc_prox": 1.0,   "precip_p": 0.20,  "temp_p": 0.10,  "barren": 1.0},
             "weights": {"volc_prox": 3,     "precip_p": 1,     "temp_p": 2,     "barren": 0.5},
             "dir":     {"volc_prox": "min", "precip_p": "max", "temp_p": "max", "barren": "min"}},
}
label_app("cave", CAVE, cave_gate, cave_gate & (cells.dist_basalt_volc_km <= CAVE_KM))
top("cave", ["dist_basalt_volc_km", "precip_p", "temp_p", "barren"])

# %% [markdown]
# ## Application 2: rover testing

# %%
# Gate: land-cover screening + mostly bare ground (barren >= 50 %).
# Hard condition: a rover can drive it -> the cell passes the terrain rules of the screening
# (slope_p90 <= 15°, rough_p10 <= 15 m).
# Moon / Mars: how close the terrain statistics (slope, roughness, relief, hypsometry) are to the
# real Moon / Mars DEMs (moon_like / mars_like, as Earth percentiles), plus dryness and bare ground.
# Mars: stricter dryness (driest 10 % of Earth, double weight) and cooler than the warmest 60 %.
# Sand (ASTER GED emissivity) is not in yet.
ROVER_BARREN = 0.50
rover_gate = landcover_ok & (cells.barren >= ROVER_BARREN)
rover_site = rover_gate & cells.pass_slope & cells.pass_rough

ROVER = {
    "moon": {"target":  {"moon_like_p": 0.90,  "precip_p": 0.20,  "barren": 1.0},
             "weights": {"moon_like_p": 3,     "precip_p": 1,     "barren": 1},
             "dir":     {"moon_like_p": "min", "precip_p": "max", "barren": "min"}},
    "mars": {"target":  {"mars_like_p": 0.90,  "precip_p": 0.10,  "barren": 1.0,   "temp_p": 0.40},
             "weights": {"mars_like_p": 3,     "precip_p": 2,     "barren": 1,     "temp_p": 1},
             "dir":     {"mars_like_p": "min", "precip_p": "max", "barren": "min", "temp_p": "max"}},
}
label_app("rover", ROVER, rover_gate, rover_site)
top("rover", ["moon_like_p", "mars_like_p", "precip_p", "temp_p", "barren", "slope_p90"])

# %% [markdown]
# ## Application 3: spacewalk / EVA

# %%
# Gate: land-cover screening + open ground (barren >= 30 %).
# Hard condition: walkable in a suit -> slope_p90 <= 15° (screening slope rule).
# Moon: large temperature swings (BIO7 annual range), dry, bare, high (thin air / radiation proxy).
# Mars: very dry first (driest 10 % of Earth), then high elevation (low pressure), cool, bare,
#       some temperature swing.
EVA_BARREN = 0.30
eva_gate = landcover_ok & (cells.barren >= EVA_BARREN)
eva_site = eva_gate & cells.pass_slope

SPACEWALK = {
    "moon": {"target":  {"temp_range_p": 0.90,  "precip_p": 0.20,  "barren": 1.0,   "elev_p": 0.80},
             "weights": {"temp_range_p": 2,     "precip_p": 1,     "barren": 1,     "elev_p": 1},
             "dir":     {"temp_range_p": "min", "precip_p": "max", "barren": "min", "elev_p": "min"}},
    "mars": {"target":  {"temp_p": 0.40,  "elev_p": 0.80,  "precip_p": 0.10,  "barren": 1.0,   "temp_range_p": 0.70},
             "weights": {"temp_p": 1,     "elev_p": 1.5,   "precip_p": 2,     "barren": 1,     "temp_range_p": 0.5},
             "dir":     {"temp_p": "max", "elev_p": "min", "precip_p": "max", "barren": "min", "temp_range_p": "min"}},
}
label_app("spacewalk", SPACEWALK, eva_gate, eva_site)
top("spacewalk", ["temp_range_p", "temp_p", "elev_p", "precip_p", "barren"])

# %% [markdown]
# ## Application 4: craters
# ### Download impact structures

# %%
# Impact structures on Earth from Wikidata (CC0): instances of "impact crater" (Q55818) whose
# coordinates are on Earth. Stand-in for the Earth Impact Database / Kenkmann 2021, which have no API.
CRATER_CSV = RAW / "craters" / "wikidata_impact_craters.csv"
SPARQL = "https://query.wikidata.org/sparql"
QUERY = """
SELECT ?item ?itemLabel ?lat ?lon ?diam WHERE {
  ?item wdt:P31/wdt:P279* wd:Q55818 ; p:P625/psv:P625 ?c .
  ?c wikibase:geoGlobe wd:Q2 ; wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
  OPTIONAL { ?item wdt:P2386 ?diam }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}"""

if CRATER_CSV.exists():
    print(f"✓ already have {CRATER_CSV.name}")
else:
    r = requests.get(SPARQL, params={"query": QUERY}, timeout=120,
                     headers={"Accept": "text/csv", "User-Agent": "analog-finder-hackathon/0.1"})
    r.raise_for_status()
    CRATER_CSV.write_bytes(r.content)
    print(f"✓ downloaded {CRATER_CSV.name}")

craters = (pd.read_csv(CRATER_CSV)
             .rename(columns={"itemLabel": "name", "diam": "diameter_km"})
             .dropna(subset=["lat", "lon"])
             .drop_duplicates("item")
             .reset_index(drop=True))
print(f"Impact structures: {len(craters):,} ({craters.diameter_km.notna().sum()} with a diameter)")

cells["dist_crater_km"] = nearest_km(cells, craters)
# 1.0 within 25 km (≈ crater in the cell), linear down to 0 at 100 km (same shape as volc_prox)
cells["crater_prox"] = np.clip(1 - (cells.dist_crater_km - 25) / 75, 0, 1)

# %% [markdown]
# ### Crater scoring

# %%
# Gate: land-cover screening (a crater under forest, a city or a lake is not an exposed analog)
#       + impact structure within 100 km. Crater site = within 50 km (crater in or next to the cell).
# Terrain rules are not applied: crater rims are steep by nature.
# Profiles follow the caves: proximity first, then dryness and bare ground (preserved, visible
# morphology); Mars is stricter on dryness (driest 10 %, double weight) and adds cool climate.
CRATER_GATE_KM = 100
CRATER_KM = 50
crater_gate = landcover_ok & (cells.dist_crater_km <= CRATER_GATE_KM)

CRATERS = {
    "moon": {"target":  {"crater_prox": 1.0,   "precip_p": 0.20,  "barren": 1.0},
             "weights": {"crater_prox": 3,     "precip_p": 1,     "barren": 1},
             "dir":     {"crater_prox": "min", "precip_p": "max", "barren": "min"}},
    "mars": {"target":  {"crater_prox": 1.0,   "precip_p": 0.10,  "temp_p": 0.40,  "barren": 1.0},
             "weights": {"crater_prox": 3,     "precip_p": 2,     "temp_p": 1,     "barren": 1},
             "dir":     {"crater_prox": "min", "precip_p": "max", "temp_p": "max", "barren": "min"}},
}
label_app("craters", CRATERS, crater_gate, crater_gate & (cells.dist_crater_km <= CRATER_KM))
top("craters", ["dist_crater_km", "precip_p", "temp_p", "barren"])

# %% [markdown]
# ## Validation

# %%
# Known analog sites and the application they are used for. A site should get a label in "its" column.
sites = pd.DataFrame([
    ("cave",      "Craters of the Moon, Idaho",     43.42, -113.52),
    ("cave",      "Lava Beds, California",          41.71, -121.51),
    ("cave",      "Mauna Loa (HI-SEAS), Hawaii",    19.60, -155.47),
    ("cave",      "Cueva de los Verdes, Lanzarote", 29.16,  -13.44),
    ("cave",      "Undara, Australia",             -18.20,  144.60),
    ("cave",      "Raufarhólshellir, Iceland",      64.02,  -21.40),
    ("rover",     "Atacama (Yungay), Chile",       -24.08,  -69.92),
    ("rover",     "MDRS, Utah",                     38.41, -110.79),
    ("rover",     "Ramon Crater (D-MARS), Negev",   30.61,   34.80),
    ("rover",     "Erfoud (Ibn Battuta), Morocco",  31.43,   -4.23),
    ("spacewalk", "Black Point Lava Flow, Arizona", 35.70, -111.40),
    ("spacewalk", "Qaidam Basin, China",            38.00,   93.00),
    ("spacewalk", "Mauna Kea, Hawaii",              19.82, -155.47),
    ("craters",   "Meteor Crater, Arizona",         35.03, -111.02),
    ("craters",   "Haughton, Devon Island",         75.38,  -89.67),
    ("craters",   "Gosses Bluff, Australia",       -23.82,  132.31),
    ("craters",   "Roter Kamm, Namibia",           -27.77,   16.29),
    ("craters",   "Wolfe Creek, Australia",        -19.17,  127.80),
], columns=["used_for", "name", "lat", "lon"])
sites["cell_id"] = cell_id(sites.lat, sites.lon)

cols = ["cell_id", "barren", "precip_p", "temp_p", "slope_p90"] + [f"label_{a}" for a in APPS] + ["excluded_by"]
check = sites.merge(cells[cols], on="cell_id", how="left")
check["excluded_by"] = check["excluded_by"].fillna("not a land cell")
check["hit"] = [isinstance(r[f"label_{r.used_for}"], str) and r[f"label_{r.used_for}"] != "" for _, r in check.iterrows()]
print(f"Known sites labelled for their own application: {check.hit.sum()} of {len(check)}")
display(check.drop(columns=["cell_id", "lat", "lon"]).round(2))

# %% [markdown]
# ## Maps

# %%
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

def to_grid(values):
    grid = np.full((NROWS, NCOLS), np.nan)
    r, c = np.divmod(cells.cell_id.values, NCOLS)
    grid[r, c] = values
    return grid

land = to_grid(np.ones(len(cells)))                      # background: all land cells, light grey
colors = {1: "#f0a500", 2: "#c1440e", 3: "#7b3fa0"}     # moon / mars / both
EXTENT = [-180, 180, -90, 90]

# Map 1: label per application
fig, axes = plt.subplots(2, 2, figsize=(22, 11))
for ax, app in zip(axes.ravel(), APPS):
    lab = to_grid(cells[f"label_{app}"].map({"moon": 1, "mars": 2, "both": 3}).fillna(0).values)
    lab[lab == 0] = np.nan
    ax.imshow(land, extent=EXTENT, cmap=ListedColormap(["#e6e6e6"]))
    ax.imshow(lab, extent=EXTENT, cmap=ListedColormap([colors[1], colors[2], colors[3]]),
              vmin=1, vmax=3, interpolation="nearest")
    s = sites[sites.used_for == app]
    ax.scatter(s.lon, s.lat, c="cyan", s=30, edgecolor="k", zorder=3)
    ax.set_title(f"{app}: Moon vs Mars ({(cells[f'label_{app}'] != '').sum():,} cells)")
axes[0, 0].legend(handles=[Patch(color=colors[1], label="Moon"), Patch(color=colors[2], label="Mars"),
                           Patch(color=colors[3], label="both"), Patch(color="#e6e6e6", label="not a site")],
                  loc="lower left")
plt.tight_layout(); plt.show()

# Map 2: quality per application (ranking score within the labelled cells)
fig, axes = plt.subplots(2, 2, figsize=(22, 11))
for ax, app in zip(axes.ravel(), APPS):
    q = to_grid(cells[f"{app}_quality"].values)
    q[q == 0] = np.nan
    ax.imshow(land, extent=EXTENT, cmap=ListedColormap(["#e6e6e6"]))
    im = ax.imshow(q, extent=EXTENT, cmap="magma", vmin=0.4, vmax=1, interpolation="nearest")
    ax.set_title(f"{app}: quality (best of Moon / Mars score)")
    plt.colorbar(im, ax=ax, fraction=0.025)
plt.tight_layout(); plt.show()

# %% [markdown]
# ## Save (base table stays untouched)

# %%
cells.to_parquet(OUT / "cells_scored.parquet", index=False)
print(f"Saved {OUT / 'cells_scored.parquet'} with applications {APPS}")
print("Next: python scripts/export_frontend.py  (uses the real columns automatically)")
