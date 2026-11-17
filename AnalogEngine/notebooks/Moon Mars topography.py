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
# # MOON & MARS TOPOGRAPHY

# %% [markdown]
# ## Imports

# %%
import re
import json
from pathlib import Path
from scipy import ndimage
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import rasterio
import requests
import xarray as xr

RAW = Path("../data/raw")
OUT = Path("../data/processed")
FRONT = Path("../public/data")
for d in (RAW / "moon", RAW / "mars", RAW / "etopo", OUT, FRONT):
    d.mkdir(parents=True, exist_ok=True)

POLAR_LAT = 75
PX_PER_CELL = 120                 # 120 px ≈ 55 km on all three DEMs, same as an Earth 0.5° cell
EARTH_R = 6_371_000               # m, mean sphere
ETOPO_KIND = "surface"            # or "bed"; must match the tiles you have on disk
MOON_R = 1_737_400                # m, LOLA reference sphere
MARS_R = 3_396_190                # m, MOLA reference sphere


# %% [markdown]
# ## Data download (skips files already present)

# %%
def download(url, dest):
    dest = Path(dest)
    if dest.exists():
        print(f"✓ already have {dest.name}")
        return dest
    print(f"↓ downloading {dest.name} ...")
    tmp = dest.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.replace(dest)
    return dest

MOON_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_PA/LDEM64_PA_gridline_202405.grd"
moon_path = download(MOON_URL, RAW / "moon" / "LDEM64_PA_gridline_202405.grd")

MARS_URL = "https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
mars_path = download(MARS_URL, RAW / "mars" / "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif")

ETOPO_URL = f"https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_{ETOPO_KIND}_elev_gtif/"
existing_etopo = sorted((RAW / "etopo").glob(f"ETOPO_2022_v1_15s_*_{ETOPO_KIND}.tif"))
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
# ## Open the elevation models

# %%
moon = xr.open_dataset(moon_path)
if moon.lat[0] < moon.lat[-1]:
    moon = moon.isel(lat=slice(None, None, -1))
moon = moon.isel(lon=slice(0, -1))
moon_px = 360 / moon.sizes["lon"]
print(f"Moon: {dict(moon.sizes)} | {moon_px * np.pi * MOON_R / 180:.0f} m/px | "
      f"lat {float(moon.lat[0])}..{float(moon.lat[-1])} | lon {float(moon.lon[0])}..{float(moon.lon[-1])}")

mars = rasterio.open(mars_path)
mars_lat = 90 - 180 / mars.height * (np.arange(mars.height) + 0.5)
print(f"Mars: {{'lat': {mars.height}, 'lon': {mars.width}}} | {mars.transform.a:.0f} m/px | nodata={mars.nodata} | "
      f"lon {np.degrees(mars.bounds.left / MARS_R):.1f}..{np.degrees(mars.bounds.right / MARS_R):.1f}")

def mars_rows(y0, y1):
    dem = mars.read(1, window=rasterio.windows.Window(0, y0, mars.width, y1 - y0)).astype("float64")
    if mars.nodata is not None:
        dem[dem == mars.nodata] = np.nan
    return dem

# Earth: metres above sea level, 12 x 24 tiles stitched on the fly into one pole-to-pole grid
etopo = {}
for p in etopo_paths:
    src = rasterio.open(p)
    etopo[(round((90 - src.bounds.top) / 15), round((src.bounds.left + 180) / 15) % 24)] = src
tile_px = next(iter(etopo.values())).height
assert len(etopo) == 12 * 24 and all(s.height == s.width == tile_px for s in etopo.values())
earth_h, earth_w = 12 * tile_px, 24 * tile_px
earth_lat = 90 - 180 / earth_h * (np.arange(earth_h) + 0.5)
print(f"Earth: {{'lat': {earth_h}, 'lon': {earth_w}}} | {360 / earth_w * np.pi * EARTH_R / 180:.0f} m/px")

