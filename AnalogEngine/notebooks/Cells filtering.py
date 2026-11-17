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
# # INITIAL FILTERING

# %% [markdown]
# ## Imports

# %%
import json
import glob
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from joblib import Parallel, delayed
from pathlib import Path
from rasterio.enums import Resampling
from scipy import ndimage
from scipy.spatial import cKDTree

import numpy as np
import pandas as pd
import rasterio
import requests
import rioxarray
import earthaccess

ETOPO_SIZE = "60"
RAW = Path("../data/raw")
OUT = Path("../data/processed")
GEDI_DIR = RAW / "gedi"
FRONT = Path("../public/data")
for d in (RAW / "worldclim", RAW / "modis_lc", RAW / "etopo", FRONT, GEDI_DIR, OUT):
    d.mkdir(parents=True, exist_ok=True)

RES = 0.5
NCOLS = int(360 / RES)            # 720


# %% [markdown]
# ## Data download (skips files already present)

# %%
def download(url, dest):
    dest = Path(dest)
    if dest.exists():
        print(f"✓ already have {dest.name}")
        return dest
    print(f"↓ downloading {dest.name} ...")
    tmp = dest.with_suffix(".part")             # renamed when complete, so an interrupted run is retried
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.replace(dest)
    return dest

# WorldClim 2.1 bioclim, 10 arc-minutes
WC_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
wc_zip = download(WC_URL, RAW / "worldclim" / "wc2.1_10m_bio.zip")
wc_bio1 = RAW / "worldclim" / "wc2.1_10m_bio_1.tif"
if not wc_bio1.exists():
    with zipfile.ZipFile(wc_zip) as z:
        z.extractall(RAW / "worldclim")
    print("✓ unzipped WorldClim")

# MODIS MCD12C1 land cover (NASA Earthdata login needed)
existing_lc = sorted((RAW / "modis_lc").glob("MCD12C1*.hdf"))
if existing_lc:
    lc_path = existing_lc[-1]
    print(f"✓ already have {lc_path.name}")
else:
    earthaccess.login(persist=True)
    res = earthaccess.search_data(short_name="MCD12C1", version="061",
                                  temporal=("2022-01-01", "2022-12-31"))
    lc_path = Path(earthaccess.download(res[:1], str(RAW / "modis_lc"))[0])
    print(f"✓ downloaded {lc_path.name}")

# GEDI biomass (AGBD), full mission, 12 km
existing_gedi = sorted(GEDI_DIR.glob("*agbd*20230316*12000m.tif"))
if existing_gedi:
    gedi_path = existing_gedi[0]
    print(f"✓ already have {gedi_path.name}")
else:
    earthaccess.login(persist=True)
    gedi_res = earthaccess.search_data(concept_id="C3043630107-ORNL_CLOUD")
    names = [g["umm"]["GranuleUR"] for g in gedi_res]
    want = [(g, n) for g, n in zip(gedi_res, names)
            if "_agbd-" in n and "20190417_20230316" in n and n.endswith("12000m.tif")]
    want.sort(key=lambda gn: "_vf_" not in gn[1])                  # prefer _vf_
    if not want:
        print("No matching AGBD file. Available biomass files:")
        print("\n".join(n for n in names if "agbd" in n))
        raise SystemExit("Adjust the GEDI file selection")
    print("picked:", want[0][1])
    gedi_path = Path(earthaccess.download([want[0][0]], str(GEDI_DIR))[0])

# ETOPO 2022 bedrock elevation, 15 arc-seconds, 15° tiles (NOAA NGDC, no login needed)
ETOPO_URL = "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_surface_elev_gtif/"
existing_etopo = sorted((RAW / "etopo").glob("ETOPO_2022_v1_15s_*_bed.tif"))

# ETOPO_URL = "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/60s_bed_elev_gtif/"
# existing_etopo = sorted((RAW / "etopo").glob("ETOPO_2022_v1_60s_*_bed.tif"))
try:
    listing = requests.get(ETOPO_URL, timeout=120)
    listing.raise_for_status()
    tiles = sorted(set(re.findall(r'ETOPO_2022[^"<>]*\.tif', listing.text)))
except requests.RequestException as e:
    if not existing_etopo:
        raise
    tiles = [p.name for p in existing_etopo]
    print(f"! could not list ETOPO tiles ({type(e).__name__}), using the {len(tiles)} already on disk")
