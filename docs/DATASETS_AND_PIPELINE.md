# Datasets and Pipeline Overview

Analog, NASA Space Apps 2026 (Edmonton). This is a **prototype built in a short hackathon window**.
Parameter choices below are informed assumptions, not fully literature-validated values. Where a choice is a judgement call, we say so.

---

## 1. Datasets used

| # | Dataset | Provider | Used for | Columns produced | Access |
|---|---|---|---|---|---|
| 1 | **MODIS MCD12C1 v061** (Land Cover Type 1, IGBP, percent per class, year 2022, 0.05°) | NASA LP DAAC | Screening filters, barren ground | `water_pct`, `forest_pct`, `urban_pct`, `snow_pct`, `barren_pct` | NASA Earthdata login (`earthaccess`) |
| 2 | **GEDI gridded aboveground biomass density** (agbd mean, 12 km, 2019-04-17 to 2023-03-16) | NASA ORNL DAAC (collection 2339, concept `C3043630107-ORNL_CLOUD`) | Vegetation/biomass feature (not a filter) | `biomass`, `biomass_p` | NASA Earthdata login (`earthaccess`) |
| 3 | **WorldClim 2.1 bioclim, 10 arc-min** (BIO1, BIO6, BIO7, BIO12) | UC Davis / WorldClim (not NASA) | Climate: base land mask, temperature, dryness | `temp`, `temp_min`, `temp_range`, `precip` (+ `*_p` percentiles) | Direct download, `geodata.ucdavis.edu` |
| 4 | **Smithsonian GVP, Holocene Volcanoes** (Volcanoes of the World, WFS) | Smithsonian Global Volcanism Program (not NASA) | Cave exploration: distance to basaltic volcanoes | `dist_basalt_volc_km`, `volc_prox` | Public WFS, `webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs` |

Planned but **not yet used** (see `CLAUDE.md`): ASTER GED emissivity (sand), elevation/roughness (teammate), WorldClim `vapr`, impact-crater databases.

### Source URLs
- MODIS MCD12C1: https://lpdaac.usgs.gov/products/mcd12c1v061/
- GEDI gridded biomass (ORNL DAAC): https://daac.ornl.gov/ (search the GEDI gridded biomass collection, DOI listed on the dataset landing page)
- WorldClim 2.1: https://www.worldclim.org/data/worldclim21.html (file: `wc2.1_10m_bio.zip`)
- Smithsonian GVP: https://volcano.si.edu/

### Licences and citation (to verify before submission)
Quick check from what we know. **Please confirm the exact wording on each landing page** before we put it in the final submission.

| Dataset | Licence / terms | Notes |
|---|---|---|
| MODIS MCD12C1 | NASA Earth science data policy: free and open, no restrictions on use | Cite as per the LP DAAC product page (Friedl & Sulla-Menashe) |
| GEDI gridded biomass (ORNL DAAC) | NASA Earth science data policy: free and open | Cite the dataset DOI and the ORNL DAAC. Mean agbd only. |
| WorldClim 2.1 | Free to use. **Not NASA**, so we need to check whether the current terms are CC BY 4.0 or "academic/non-commercial". Fine for a hackathon prototype either way. | Cite Fick & Hijmans (2017), *Int. J. Climatology* |
| Smithsonian GVP | **Not NASA.** Public web service, free to use with attribution. Check the GVP terms of use. | Cite as "Global Volcanism Program, Smithsonian Institution" |

Two of four layers are not NASA. That is acceptable for the challenge, but because NASA data is a judging criterion we should be explicit about which layers are NASA in the pitch, and swap in NASA/other agency alternatives later where possible.

---

## 2. Pipeline

```
raw data  ->  regrid to 0.5° grid  ->  cells.parquet (+ filter flags)  ->  scoring  ->  cells_scored.parquet  ->  frontend JSON
```

