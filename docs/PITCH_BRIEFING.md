# Pitch briefing: Analog

Everything the team should know before presenting. NASA Space Apps 2026, Edmonton.
Numbers are from the data exported on 2026-11-15. If the notebooks are re-run, re-check them.

Three kinds of statement appear below. Keep them apart when judges ask questions:
- **Checked**: we ran it and saw the result.
- **Assumed**: a reasoned choice we made, not validated against literature.
- **Not checked**: we have not verified it at all.

---

## 1. The problem

Space agencies test rovers, spacesuits and cave robots on Earth, in places that resemble the Moon or Mars ("terrestrial analogs"). In practice a few famous sites do most of the work: Atacama, Mauna Kea, Haughton Crater on Devon Island, Craters of the Moon, Utah (MDRS).

Three gaps:
1. **No global, data-driven search.** Sites are picked by experience and word of mouth. There is no tool to ask "where else on Earth is like Mars for this activity?"
2. **Different activities need different places.** A rover needs drivable, bare terrain. A spacewalk needs open ground and a harsh climate. Cave robots need lava tubes. One list of "Mars-like places" cannot serve all of them.
3. **Moon and Mars are different.** Most lists do not say which body a site is good for.

Challenge wording: use open NASA / space-agency data to identify and characterise new terrestrial analogs (deserts, polar regions, volcanic terrain, caves, craters) and present them as a map or tool.

## 2. Our solution in one paragraph

A world map on a fixed 0.5° grid (about 55 km cells, 95,447 land cells). Each cell is screened, then scored for four activities (rover testing, spacewalk/EVA, craters, cave exploration), separately for the Moon and for Mars. Each cell gets a label per activity (`moon`, `mars`, `both`, or none) and a quality score for ranking. The user picks a target body, one or more activities, and a temperature and elevation range, and the map shows the matching cells.

**It is a screening tool.** It narrows the planet down to regions worth a closer look. It does not select a final site.

## 3. The data and why we use it

| Layer | Source | NASA? | Why we use it |
|---|---|---|---|
| Land cover (forest, urban, water, snow, barren %) | MODIS MCD12C1 v061, year 2022, NASA LP DAAC | Yes | Removes places that are obviously not Moon- or Mars-like, and measures bare ground |
| Earth terrain (slope, roughness, relief, elevation) | ETOPO 2022, 15 arc-second surface, NOAA NCEI | No (NOAA, US agency) | Tells us if ground is drivable or walkable, and gives terrain statistics to compare with other worlds |
| Moon terrain | LOLA elevation model (LDEM64), NASA GSFC | Yes | Real Moon terrain statistics, computed the same way as for Earth |
| Mars terrain | MOLA elevation model (MGS, 463 m mosaic), NASA / USGS | Yes | Real Mars terrain statistics, same method |
| Climate (mean temperature, coldest month, annual range, precipitation) | WorldClim 2.1, 10 arc-minute | No (academic) | Cold and dryness for Mars, temperature swing for the Moon. Also defines which cells are land. |
| Holocene volcanoes | Smithsonian Global Volcanism Program | No | Lava tubes form near basaltic volcanoes, so this locates cave candidates |
| Impact craters | Wikidata (207 structures) | No | Locates crater candidates. Stand-in for the Earth Impact Database, which has no API. |
| Biomass | GEDI gridded biomass, NASA ORNL DAAC | Yes | In the table as a vegetation feature. **Not used in any filter or score.** |

**What to say about NASA data:** the land cover and both planetary elevation models are NASA. Climate, volcanoes and craters are not. Do not claim "all NASA data".

**Key idea worth pitching:** we compute the same terrain statistics on Earth, the Moon and Mars at the same cell size (about 55 km), so "how Moon-like is this terrain" is measured against the real Moon, not guessed. The Moon table has 18,432 cells and the Mars table 73,728.

## 4. How it works