new_tiles = [n for n in tiles if not (RAW / "etopo" / n).exists()]
with ThreadPoolExecutor(4) as pool:
    list(pool.map(lambda n: download(ETOPO_URL + n, RAW / "etopo" / n), new_tiles))
etopo_paths = [RAW / "etopo" / n for n in tiles]
print(f"✓ already have {len(tiles) - len(new_tiles)} of {len(tiles)} ETOPO tiles, downloaded {len(new_tiles)}")


# %% [markdown]
# ## Stable cell ID

# %%
def cell_id(lat, lon):
    lat = np.asarray(lat); lon = np.asarray(lon)
    row = ((90 - lat) // RES).astype(int)       # 0 = northernmost row
    col = ((lon + 180) // RES).astype(int)      # 0 = lon -180
    return row * NCOLS + col


# %% [markdown]
# ## Base grid: WorldClim temperature (defines land cells)

# %%
t = rioxarray.open_rasterio(f"{RAW}/worldclim/wc2.1_10m_bio_1.tif", masked=True).squeeze()
t05 = t.coarsen(x=3, y=3, boundary="trim").mean().rio.write_crs(4326)

# %% [markdown]
# ## MODIS land cover (% per IGBP class)

# %%
try:
    with rasterio.open(lc_path) as src:
        sds = next(s for s in src.subdatasets if s.endswith("Land_Cover_Type_1_Percent"))
    pct = rioxarray.open_rasterio(sds, masked=True).squeeze()
except rasterio.errors.RasterioIOError:
    # pip/uv builds of GDAL have no HDF4 driver (conda's libgdal-hdf4 does): read with pyhdf instead
    import xarray as xr
    from pyhdf.SD import SD
    raw = SD(str(lc_path)).select("Land_Cover_Type_1_Percent").get()    # (y, x, class) uint8
    step = 180 / raw.shape[0]                                           # 0.05° global grid, row 0 = north
    pct = xr.DataArray(np.moveaxis(raw, -1, 0), dims=("band", "y", "x"),
                       coords={"band": np.arange(1, raw.shape[-1] + 1),
                               "y": 90 - step * (np.arange(raw.shape[0]) + 0.5),
                               "x": -180 + step * (np.arange(raw.shape[1]) + 0.5)})
print("Land cover bands:", dict(pct.sizes))     # expect band: 17 → band = class + 1

def igbp(c):
    """Percent of IGBP class c per 0.5° cell, aligned to t05."""
    band = pct.sel(band=c + 1)
    band = band.where(band != 255)              # 255 = fill (already NaN when read through GDAL)
    return (band.coarsen(x=10, y=10, boundary="trim").mean().rio.write_crs(4326).rio.reproject_match(t05))

layers = {
    "water_pct":  igbp(0),
    "forest_pct": sum(igbp(c) for c in range(1, 6)),
    "urban_pct":  igbp(13),
    "snow_pct":   igbp(15),     # info only
    "barren_pct": igbp(16),     # info only
}

# %% [markdown]
# ## GEDI biomass → 0.5° grid

# %%
with rasterio.open(gedi_path) as src:
    print(f"GEDI: CRS={src.crs} | bands={src.count} | nodata={src.nodata}")
    print("GEDI band descriptions:", src.descriptions)
    descs = src.descriptions
mean_band = next((i + 1 for i, d in enumerate(descs) if d and "mean" in d.lower()), 1)
print("Using GEDI band:", mean_band)

gedi = rioxarray.open_rasterio(gedi_path, masked=True)
agbd = gedi.sel(band=mean_band) if "band" in gedi.dims else gedi
layers["biomass"] = agbd.rio.reproject_match(t05, resampling=Resampling.average)

# %% [markdown]
# ## Elevation & Slope restrictions

# %%
### ETOPO 2022 bedrock: slope, ruggedness, elevation stats per 0.5° cell
assert etopo_paths, "No ETOPO tiles found, run the data download cell first"

def compute_etopo_features(tif_path, target_da, res_deg=0.5, px_per_cell=120):
    """Slope (deg), TRI (m), elevation stats aggregated to 0.5° cells.
    Returns dict of 2D arrays aligned to target_da (t05) via reproject_match.
    """
    with rasterio.open(tif_path) as src:
        H, W = src.height, src.width
        tr = src.transform
        nodata = src.nodata
        top, left = src.bounds.top, src.bounds.left
        crs = src.crs
        epsg = crs.to_epsg()
        if epsg not in (4326, 9518):
            raise ValueError(f"Unexpected CRS: {crs} (EPSG:{epsg})")
        dy_m = abs(tr.e) * 110574

    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]) / 8
    ky = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]]) / (8 * dy_m)

    def block_stat(arr, func):
        h, w = arr.shape
        hb, wb = h // px_per_cell, w // px_per_cell
        a = arr[:hb*px_per_cell, :wb*px_per_cell].reshape(hb, px_per_cell, wb, px_per_cell)
        with np.errstate(all="ignore"):
            return func(a, axis=(1, 3))

    def block_percentiles(arr, qs):
        """Exact np.nanpercentile per block for several percentiles at once (one sort instead of one per percentile)."""
        h, w = arr.shape
        hb, wb = h // px_per_cell, w // px_per_cell
        flat = (arr[:hb*px_per_cell, :wb*px_per_cell].reshape(hb, px_per_cell, wb, px_per_cell)
                .transpose(0, 2, 1, 3).reshape(hb, wb, -1))
        s = np.sort(flat, axis=-1)                                  # NaN sorts to end
        n_valid = np.sum(~np.isnan(flat), axis=-1)
        out = []
        for q in qs:
            idx = (n_valid - 1) * (q / 100.0)                       # linear-interp position
            lo = np.clip(np.floor(idx).astype(int), 0, s.shape[-1] - 1)
            hi = np.clip(np.ceil(idx).astype(int), 0, s.shape[-1] - 1)
            v_lo = np.take_along_axis(s, lo[..., None], axis=-1)[..., 0]
            v_hi = np.take_along_axis(s, hi[..., None], axis=-1)[..., 0]
            v = v_lo + (idx - np.floor(idx)) * (v_hi - v_lo)
            v[n_valid == 0] = np.nan
            out.append(v)
        return out

    nb_y, nb_x = H // px_per_cell, W // px_per_cell
    blocks = {k: np.full((nb_y, nb_x), np.nan)
              for k in ("elev_min", "elev_max", "elev_mean", "elev_p05", "elev_p95",
                        "slope_mean", "slope_p50", "slope_p90", "rough_p10", "rough_p50")}

    strip_h = 1080
    with rasterio.open(tif_path) as src:
        for y0 in range(0, H, strip_h):
            window = rasterio.windows.Window(0, y0, W, min(strip_h, H - y0))
            dem = src.read(1, window=window).astype("float64")
            if nodata is not None:
                dem[dem == nodata] = np.nan

            lat = top - abs(tr.e) * (np.arange(y0, y0 + dem.shape[0]) + 0.5)
            dx_m = (abs(tr.a) * 111320 * np.cos(np.radians(lat)))[:, None]

            dem_f = np.where(np.isnan(dem), np.nanmean(dem), dem)
            dzdx = ndimage.convolve(dem_f, kx, mode="nearest") / dx_m
            dzdy = ndimage.convolve(dem_f, ky, mode="nearest")
            slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
            slope[np.isnan(dem)] = np.nan

            tri = np.zeros_like(dem)
            cnt = np.zeros_like(dem)
            for ddy, ddx in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
                nb = np.roll(np.roll(dem, ddy, 0), ddx, 1)
                d = np.abs(dem - nb)
                v = ~np.isnan(d)
                tri[v] += d[v]; cnt[v] += 1
            tri = np.where(cnt > 0, tri / np.maximum(cnt, 1), np.nan)

            b0 = y0 // px_per_cell
            b1 = b0 + dem.shape[0] // px_per_cell
            blocks["slope_mean"][b0:b1] = block_stat(slope, np.nanmean)
            blocks["slope_p50"][b0:b1], blocks["slope_p90"][b0:b1] = block_percentiles(slope, [50, 90])
            blocks["rough_p10"][b0:b1], blocks["rough_p50"][b0:b1] = block_percentiles(tri, [10, 50])
            blocks["elev_min"][b0:b1] = block_stat(dem, np.nanmin)
            blocks["elev_max"][b0:b1] = block_stat(dem, np.nanmax)
            blocks["elev_mean"][b0:b1] = block_stat(dem, np.nanmean)
            blocks["elev_p05"][b0:b1], blocks["elev_p95"][b0:b1] = block_percentiles(dem, [5, 95])

        blocks["elev_range"] = blocks["elev_max"] - blocks["elev_min"]
        blocks["relief_p90"] = blocks["elev_p95"] - blocks["elev_p05"]       # relief without the extreme pixels
        with np.errstate(all="ignore"):                                      # 0 = plain with peaks, 1 = plateau with pits
            blocks["hyps"] = np.where(blocks["elev_range"] > 0,
                                      (blocks["elev_mean"] - blocks["elev_min"]) / blocks["elev_range"], 0.5)

    out = {}
    for name, arr in blocks.items():
        import xarray as xr
        x = left + res_deg * (np.arange(arr.shape[1]) + 0.5)
        y = top  - res_deg * (np.arange(arr.shape[0]) + 0.5)
        da = xr.DataArray(arr, dims=("y", "x"),
                          coords={"y": y, "x": x}).rio.write_crs(4326)
        if da.x.max() > 180:
            da = da.assign_coords(x=(((da.x + 180) % 360) - 180)).sortby("x")
        out[name] = da.rio.reproject_match(target_da)
    return out