### 2.1 Grid
- Fixed global grid, 0.5° in EPSG:4326, 720 x 360 cells. Centres at .25 and .75.
- `cell_id = row * 720 + col`, where `row = (90 - lat) // 0.5` (row 0 is north) and `col = (lon + 180) // 0.5`.
- WorldClim BIO1 (temperature) defines the **land mask**. A cell with no temperature value is ocean and is dropped from the table.
- Every layer is regridded onto this grid, then joined on `cell_id`:
  - Exact multiples use `coarsen` and mean. WorldClim 10′ to 0.5° is 3x3. MODIS 0.05° to 0.5° is 10x10.
  - Otherwise `reproject_match` with `Resampling.average`. GEDI 12 km uses this.
- Climate variables also get an **Earth percentile** (`*_p`, rank percentile 0–1 across all land cells). Scoring uses percentiles, so every feature lives on the same scale.

### 2.2 Master table: `data/processed/cells.parquet`
One row per land cell. **Filters add columns and never delete rows**, so every decision can be inspected and mapped.

Columns: `cell_id, lat, lon`, climate (`temp`, `temp_min`, `temp_range`, `precip` and `*_p`), land cover (`*_pct`), biomass (`biomass`, `biomass_p`), then filter output (`pass_<name>`, `passes_all`, `excluded_by`).

Note on biomass: GEDI only covers 52°N to 52°S. Outside that band the value is NaN, except cells with `barren + snow > 80%`, which are set to 0 (a bare rock or ice cell has no biomass, so this is a safe fill). Biomass is **a feature only, not a filter**, because of this coverage gap.

---

## 3. Screening filters

The screening step answers: **"Is this cell obviously unlike a lunar or Martian surface, so that it should never be offered as an analog?"** It is deliberately coarse. It removes the clear mismatches and leaves detailed ranking to scoring.

Implemented as a registry (`FILTERS`) in `AnalogEngine/notebooks/Cells filtering.py`. Each rule is a function returning True when the cell **passes**. Missing values count as 0%, so a cell is not rejected just for lacking data.

| Filter | Passes if | Rejects | Why this threshold (assumption) |
|---|---|---|---|
| `forest` | `forest_pct <= 10` | Cells where more than 10% is forest (IGBP classes 1–5: evergreen/deciduous needleleaf and broadleaf, mixed forest) | Moon and Mars have no vegetation. Dense canopy hides the terrain and changes the thermal and radar signature. We allow up to 10% so a cell with a few trees on a mostly barren volcanic field, or a forest patch at a cell edge, is not thrown out. |
| `urban` | `urban_pct <= 2` | Cells with more than 2% built-up area (IGBP class 13) | Analog fieldwork needs undisturbed ground. The threshold is strict because even a small settlement means roads, infrastructure and people. 2% still tolerates MODIS's coarse pixel noise. |
| `water` | `water_pct <= 25` | Cells where more than 25% is water (IGBP class 0) | Coastlines and lakes are not analog terrain. We are looser here than for forest, because a coastal cell with a lot of land is still usable, and the grid is coarse (about 55 km). |

**Deliberately not filters**
- `snow_pct` and `barren_pct`: info only at this stage. Polar ice and deserts are valid analogs, so we must not exclude them. Application gates use barren later (e.g. rover needs `barren >= 50%`).
- `biomass`: coverage gap (see above).
- Caves ignore the `water` filter in their own gate (see 4.2), because ocean next to a lava tube does not matter underground. This is why island sites like Lanzarote survive.

**Output per cell**: `pass_forest`, `pass_urban`, `pass_water`, `passes_all`, and `excluded_by` (a comma-separated list of the filters that rejected it, for tooltips and pitch funnel).

**Funnel and sanity check.** The notebook prints how many cells remain after each filter, and checks that known analogs survive: Atacama, Antarctic Dry Valleys, Haughton Crater, Mauna Kea, Black Point Lava Flow, Rio Tinto, Teide. If a known analog gets rejected, we treat that as a bug in the thresholds.

**Caveats**
- 0.5° cells are about 55 km wide. Percent cover is an average over that area, so a good small site can be hidden by its surroundings (e.g. a lava field next to a forest).
- MODIS land cover is a single year (2022). Good enough for a global screening.
- Thresholds are initial guesses chosen to behave sensibly on the sanity-check sites. They have not been tuned or validated against papers yet.

