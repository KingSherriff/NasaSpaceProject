# Analog

NASA Space Apps Challenge 2026, Edmonton.

Before a rover, a suit or a crew goes to the Moon or Mars, it gets tested somewhere on Earth that resembles the destination. Those places are called terrestrial analogs. The well-known ones (Haughton Crater, the Atacama, the lava fields of Hawaii) were found by people who already knew the area. We wanted to search the whole planet instead.

This project divides Earth's land into about 95,000 cells, measures each one with open satellite data, and compares it against the Moon and Mars. The result is a map you can filter by what you want to test and where you want to pretend you are.

## What you can do with it

- Pick a target (Moon, Mars, or both) and an activity (cave exploration, rover testing, spacewalk, craters). The map shows the cells that fit.
- Narrow the result by average temperature and elevation.
- Click a cell to see its scores and how its terrain compares with the closest matching cell on the Moon and on Mars.
- Switch to the Moon or Mars globe, click a landing site such as Apollo 15 or Jezero, and get the ten places on Earth whose terrain is most like it.

## Run the app

Node 18 or newer is required. The data is already in the repository, so no downloads or accounts are needed.

```
cd Visuals_globe
npm install
npm run dev
```

`Visuals_flat` is an earlier version with a flat map only. It starts the same way.

## How it works

### One grid for everything

Every dataset is resampled to the same global grid: 0.5 degrees per cell, 720 columns by 360 rows, about 55 km across at the equator. Each cell has a fixed ID (`row * 720 + col`, row 0 at the north pole), and all layers are joined on that ID. Ocean cells are dropped, which leaves 95,447 land cells.

### Step 1: rule out the obvious

A cell is rejected if it clearly does not look like the Moon or Mars:

| Rule | A cell passes when |
|---|---|
| Forest | forest covers 10% or less |
| Urban | built-up area covers 2% or less |
| Water | water covers 25% or less |
| Slope | the steepest tenth of the cell is at 15 degrees or less |
| Roughness | the smoothest tenth of the cell has a ruggedness index of 15 m or less |

Rejected cells stay in the table with a note saying which rule removed them, so every decision can be checked on the map. Snow and bare ground are never grounds for rejection, because ice sheets and deserts are exactly what we are looking for.

We check the rules against known analog sites: Atacama, the Antarctic Dry Valleys, Haughton Crater, Mauna Kea, Black Point Lava Flow, Rio Tinto and Teide. If one of them is rejected, we treat the rule as wrong.

### Step 2: score each activity

For each activity we ask three questions in order.

1. Is the activity possible here at all? For caves, that means a basaltic volcano within 100 km, since lava tubes form in basalt.
2. Does the cell look more like the Moon or more like Mars? Each body has a target profile (for example: very dry, bare ground, and for Mars also cold). The cell gets a score from 0 to 1 against each profile. If the two scores are within 0.03 of each other, the cell is labelled as suitable for both.
3. How good is it? The higher of the two scores is used to rank cells that share a label.

Scores are computed on percentiles of Earth's land rather than raw values, so temperature, rainfall and bare ground all sit on the same 0 to 1 scale.

### Step 3: compare terrain across three worlds

We cut the elevation models of the Moon, Mars and Earth into blocks of 120 by 120 pixels. On all three models that is about 55 km, so a block on the Moon covers the same ground as a cell on Earth. For each block we compute five numbers:

- typical slope (median)
- steep slope (90th percentile)
- roughness (median terrain ruggedness index)
- relief (90th percentile)
- hypsometric integral, which describes whether the block is mostly high ground with a few low spots or the reverse

Two blocks are similar when these five numbers are close after scaling. From that we get:

- for every Earth cell, a Moon-likeness and a Mars-likeness score, based on its 25 nearest neighbours on that body
- for every Moon and Mars cell, its closest cell on Earth
- for 15 reference sites (Apollo landing sites, the lunar south pole, Jezero, Gale and others), the ten best matches on Earth, kept at least 300 km apart so the list is not ten neighbours of the same valley

The land-cover rules apply to this comparison, but the slope and roughness rules do not. A steep crater rim on the Moon should be allowed to match a steep place on Earth.

## Data

| Dataset | Source | Used for |
|---|---|---|
| MODIS MCD12C1 v061 land cover, 2022 | NASA LP DAAC | forest, urban, water, snow and bare ground per cell |
| GEDI gridded aboveground biomass | NASA ORNL DAAC | vegetation density |
| LOLA lunar elevation model, 64 pixels per degree | NASA GSFC | Moon terrain |
| MOLA Mars elevation mosaic, 463 m | NASA and USGS | Mars terrain |
| ETOPO 2022, 15 arc-seconds | NOAA | Earth terrain |
| WorldClim 2.1 bioclimatic variables | WorldClim | temperature, temperature range, rainfall, land mask |
| Holocene volcano list | Smithsonian Global Volcanism Program | distance to basaltic volcanoes |

MODIS and GEDI need a free NASA Earthdata login to download. The rest are direct downloads.

## What is real and what is a placeholder

We ran out of weekend before every layer was finished. The app marks unfinished layers with a "demo data" badge, and the list below matches what the app shows.

Real:
- the land-cover and terrain rules
- cave exploration scoring
- terrain comparison between Earth, the Moon and Mars, including the reference site matches
- average temperature

Placeholder (generated values, not measurements):
- rover testing, spacewalk and crater scores
- the elevation slider

The export script picks up real columns as soon as the scoring notebook produces them, so replacing a placeholder needs no change to the app.

## Limits

- A cell is about 55 km wide. A good small site can be hidden by its surroundings, for example a lava field next to a forest. This is a tool for narrowing down where to look, not for choosing a campsite.
- The thresholds and weights come from reasoning and from checking known sites. They have not been tuned against the literature.
- Scores are relative to Earth. "Very dry" means dry compared with the rest of Earth's land, which is still far wetter than Mars.
- The volcano list covers the last 12,000 years or so. Older lava tubes are missed.
- Volcano type stands in for rock type, because the volcano list has no rock-type column.
- Biomass data only covers 52°N to 52°S.

## Rebuilding the data

Only needed if you want to change the rules or add a layer. The setup assumes Linux with mamba; see `env_setup.md`.

```
mamba env create -f environment.lock.yml
mamba activate spaceapps
jupyter lab
```

Run the notebooks in this order:

1. `notebooks/Moon Mars topography.ipynb` computes terrain numbers for the Moon and Mars.
2. `notebooks/Cells filtering.ipynb` builds the Earth table, applies the rules and runs the terrain comparison.
3. `notebooks/Scoring.ipynb` scores the activities.

Then export for the app:

```
python scripts/export_frontend.py
cd Visuals_globe
or
cd Visuals_flat
npm run export:compare -- ../data/processed public/data/frontend_cells.json public/data/compare.json
```

The first command writes `public/data/frontend_cells.json` at the repository root and refuses to write a file that breaks the data contract. Copy that file into `Visuals_globe/public/data/` before running the second command.

The first run downloads several gigabytes of elevation data. Later runs skip files that are already on disk.

## Repository layout

```
notebooks/        data pipeline (three notebooks, run in the order above)
scripts/          export and validation scripts
data/processed/   Moon, Mars and reference site tables
public/data/      JSON exports from the pipeline
Visuals_globe/    the app: Earth map plus Moon and Mars globes
Visuals_flat/     earlier flat-map version of the app
docs/             dataset notes and the data contract for the frontend
```

More detail on thresholds, profiles and reasoning is in `docs/DATASETS_AND_PIPELINE.md`.