results = Parallel(n_jobs=4)(
    delayed(compute_etopo_features)(p, t05) for p in etopo_paths
)

etopo_layers = {}
for tile_feats in results:
    for k, v in tile_feats.items():
        etopo_layers[k] = v if k not in etopo_layers else etopo_layers[k].fillna(v)

print("ETOPO layers:", {k: dict(v.sizes) for k, v in etopo_layers.items()})
print(f"ETOPO coverage: {len(etopo_paths)} tiles, "
      f"{int(etopo_layers['slope_p90'].notnull().sum()):,} of {etopo_layers['slope_p90'].size:,} cells have terrain data")

# %% [markdown]
# ## Master table: one row per land cell

# %%
lon2d, lat2d = np.meshgrid(t05.x.values, t05.y.values)
cells = pd.DataFrame({"lat": lat2d.ravel(), "lon": lon2d.ravel(),
                      "temp": t05.values.ravel()})

for name, da in {**layers, **etopo_layers}.items():
    cells[name] = da.values.ravel()

cells = cells.dropna(subset=["temp"]).reset_index(drop=True)
cells.insert(0, "cell_id", cell_id(cells.lat, cells.lon))
cells["polar"] = cells.lat.abs() > 75
cells["temp_p"] = cells["temp"].rank(pct=True)