---

## 4. Scoring (applications)

Implemented in `AnalogEngine/notebooks/Scoring.py`. Output: `data/processed/cells_scored.parquet`. The base table is never modified.

### 4.1 Three separate questions
1. **Suitability.** Is the activity physically possible here? A gate plus a hard condition decides if the cell gets a label at all.
2. **Body.** Moon or Mars? Two target profiles are scored. If `|moon - mars| < 0.03` the label is `both`.
3. **Quality.** `max(moon, mars)`. Used only to rank cells within a label, never to decide the label.

### 4.2 Score function
Each profile has a target value per feature (on an Earth percentile or 0–1 scale), a weight, and a direction:
- `max`: only too high is penalised (e.g. precipitation, cold)
- `min`: only too low is penalised (e.g. volcano proximity, barren ground)
- `eq`: penalised both ways

`score = 1 - weighted RMS of directional differences`. Cells outside the gate score 0. Missing features are skipped in the weighted average.

### 4.3 Cave exploration (v1, done)
- **Basaltic volcano proxy.** GVP has no rock-type column, so `VolcanoType` is matched against: shield, volcanic field, fissure, lava cone, lava field, pyroclastic cone. Reason: lava tubes form in fluid basaltic lava, and these types are mostly effusive basalt, while stratovolcanoes, calderas and domes are mostly andesitic or explosive.
- **Gate.** Passes forest and urban filters, water ignored, and a basaltic volcano within **100 km**.
- **Cave site.** Gate passed and basaltic volcano within **50 km** of the cell centre. Chosen so that the volcano is in or next to the 55 km cell.
- **Volcano proximity feature.** `volc_prox` = 1 within 25 km, falling linearly to 0 at 100 km.

| Feature | Moon target (weight, direction) | Mars target (weight, direction) |
|---|---|---|
| `volc_prox` | 1.0 (3, min) | 1.0 (3, min) |
| `precip_p` (dryness) | 0.20 (1, max) | 0.20 (1, max) |
| `barren` (barren fraction) | 1.0 (0.5, min) | 1.0 (0.5, min) |
| `temp_p` (cold) | not used | 0.10 (2, max) |

Reasoning (assumptions): proximity to basalt matters most, so it has the highest weight. Both bodies are very dry, so we want low precipitation. Both have bare surfaces, with a low weight because barren percent from MODIS is only a rough proxy at this scale. Mars is much colder than the Moon's equatorial regions on average, so a cold climate (low temperature percentile) is added for Mars.

**Validation sites**: Craters of the Moon (Idaho), Lava Beds (California), Mauna Loa / HI-SEAS (Hawaii), Cueva de los Verdes (Lanzarote), Undara (Australia), Raufarhólshellir (Iceland). The notebook prints each site's scores and, if rejected, which filter did it.

### 4.4 Planned
| Application | Gate | Key data |
|---|---|---|
| Rover testing | barren >= 50% | roughness (elevation), dryness, sand (ASTER GED) |
| Spacewalk / EVA | barren >= 30% | temperature range (Moon), cold (Mars), dryness, elevation |
| Craters | exposed impact crater within 50 km | impact-craters.com (Kenkmann 2021), Earth Impact Database |

Researchers fill in the target profile tables (percentile, weight, real Moon/Mars value, source).

---

## 5. Known limitations
- Prototype thresholds were chosen from reasoning and spot-checks on known sites, not from a systematic literature review.
- 0.5° resolution (about 55 km) is coarse. This is a screening tool, not a site-selection tool.
- Earth percentiles are relative to Earth's land, not absolute Moon/Mars values. The profile tables should later be backed with real Moon/Mars numbers and sources.
- Volcano type is only a proxy for basalt. Lava tubes can also exist outside the Holocene volcano list (older flows), which we miss.
- Two of four input layers (WorldClim, GVP) are not NASA data.
