# NASA Space Apps 2026: Analog

Context for AI assistants working in this repo. Hackathon project (Edmonton, Nov 14–15 2026).

## Challenge
Use open NASA / space-agency data to identify and characterize new terrestrial analogs for Moon and Mars
(deserts, polar regions, volcanic terrain, caves, craters) and present them as a map or tool.

## Product
A global map of Earth on a fixed 0.5° grid. Each land cell is filtered, then scored per **application**
(rover testing, spacewalk/EVA, cave exploration, craters), separately for **Moon** and **Mars**.
Output: labels per cell, e.g. `cave: moon`, plus a quality score for ranking.

## Environment
- Linux (Ubuntu), mamba env `spaceapps` from `environment.yml` (conda-forge; GDAL with HDF4 plugin
  `libgdal-hdf4` for MODIS files).
- Repo root: `~/spaceapps`. Use **absolute paths** built from `ROOT = Path.home() / "spaceapps" / "AnalogEngine"`
  (relative `../data` paths broke once when the notebook's working folder disappeared).
- Layout: `AnalogEngine/` = data pipeline (`notebooks/` as py:percent, `scripts/`, `data/`, `public/data/` exports);
  `AnalogApp/` = the frontend (Vite + React + MapLibre, Globe/Flat projection toggle).
- Raw data: `AnalogEngine/data/raw/<source>/`, processed: `AnalogEngine/data/processed/`. Both git-ignored.
- NASA Earthdata login via `earthaccess.login(persist=True)` (~/.netrc).

## Grid and cell IDs
- 0.5° EPSG:4326, 720 × 360. Cell centers at .25 / .75.
- `cell_id = row * 720 + col`, `row = (90 - lat) // 0.5`, `col = (lon + 180) // 0.5` (row 0 = north).
- Every dataset is regridded to this grid (`coarsen` for exact multiples, `rio.reproject_match` with
  `Resampling.average` otherwise) and joined on `cell_id`.

## Pipeline
1. **Base notebook** → `data/processed/cells.parquet` (one row per land cell; never filtered in place).
   - WorldClim 2.1 10′ bioclim: `temp` (BIO1 annual mean °C), `temp_min` (BIO6), `temp_range` (BIO7),
     `precip` (BIO12); each also as Earth percentile `*_p` (rank pct, 0–1).
   - MODIS MCD12C1 v061 (2022) IGBP percent cover: `water_pct` (class 0), `forest_pct` (1–5),
     `urban_pct` (13), `snow_pct` (15), `barren_pct` (16).
   - GEDI gridded biomass (ORNL DAAC 2339, agbd mean, 12 km): `biomass`, `biomass_p`. Coverage only
     52°N–52°S; NaN elsewhere, gap-filled to 0 where barren+snow > 80%. **Feature only, not a filter.**
   - Screening filter registry `FILTERS` (forest ≤ 10, urban ≤ 2, water ≤ 25). Adds `pass_<name>`,
     `passes_all`, `excluded_by`. Filters add columns; rows are never deleted.
2. **Scoring notebook** (`AnalogEngine/notebooks/Scoring.py`) → `data/processed/cells_scored.parquet`.

## Scoring design
- Two separate questions:
  1. **Suitability** (is the activity physically possible here?) → gate + hard condition → label.
  2. **Body** (Moon vs Mars?) → compare two target profiles; |moon − mars| < 0.03 → `both`.
  3. **Quality** = max(moon, mars), used only for ranking within a label.
- Target profiles use Earth percentiles with weights and a **direction** per feature:
  `max` (only too high is bad, e.g. dryness, cold), `min` (only too low is bad, e.g. proximity,
  bare ground), `eq` (both ways). Score = 1 − weighted RMS of directional differences.
- **Cave exploration (done, v1):** Smithsonian GVP Holocene volcanoes via WFS
  (`webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs`, columns `LatitudeDecimal`,
  `LongitudeDecimal`, `VolcanoType`; no rock-type column). Basaltic proxy = VolcanoType matches
  shield / volcanic field / fissure / lava cone. Gate = pass_forest & pass_urban (water ignored
  underground) & basaltic volcano ≤ 100 km. Cave site = ≤ 50 km. Moon profile: proximity, dryness,
  barren; Mars adds cold (`temp_p` max 0.10).
- Validation sites: Craters of the Moon, Lava Beds, Mauna Loa, Lanzarote, Undara, Raufarhólshellir.

## Next applications (planned)
| Application | Gate | Key data |
|---|---|---|
| Rover testing | barren ≥ 50% | roughness (elevation, teammate), dryness, sand (ASTER GED emissivity 8–9 µm) |
| Spacewalk / EVA | barren ≥ 30% | temp range (Moon), cold (Mars), dryness, elevation (radiation proxy) |
| Craters | exposed impact crater ≤ 50 km | impact-craters.com (Kenkmann 2021), Earth Impact Database |
Humidity: WorldClim `vapr`. Researchers fill the target profile tables (percentile, weight, real
Moon/Mars value, source).

## Conventions
- Each new layer: download step that skips existing files → regrid to 0.5° → column(s) + `*_p`.
- Prefer NASA data where possible (judging criterion) and keep a source URL for every layer.
- Frontend later gets a slim columnar `cells.json` export (arrays per column, same index = same cell),
  not the parquet.