# biomass gap-fill outside GEDI coverage (>52° lat) for bare/ice cells
bare = (cells.barren_pct.fillna(0) + cells.snow_pct.fillna(0)) > 80
cells.loc[cells.biomass.isna() & bare, "biomass"] = 0.0
cells["biomass_p"] = cells["biomass"].rank(pct=True)           # NaN stays NaN

print(f"Land cells: {len(cells):,}")
print("Biomass (Mg/ha?) summary:\n", cells.biomass.describe().round(1))

expected = {"forest_pct", "urban_pct", "water_pct", "slope_p90", "rough_p10"}
missing = expected - set(cells.columns)
assert not missing, f"master table is missing {missing}; got {sorted(cells.columns)}"

# %% [markdown]
# ## Filter registry

# %%
FILTERS = {
    "forest": lambda df: df.forest_pct.fillna(0) <= 10,
    "urban":  lambda df: df.urban_pct.fillna(0)  <= 2,
    "water":  lambda df: df.water_pct.fillna(0)  <= 25,
    # terrain — only apply where ETOPO covers the cell
    "slope":  lambda df: df.slope_p90.fillna(0)  <= 15,
    "rough":  lambda df: df.rough_p10.fillna(0)  <= 15,
    # add later, e.g.: "protected": lambda df: df.protected_share.fillna(0) < 0.5,
}

def apply_filters(df):
    pass_cols = []
    for name, rule in FILTERS.items():
        col = f"pass_{name}"
        df[col] = rule(df)
        pass_cols.append(col)
    df["passes_all"] = df[pass_cols].all(axis=1)
    df["excluded_by"] = df[pass_cols].apply(
        lambda r: ", ".join(c[5:] for c in pass_cols if not r[c]), axis=1)
    return df

cells = apply_filters(cells)

# %% [markdown]
# ## Funnel (for the pitch)