def earth_rows(y0, y1):
    out = np.empty((y1 - y0, earth_w))
    for tr in range(y0 // tile_px, (y1 - 1) // tile_px + 1):
        a, b = max(y0, tr * tile_px), min(y1, (tr + 1) * tile_px)
        for tc in range(24):
            src = etopo[(tr, tc)]
            block = src.read(1, window=rasterio.windows.Window(0, a - tr * tile_px, tile_px, b - a)).astype("float64")
            if src.nodata is not None:
                block[block == src.nodata] = np.nan
            out[a - y0:b - y0, tc * tile_px:(tc + 1) * tile_px] = block
    return out

DEMS = {
    "moon": dict(radius_m=MOON_R, n_cols=moon.sizes["lon"], row_lat=moon.lat.values,
                 lon_left=float(moon.lon[0]) - moon_px / 2,
                 read_rows=lambda y0, y1: moon.z.isel(lat=slice(y0, y1)).values.astype("float64") * 1000),
    "mars": dict(radius_m=MARS_R, n_cols=mars.width, row_lat=mars_lat, lon_left=-180.0,
                 read_rows=mars_rows),
    "earth": dict(radius_m=EARTH_R, n_cols=earth_w, row_lat=earth_lat, lon_left=-180.0,
                 read_rows=earth_rows),
}


# %% [markdown]
# ## Slope, ruggedness, elevation stats per ~55 km cell

# %%
### Same method as compute_etopo_features in Cells filtering, on a global lat/lon grid of any body
def compute_terrain_features(read_rows, row_lat, n_cols, lon_left, radius_m, px_per_cell=PX_PER_CELL):
    """Slope (deg), TRI (m), elevation stats per px_per_cell x px_per_cell block.
    Returns one row per cell: cell_id, lat, lon and the same terrain columns as the Earth table.
    """
    px_deg = 360 / n_cols
    dy_m = px_deg * np.pi * radius_m / 180

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

    p90 = lambda a, axis: block_percentile(a, 90, axis)
    p10 = lambda a, axis: block_percentile(a, 10, axis)
    nb_y, nb_x = len(row_lat) // px_per_cell, n_cols // px_per_cell
    blocks = {k: np.full((nb_y, nb_x), np.nan) for k in ("slope_mean", "slope_p50", "slope_p90", "rough_p10", "rough_p50","elev_min", "elev_max", "elev_mean", "elev_p05", "elev_p95")}

    for b in range(nb_y):                                   # one row of cells at a time
        y0, y1 = b * px_per_cell, (b + 1) * px_per_cell
        r0, r1 = max(y0 - 1, 0), min(y1 + 1, len(row_lat))  # 1-row halo so cell edges see their neighbours
        dem = read_rows(r0, r1)

        dx_m = (dy_m * np.cos(np.radians(row_lat[r0:r1])))[:, None]
        dx_m[dx_m < 1] = np.nan                             # the pole itself has no E-W direction

        dem_f = np.where(np.isnan(dem), np.nanmean(dem), dem)
        dem_f = np.pad(dem_f, ((0, 0), (1, 1)), mode="wrap")            # longitude wraps around the globe
        dzdx = ndimage.convolve(dem_f, kx, mode="nearest")[:, 1:-1] / dx_m
        dzdy = ndimage.convolve(dem_f, ky, mode="nearest")[:, 1:-1]
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

        keep = slice(y0 - r0, y0 - r0 + px_per_cell)        # drop the halo rows again
        dem, slope, tri = dem[keep], slope[keep], tri[keep]
        blocks["slope_mean"][b] = block_stat(slope, np.nanmean)
        blocks["slope_p50"][b], blocks["slope_p90"][b] = block_percentiles(slope, [50, 90])
        blocks["rough_p10"][b], blocks["rough_p50"][b] = block_percentiles(tri, [10, 50])
        blocks["elev_min"][b] = block_stat(dem, np.nanmin)
        blocks["elev_max"][b] = block_stat(dem, np.nanmax)
        blocks["elev_mean"][b] = block_stat(dem, np.nanmean)
        blocks["elev_p05"][b], blocks["elev_p95"][b] = block_percentiles(dem, [5, 95])

        blocks["elev_range"] = blocks["elev_max"] - blocks["elev_min"]
        blocks["relief_p90"] = blocks["elev_p95"] - blocks["elev_p05"]       # relief without the extreme pixels
        with np.errstate(all="ignore"):                                      # 0 = plain with peaks, 1 = plateau with pits
            blocks["hyps"] = np.where(blocks["elev_range"] > 0,
                                      (blocks["elev_mean"] - blocks["elev_min"]) / blocks["elev_range"], 0.5)

    cell_deg = px_deg * px_per_cell
    lat = row_lat[:nb_y * px_per_cell].reshape(nb_y, px_per_cell).mean(axis=1)
    lon = (lon_left + cell_deg * (np.arange(nb_x) + 0.5) + 180) % 360 - 180
    lon2d, lat2d = np.meshgrid(lon, lat)
    cells = pd.DataFrame({"cell_id": np.arange(nb_y * nb_x), "lat": lat2d.ravel(), "lon": lon2d.ravel()})
    for name, arr in blocks.items():
        cells[name] = arr.ravel()
    cells["polar"] = cells.lat.abs() > POLAR_LAT          # wedge-shaped cells, lower confidence
    return cells

tables = {}
for body, dem in DEMS.items():
    tables[body] = compute_terrain_features(**dem)
    cell_km = 360 / dem["n_cols"] * PX_PER_CELL * np.pi * dem["radius_m"] / 180 / 1000
    print(f"{body}: {len(tables[body]):,} cells of {cell_km:.1f} km ({360 / dem['n_cols'] * PX_PER_CELL:.4f}°)")

# %%
for body, cells in tables.items():
    print(f"\n{body}:")
    display(cells[["slope_mean", "slope_p90", "rough_p10", "elev_min", "elev_max", "elev_range"]].describe().round(1))


# %% [markdown]
# ## Stable cell ID

# %%
def cell_id(body, lat, lon):
    """cell_id of the cell containing (lat, lon), east-positive longitude, for tables[body]."""
    dem = DEMS[body]
    cell_deg = 360 / dem["n_cols"] * PX_PER_CELL
    ncols = dem["n_cols"] // PX_PER_CELL
    lat = np.asarray(lat); lon = np.asarray(lon)
    row = ((90 - lat) // cell_deg).astype(int)                      # 0 = northernmost row
    col = (((lon - dem["lon_left"]) % 360) // cell_deg).astype(int)
    return row * ncols + col


# %% [markdown]
# ## Reference sites: base candidates and landing sites

# %%
sites = pd.DataFrame([
    ("moon", "Shackleton rim (south pole)", -89.7,  129.8),
    ("moon", "Malapert massif",             -86.0,    2.9),
    ("moon", "Apollo 11, Mare Tranquillitatis", 0.67,  23.47),
    ("moon", "Apollo 15, Hadley Rille",     26.13,    3.63),
    ("moon", "Apollo 17, Taurus-Littrow",   20.19,   30.77),
    ("moon", "Marius Hills pit",            14.09,  -56.77),
    ("moon", "Chang'e 4, Von Karman",      -45.44,  177.60),
    ("mars", "Jezero (Perseverance)",       18.44,   77.45),
    ("mars", "Gale (Curiosity)",            -4.59,  137.44),
    ("mars", "Elysium Planitia (InSight)",   4.50,  135.62),
    ("mars", "Meridiani (Opportunity)",     -1.95,   -5.53),
    ("mars", "Gusev (Spirit)",             -14.57,  175.47),
    ("mars", "Utopia Planitia (Zhurong)",   25.07,  109.93),
    ("mars", "Arcadia Planitia",            39.8,  -158.0),
    ("mars", "Vastitas Borealis (Phoenix)", 68.22, -125.75),
], columns=["body", "name", "lat", "lon"])
sites["cell_id"] = [int(cell_id(s.body, s.lat, s.lon)) for s in sites.itertuples()]

cols = ["cell_id", "slope_mean", "slope_p90", "rough_p10", "elev_min", "elev_max", "elev_range"]
sites = pd.concat([sites[sites.body == body].merge(cells[cols], on="cell_id", how="left")
                   for body, cells in tables.items()], ignore_index=True)
print("\nReference sites:")
display(sites.drop(columns="cell_id").round(1))

# %% [markdown]
# ## Save tables

# %%
for body, cells in tables.items():
    cells.to_parquet(OUT / f"{body}_cells.parquet", index=False)
    print(f"Saved {OUT / f'{body}_cells.parquet'}")
sites.to_parquet(OUT / "planet_sites.parquet", index=False)
print(f"Saved {OUT / 'planet_sites.parquet'}")

# %% [markdown]
# ## Frontend export

# %%
FEATURES = ["slope_p90", "rough_p10", "elev_range"]          # the terrain features cells.json has for Earth

for body, cells in tables.items():
    if body == "earth":
        continue
    front = {"cell_id": cells.cell_id.tolist(),
             "lat": cells.lat.round(2).tolist(),
             "lon": cells.lon.round(2).tolist()}
    for f in FEATURES:
        front[f] = cells[f].round(3).tolist()
    with open(FRONT / f"{body}_cells.json", "w") as fh:
        json.dump(front, fh, separators=(",", ":"), allow_nan=False)
    print(f"Exported {body}_cells.json ({len(cells):,} cells)")

with open(FRONT / "planet_sites.json", "w") as fh:
    json.dump(sites.round(3).to_dict("records"), fh, separators=(",", ":"), allow_nan=False)
print(f"Exported planet_sites.json ({len(sites)} sites)")

# %% [markdown]
# # Visual

# %%
import matplotlib.pyplot as plt

fig, axes = plt.subplots(2, 1, figsize=(16, 16))
for ax, (body, cells) in zip(axes, tables.items()):
    ncols = DEMS[body]["n_cols"] // PX_PER_CELL
    grid = cells.sort_values("cell_id").slope_p90.values.reshape(-1, ncols)
    grid = np.roll(grid, round((DEMS[body]["lon_left"] + 180) / 360 * ncols), axis=1)       # start the map at 180°W
    im = ax.imshow(grid, extent=[-180, 180, -90, 90], cmap="magma", vmin=0, vmax=30, interpolation="nearest")
    s = sites[sites.body == body]
    ax.scatter(s.lon, s.lat, c="cyan", s=40, edgecolor="k", zorder=3)
    for a in s.itertuples():
        ax.annotate(a.name, (a.lon, a.lat), xytext=(4, 4), textcoords="offset points", fontsize=8, color="white")
    fig.colorbar(im, ax=ax, label="slope_p90 (deg)", shrink=0.8)
    ax.set_title(f"{body.capitalize()}: 90th-percentile slope per ~55 km cell")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")
plt.show()