### Step 1: grid
Every dataset is averaged onto the same 0.5° grid and joined by a cell ID.

### Step 2: screening
Cells are flagged, never deleted, so every rejection can be explained.

| Rule | Passes if | Cells left |
|---|---|---|
| start | all land cells | 95,447 |
| forest | forest ≤ 10% | 77,604 |
| urban | built-up ≤ 2% | 75,129 |
| water | water ≤ 25% | 62,626 |
| slope | 90th-percentile slope ≤ 15° | 58,277 |
| roughness | roughness ≤ 15 m | 57,740 |

Each activity chooses which rules apply. Caves ignore water and terrain (a lava tube is underground, lava fields are rough). Craters ignore terrain (rims are steep).

### Step 3: score each activity
Three separate questions per cell:
1. **Is the activity possible here?** A gate plus a hard condition. Only then does the cell get a label.
2. **Moon or Mars?** Two target profiles are scored. If the scores are within 0.03 of each other, the label is `both`.
3. **How good?** Quality = the better of the two scores. Used only for ranking.

A profile is a list of features, each with a target (as a percentile of Earth's land), a weight, and a direction (only too high is bad, only too low is bad, or both).

| Activity | Must have | Moon profile | Mars profile |
|---|---|---|---|
| Rover | land-cover rules, barren ≥ 50%, slope and roughness rules | terrain like the Moon, dry, bare | terrain like Mars, very dry, bare, cool |
| Spacewalk | land-cover rules, barren ≥ 30%, slope rule | large temperature range, dry, bare, high | very dry, high, cool, bare, some temperature range |
| Craters | land-cover rules, impact crater ≤ 50 km | near crater, dry, bare | near crater, very dry, cool, bare |
| Cave | forest and urban rules, basaltic volcano ≤ 50 km | near volcano, dry, bare | same plus cold |

### Results (cells with a label)

| Activity | Moon | Mars | Both | Total |
|---|---|---|---|---|
| Rover | 3,847 | 2,315 | 627 | 6,789 |
| Spacewalk | 2,206 | 3,253 | 1,932 | 7,391 |
| Craters | 92 | 87 | 216 | 395 |
| Cave | 330 | 58 | 197 | 585 |

Exactly one cell is a site for all four activities: 23.75°S, 68.25°W in the Atacama. It is Mars for spacewalk and Moon for the other three.

## 5. What is checked

- **The pipeline runs end to end** on real data. No layer in the frontend file is mocked any more.
- **The frontend data file passes an automatic consistency check** before every export (array lengths, cell IDs match coordinates, labels agree with scores, scores are 0 on non-sites).
- **Known analog sites: 15 of 18 get a label for their own activity.**
  - Caves: Craters of the Moon, Lava Beds, Lanzarote, Undara, Raufarhólshellir pass. Mauna Loa fails.
  - Rover: Atacama, Negev (Ramon), Erfoud pass. MDRS Utah fails.
  - Spacewalk: Black Point Lava Flow and Qaidam Basin pass. Mauna Kea fails.
  - Craters: Meteor Crater, Haughton, Gosses Bluff, Roter Kamm, Wolfe Creek all pass.
- **Why the three fail:** Mauna Loa and Mauna Kea share one cell that is rejected for forest (the cell averages the whole side of the island). MDRS Utah's cell is only 36% barren, below the 50% rover gate. All three are effects of the 55 km cell size.
- **The map filter logic** was tested against the data (for example, "Moon" and "Moon + Both" return the same cells).

## 6. What is assumed

Say these openly. They are the honest weak points.

- **All thresholds are our choices**: forest 10%, urban 2%, water 25%, slope 15°, barren 50% and 30%, crater and volcano distances of 50 and 100 km. They were picked by reasoning and by checking that known sites survive, not from papers.
- **All profile targets and weights are our choices.** The Mars profiles were retuned once by trying four variants against about 17 known sites, so they are partly fitted to those sites.
- **"Mars-like" means dry and cool relative to Earth, "Moon-like" means large temperature range.** Scores are percentiles of Earth's land, not physical Moon or Mars values. Nowhere on Earth is actually as cold or dry as Mars.
- **Temperature range is the annual range** (WorldClim BIO7), used as a stand-in for the Moon's day-night swings.
- **Elevation is a stand-in** for thin air and radiation.
- **Basaltic volcanoes are identified by volcano type** (shield, volcanic field, fissure, lava cone, lava field, pyroclastic cone), because the source has no rock-type column. Only volcanoes active in the Holocene are included, so older lava fields are missed.
- **"Bare ground" comes from the MODIS barren class**, which does not include snow and ice. Antarctica and the ice sheets therefore get no rover or spacewalk label.
- **Terrain similarity** compares five statistics (median and 90th-percentile slope, roughness, relief, hypsometry) per 55 km cell. It says nothing about rocks, dust or soil.

## 7. What is not checked

- **Licences.** We believe the NASA and NOAA data are open, WorldClim is free for non-commercial use, and Wikidata is CC0, but nobody has read the current terms pages. Check before publishing anything.
- **Literature.** No threshold or weight has been confirmed against a paper.
- **Crater list quality.** Wikidata includes some unconfirmed structures (for example Shiva) and does not say if a crater is exposed or buried.
- **The Haughton label after the Mars retune.** In a test run it stayed Moon for all surface activities, although it is known as a Mars analog. Not re-checked in the final output.
- **Sand.** The planned ASTER emissivity layer for rover terrain is not in.
- **The map on other machines.** A fix for the cell overlay sometimes not redrawing was made in the flat map and tested in a headless browser, but not confirmed on the presentation laptop. The 3D globe version was not touched.

## 8. Known oddities a judge might spot

- **The Atacama is Moon for rovers.** Its terrain statistics match the Moon better (88th percentile) than Mars (73rd). It is Mars for spacewalks.
- **The central Sahara is Mars for spacewalks.** Dryness outweighs heat in the Mars profile.
- **Hawaii's volcano sites are missing.** One forest-covered cell hides them.
- **Selecting all four activities leaves one cell**, and it disappears when a single target is chosen, because its labels are mixed. This is the filter working as designed: the target must match for every selected activity.
- **Elevation is clipped at −430 m.** Coastal cells average in sea floor, so the raw values went far below sea level.

## 9. Likely questions and short answers

- **"Is this validated?"** Against 18 known analog sites, 15 are found. The scoring weights are prototype assumptions.
- **"Why 55 km cells?"** It makes a global search fast and lets us compare Earth, Moon and Mars on the same scale. The next step is finer resolution inside the best regions.
- **"What is new here?"** Per-activity and per-body labels on one global grid, and terrain compared against real Moon and Mars elevation data with one method.
- **"Is it all NASA data?"** No. Land cover and both planetary elevation models are NASA. Climate, volcanoes and craters come from other open sources.
- **"Who would use it?"** Mission planners and analog-research teams looking for candidate regions beyond the usual sites.
- **"What would you do with more time?"** Real Moon and Mars values in the profiles, literature-backed thresholds, sand and rock-type layers, a confirmed crater database, finer resolution, and a snow/ice path for polar analogs.

## 10. 30-second version

> Space agencies test rovers, spacesuits and cave robots on Earth, but they keep returning to the same few famous sites. We built a global map that scores every 55 km piece of Earth's land as an analog for the Moon, Mars or both, for four mission activities. We measure terrain the same way on Earth, the Moon and Mars using NASA elevation data, and combine it with land cover and climate. Pick a target and an activity, and the map shows where on Earth to look. It finds 15 of 18 known analog sites, and thousands of candidates nobody has listed.

Note on the last sentence: "thousands of candidates" is the count of labelled cells. We have not checked how many are genuinely new or practical to reach, so say "candidates", not "new analog sites".