# %%
print("\nFunnel:")
remaining = np.ones(len(cells), dtype=bool)
print(f"  start     : {remaining.sum():,} cells")
for name in FILTERS:
    remaining &= cells[f"pass_{name}"].values
    print(f"  after {name:<6}: {remaining.sum():,} cells")

# %% [markdown]
# ## Validation: do known analogs survive?

# %%
analogs = pd.DataFrame([
    ("Atacama Desert",        -24.50,  -69.25),
    ("Antarctic Dry Valleys", -77.50,  162.00),
    ("Haughton Crater",        75.38,  -89.67),
    ("Mauna Kea",              19.82, -155.47),
    ("Black Point Lava Flow",  35.70, -111.40),
    ("Rio Tinto",              37.70,   -6.60),
    ("Teide",                  28.27,  -16.64),
], columns=["name", "lat", "lon"])
analogs["cell_id"] = cell_id(analogs.lat, analogs.lon)

cols = ["cell_id", "forest_pct", "urban_pct", "water_pct", "biomass", "passes_all", "excluded_by"]
check = analogs.merge(cells[cols], on="cell_id", how="left")
check["passes_all"] = check["passes_all"].fillna(False)
check["excluded_by"] = check["excluded_by"].fillna("not a land cell")
print("\nKnown analogs:")
display(check[["name", "forest_pct", "urban_pct", "water_pct", "biomass",
               "passes_all", "excluded_by"]].round(1))


# %%
TOPO_FEATURES = ["slope_p50", "slope_p90", "rough_p50", "relief_p90", "hyps"]
LINEAR = {"hyps"}                 # already 0..1, not log-scaled
EARTH_RULES = ["pass_forest", "pass_urban", "pass_water"] # land-cover rules an Earth cell must pass; terrain rules are NOT applied
TOP_N = 10                        # Earth matches kept per reference site
MIN_SEP_KM = 300                  # matches for one site must be this far apart, so the list is not one cluster
K_LIKE = 25                       # neighbours used for the Moon-/Mars-likeness score
EARTH_R_KM = 6371

earth = cells[cells[EARTH_RULES].all(axis=1)].dropna(subset=TOPO_FEATURES).reset_index(drop=True)
bodies = {"earth": earth,
          "moon": pd.read_parquet(OUT / "moon_cells.parquet"),
          "mars": pd.read_parquet(OUT / "mars_cells.parquet")}
sites = pd.read_parquet(OUT / "planet_sites.parquet")

for body, df in bodies.items():
    print(f"{body:<5}: {len(df):>6,} cells")
print(f"Earth candidates: {len(earth):,} of {len(cells):,} land cells pass {EARTH_RULES}")


# %%
def logf(df):
    X = np.array(df[TOPO_FEATURES], dtype=float)
    k = [j for j, f in enumerate(TOPO_FEATURES) if f not in LINEAR]
    X[:, k] = np.log1p(X[:, k])
    return X


# one scale for all bodies, each body weighted equally whatever its cell count
mus = np.array([logf(df).mean(axis=0) for df in bodies.values()])
vrs = np.array([logf(df).var(axis=0) for df in bodies.values()])
MU = mus.mean(axis=0)
SD = np.sqrt((vrs + (mus - MU) ** 2).mean(axis=0))

WEIGHTS = {"slope_p50": 1, "slope_p90": 1, "rough_p50": 1, "relief_p90": 1, "hyps": 2}
W = np.sqrt([WEIGHTS.get(f, 1) for f in TOPO_FEATURES])

def to_z(df):
    return (logf(df) - MU) / SD * W

Z = {body: to_z(df) for body, df in bodies.items()}
trees = {body: cKDTree(z) for body, z in Z.items()}

def similarity(d):
    """Distance in feature space -> 0..1 score (1 = identical terrain statistics)."""
    return np.exp(-np.asarray(d))

print(pd.DataFrame(np.corrcoef(np.vstack(list(Z.values())).T), index=TOPO_FEATURES, columns=TOPO_FEATURES).round(2))
print(pd.DataFrame({"log_mean": MU, "log_sd": SD}, index=TOPO_FEATURES).round(3))


# %%
def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))

def earth_matches(z_target, top_n=TOP_N, min_sep_km=MIN_SEP_KM):
    """Closest Earth cells to one target point, thinned so no two are within min_sep_km."""
    dist = np.linalg.norm(Z["earth"] - z_target, axis=1)
    picked = []
    for i in np.argsort(dist):
        if all(haversine_km(earth.lat[i], earth.lon[i], earth.lat[j], earth.lon[j]) >= min_sep_km for j in picked):
            picked.append(i)
            if len(picked) == top_n:
                break
    return np.array(picked), dist

rows = []
for s in sites.itertuples():
    src = bodies[s.body]
    hit = np.flatnonzero(src.cell_id.values == s.cell_id)
    assert len(hit) == 1, f"{s.name}: cell {s.cell_id} not found in {s.body} table"
    z_t = Z[s.body][hit[0]]
    picked, dist = earth_matches(z_t)
    for rank, i in enumerate(picked, start=1):
        row = {"body": s.body, "site": s.name, "site_cell_id": int(s.cell_id), "rank": rank,
               "earth_cell_id": int(earth.cell_id[i]), "earth_lat": earth.lat[i], "earth_lon": earth.lon[i],
               "site_polar": bool(src.polar.values[hit[0]]), "earth_polar": bool(earth.polar[i]),
               "distance": dist[i], "similarity": float(similarity(dist[i]))}
        for k, f in enumerate(TOPO_FEATURES):
            row[f"site_{f}"] = src[f].values[hit[0]]
            row[f"earth_{f}"] = earth[f][i]
            row[f"dz_{f}"] = Z["earth"][i, k] - z_t[k]      # + = Earth cell is higher on this feature
        rows.append(row)
matches = pd.DataFrame(rows)

print("Best Earth match per site:")
display(matches[matches["rank"] == 1].drop(columns=["rank", "site_cell_id"] + [c for c in matches if c.startswith("dz_")]).round(2))

# %%
for body in ("moon", "mars"):
    d, i = trees["earth"].query(Z[body])
    bodies[body]["earth_match_id"] = earth.cell_id.values[i]
    bodies[body]["earth_match_dist"] = d
    bodies[body]["earth_match_sim"] = similarity(d)
    q = np.percentile(d, [50, 90, 99])
    print(f"{body}: distance to best Earth cell  median {q[0]:.3f} | p90 {q[1]:.3f} | p99 {q[2]:.3f} | "
          f"{(d > 0.5).mean():.1%} of cells have no Earth cell within 0.5")

# %%
for body in ("moon", "mars"):
    d, _ = trees[body].query(Z["earth"], k=K_LIKE)
    earth[f"{body}_dist"] = d.mean(axis=1)
    earth[f"{body}_like"] = similarity(earth[f"{body}_dist"])
    d1, i1 = trees[body].query(Z["earth"])
    earth[f"{body}_match_id"] = bodies[body].cell_id.values[i1]

for body in ("moon", "mars"):
    top = earth.sort_values(f"{body}_like", ascending=False).head(5)
    print(f"\nMost {body}-like Earth cells:")
    display(top[["cell_id", "lat", "lon"] + TOPO_FEATURES + [f"{body}_like"]].round(2))

score_cols = ["moon_like", "mars_like", "moon_match_id", "mars_match_id"]
cells = cells.drop(columns=score_cols, errors="ignore").merge(earth[["cell_id"] + score_cols], on="cell_id", how="left")

# %%
matches.to_parquet(OUT / "site_matches.parquet", index=False)
for body in ("moon", "mars"):
    bodies[body].to_parquet(OUT / f"{body}_cells_matched.parquet", index=False)

dump = dict(separators=(",", ":"), allow_nan=False)

out_sites = []
for (body, site), g in matches.groupby(["body", "site"], sort=False):
    out_sites.append({"body": body, "site": site, "site_cell_id": int(g.site_cell_id.iloc[0]),
                      "site_features": {f: round(float(g[f"site_{f}"].iloc[0]), 3) for f in TOPO_FEATURES},
                      "matches": [{"rank": int(r["rank"]), "cell_id": int(r["earth_cell_id"]),
                                   "lat": round(float(r["earth_lat"]), 2), "lon": round(float(r["earth_lon"]), 2),
                                   "distance": round(float(r["distance"]), 4), "similarity": round(float(r["similarity"]), 4),
                                   "features": {f: round(float(r[f"earth_{f}"]), 3) for f in TOPO_FEATURES},
                                   "dz": {f: round(float(r[f"dz_{f}"]), 3) for f in TOPO_FEATURES}}
                                  for _, r in g.iterrows()]})
with open(FRONT / "site_matches.json", "w") as fh:
    json.dump({"features": TOPO_FEATURES, "scale": {"log_mean": MU.round(5).tolist(), "log_sd": SD.round(5).tolist()},
               "sites": out_sites}, fh, **dump)

with open(FRONT / "earth_analog_scores.json", "w") as fh:
    json.dump({"cell_id": earth.cell_id.tolist(),
               **{f"{b}_like": earth[f"{b}_like"].round(4).tolist() for b in ("moon", "mars")},
               **{f"{b}_match_id": earth[f"{b}_match_id"].tolist() for b in ("moon", "mars")}}, fh, **dump)

for body in ("moon", "mars"):
    df = bodies[body]
    with open(FRONT / f"{body}_earth_match.json", "w") as fh:
        json.dump({"cell_id": df.cell_id.tolist(), "earth_match_id": df.earth_match_id.tolist(),
                   "earth_match_sim": df.earth_match_sim.round(4).tolist()}, fh, **dump)
print("Exported site_matches.json, earth_analog_scores.json, moon_earth_match.json, mars_earth_match.json")

# %% [markdown]
# ## Save master table

# %%
cells.to_parquet(OUT / "cells.parquet", index=False)
print(f"\nSaved {OUT / 'cells.parquet'}")

# %% [markdown]
# ## Frontend export

# %%
FEATURES = ["temp_p", "slope_p90", "rough_p10", "elev_range"]          # add ndvi_p, aridity_p, rough_p, ... as they come

ok = cells[cells.passes_all]
front = {"cell_id": ok.cell_id.tolist(),
         "lat": ok.lat.round(2).tolist(),
         "lon": ok.lon.round(2).tolist()}
for f in FEATURES:
    front[f] = ok[f].round(3).tolist()

with open(FRONT / "cells.json", "w") as fh:
    json.dump(front, fh, separators=(",", ":"))

bad = cells[~cells.passes_all]
with open(FRONT / "excluded.json", "w") as fh:
    json.dump({"cell_id": bad.cell_id.tolist(),
               "excluded_by": bad.excluded_by.tolist()}, fh, separators=(",", ":"))

print(f"Exported cells.json ({len(ok):,} cells) and excluded.json ({len(bad):,} cells)")

# %% [markdown]
# # Visual

# %%
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

NROWS = int(180 / RES)                       # 360

def to_grid(df, values):
    """Put a per-cell value back onto the 360 x 720 grid using cell_id."""
    grid = np.full((NROWS, NCOLS), np.nan)
    rows, cols = np.divmod(df.cell_id.values, NCOLS)
    grid[rows, cols] = values
    return grid

# Category per cell: 0 = passes, 1.. = first filter that rejected it
names = list(FILTERS)
def first_fail(r):
    for i, n in enumerate(names, start=1):
        if not r[f"pass_{n}"]:
            return i
    return 0
cat = cells.apply(first_fail, axis=1).values
grid = to_grid(cells, cat)

colors = ["#2ca25f"] + ["#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5"][:len(names)]
fig, ax = plt.subplots(figsize=(16, 8))
ax.imshow(grid, extent=[-180, 180, -90, 90], cmap=ListedColormap(colors),
          vmin=0, vmax=len(names), interpolation="nearest")
ax.scatter(analogs.lon, analogs.lat, c="red", s=40, edgecolor="k", zorder=3)
for _, a in analogs.iterrows():
    ax.annotate(a["name"], (a.lon, a.lat), xytext=(4, 4), textcoords="offset points", fontsize=8)

legend = [Patch(color=colors[0], label="passes all")] + \
         [Patch(color=colors[i], label=f"rejected: {n}") for i, n in enumerate(names, start=1)]
ax.legend(handles=legend, loc="lower left")
ax.set_title("Cells after screening filters")
ax.set_xlabel("lon"); ax.set_ylabel("lat")
plt.show()

# %%
for _, a in analogs.iterrows():
    cid = cell_id(a.lat, a.lon)
    row = cells[cells.cell_id == cid]
    print(f"{a['name']:<25} slope_p90={row.slope_p90.iloc[0]:>6.1f}  "
          f"rough_p10={row.rough_p10.iloc[0]:>6.1f}  "
          f"pass_slope={row.pass_slope.iloc[0]}  pass_rough={row.pass_rough.iloc[0]}")

# %%
