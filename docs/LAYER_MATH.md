# Layer Math

Analog, NASA Space Apps 2026 (Edmonton). This page has the formula behind every layer we compute now,
with a short note on why we chose it. Code references point to the current implementation:
the `AnalogEngine/analog_engine/` package (`base_table.py`, `terrain.py`, `filters.py`, `planets.py`,
`likeness.py`, `scoring/`).

Equations use GitHub's verbatim math syntax (inline `` $`…`$ ``, display ` ```math ` blocks), so Markdown
does not eat backslashes such as `\\`, `\,` or `\_`.

---

## 0. Notation

| Symbol | Meaning |
|---|---|
| $`\varphi, \lambda`$ | latitude, longitude (degrees) |
| $`c`$ | one 0.5° grid cell |
| $`P(c)`$ | set of native raster pixels whose centres fall inside cell $`c`$ |
| $`N`$ | number of land cells in the table |
| $`x_c`$ | value of a feature in cell $`c`$ |
| $`R_\oplus`$ | Earth radius, 6371 km |

---

## 1. Grid and cell ID

**Math.** Global EPSG:4326 grid with cell size $`\Delta = 0.5°`$, so $`720 \times 360`$ cells.

```math
\text{row} = \left\lfloor \frac{90 - \varphi}{\Delta} \right\rfloor,\qquad
\text{col} = \left\lfloor \frac{\lambda + 180}{\Delta} \right\rfloor,\qquad
\mathrm{cell\_id} = 720\cdot\text{row} + \text{col}
```

Cell centres are at $`\varphi_r = 90 - \Delta(r + \tfrac12)`$ and $`\lambda_k = -180 + \Delta(k + \tfrac12)`$.

**Why.** One integer key lets every dataset join on `cell_id` without spatial joins. Row 0 is north, so
`cell_id` is the row-major index of the image, and the frontend can put values back on the map with
`divmod(cell_id, 720)`. 0.5° (about 55 km at the equator) is coarse enough to cover the whole planet in a
browser and fine enough to separate distinct terrains.

---

## 2. Regridding to the 0.5° grid

**Math.** Every raster becomes a cell mean of its valid pixels.

If the native resolution divides 0.5° exactly and the raster edges sit on cell edges (WorldClim 10′ → factor
3, MODIS 0.05° → factor 10), we block average (`coarsen`):

```math
x_c = \frac{1}{|P(c)|}\sum_{p \in P(c)} x_p
```

Otherwise (GEDI 12 km, other projections) we use `rio.reproject_match` with `Resampling.average`, which is
the area-weighted mean of the overlapping source pixels:

```math
x_c = \frac{\sum_{p} A(p \cap c)\, x_p}{\sum_{p} A(p \cap c)}
```

Several bands summed into one column (for example forest = 5 IGBP classes) are regridded one by one and
then added. A NaN in any band gives NaN.

**Why.** A mean keeps the physical unit (°C, mm, %, Mg/ha) and does not depend on which pixel happens to
sit in the cell centre. `coarsen` is exact and fast when the grids line up. `reproject_match` handles
everything else with the same averaging meaning.

---

## 3. Land mask

**Math.** A cell exists in the table when its WorldClim BIO1 value is defined:

```math
\mathcal{L} = \{\, c : \text{temp}_c \neq \text{NaN} \,\}
```

Rows are never dropped after this step. Filters only add columns.

**Why.** WorldClim is defined on land only, so it is a free and consistent land/ocean mask on the same
grid as our climate features. Keeping every land row means any decision (filter, gate, label) can be
mapped and explained afterwards.

---

## 4. Earth percentiles (`*_p`)

**Math.** For a feature $`x`$, the percentile of cell $`c`$ over the land cells with a value is its
average rank divided by the number of valid cells (pandas `rank(pct=True)`, ties share the mean rank):

```math
x^{p}_c = \frac{\mathrm{rank}(x_c)}{N_{\text{valid}}} \in (0, 1]
```

NaN stays NaN.

**Why.** Temperature (°C), precipitation (mm) and elevation (m) have different units and very skewed
distributions. On percentiles every feature lives on the same 0–1 scale, so the weighted distance in the
scoring (Section 12) is fair between features, and targets read naturally ("driest 10 % of Earth's land"
is `precip_p = 0.10`). Percentiles also resist outliers.

---

## 5. Climate: WorldClim 2.1 bioclim (10′)

**Math.** Direct cell means (Section 2) of four bioclim variables, each with a percentile:

| Column | Source | Definition |
|---|---|---|
| `temp` | BIO1 | annual mean temperature, °C |
| `temp_min` | BIO6 | minimum temperature of the coldest month, °C |
| `temp_range` | BIO7 | annual temperature range, $`\text{BIO5} - \text{BIO6}`$, °C |
| `precip` | BIO12 | annual precipitation, mm |

**Why.**
- `temp`: cold is the main climate match for Mars (mean surface about −60 °C).
- `temp_range`: the Moon has huge day/night swings (about −170 to +120 °C). The annual range is the best
  global proxy for thermal stress we have on Earth.
- `precip`: dryness is the strongest single analog property for both bodies (no liquid water, little
  weathering, no vegetation). Hyperarid deserts like Atacama score well through it.
- `temp_min`: kept as a feature for later profiles.

WorldClim is not NASA data. It is used because it is a standard, gap-free climatology at a resolution that
divides 0.5° exactly.

---

## 6. Land cover: MODIS MCD12C1 v061 (2022, 0.05°)

**Math.** The product gives the percent of each IGBP class per 0.05° pixel. Band $`b`$ holds class $`b-1`$.
Fill value 255 is masked. Each column is the cell mean of the class percent, summed over its classes:

```math
\mathrm{forest\_pct}_c = \sum_{k=1}^{5} \overline{\text{pct}_k}(c),\qquad
\mathrm{water\_pct}_c = \overline{\text{pct}_0}(c),\quad
\mathrm{urban\_pct}_c = \overline{\text{pct}_{13}}(c),\quad
\mathrm{snow\_pct}_c = \overline{\text{pct}_{15}}(c),\quad
\mathrm{barren\_pct}_c = \overline{\text{pct}_{16}}(c)
```

Classes 1–5 are the five IGBP forest types (evergreen/deciduous needleleaf/broadleaf, mixed).
For scoring we use the fraction:

```math
\text{barren}_c = \frac{\mathrm{barren\_pct}_c}{100}\quad(\text{NaN} \to 0)
```

**Why.** NASA product, global, and already a percent per class, so averaging to 0.5° keeps an exact
"share of the cell" meaning. Forest, cities and open water rule out any Moon/Mars analog. Barren share is
the direct measure of "bare rock and regolith" that every application wants.

---

## 7. Vegetation: GEDI gridded biomass (ORNL DAAC 2339, 12 km)

**Math.** Area-weighted mean of the `agbd` mean band (Mg/ha) onto the grid (Section 2), then a gap fill
outside GEDI coverage (52° N – 52° S):

```math
\text{biomass}_c =
\begin{cases}
0 & \text{if biomass}_c = \text{NaN and } \mathrm{barren\_pct}_c + \mathrm{snow\_pct}_c > 80 \\
\text{biomass}_c & \text{otherwise}
\end{cases}
```

plus `biomass_p` (Section 4).

**Why.** NASA lidar biomass is a strong independent check on "is this place alive". It is a feature only,
not a filter, because it is missing north of 52° and south of 52°, where many polar analogs are. A bare
rock or ice cell has no biomass, so setting those to 0 is a safe fill. Other high-latitude cells stay NaN.

---

## 8. Terrain: ETOPO 2022 (15″, NOAA)

Computed per 15° tile on native pixels, then summarised per 0.5° cell. At 15″ a cell holds
$`120 \times 120`$ pixels.

### 8.1 Pixel spacing

```math
\Delta y = \Delta\varphi_{\text{px}} \cdot 110\,574\ \text{m},\qquad
\Delta x(\varphi) = \Delta\lambda_{\text{px}} \cdot 111\,320 \cdot \cos\varphi\ \text{m}
```

### 8.2 Slope (Sobel / Horn gradient)

With elevation $`z`$ on the $`3\times3`$ neighbourhood

```math
\frac{\partial z}{\partial x} = \frac{1}{8\,\Delta x}
\begin{bmatrix}-1 & 0 & 1\\-2 & 0 & 2\\-1 & 0 & 1\end{bmatrix} * z,\qquad
\frac{\partial z}{\partial y} = \frac{1}{8\,\Delta y}
\begin{bmatrix}1 & 2 & 1\\0 & 0 & 0\\-1 & -2 & -1\end{bmatrix} * z
```

```math
\text{slope} = \frac{180}{\pi}\arctan\sqrt{\left(\frac{\partial z}{\partial x}\right)^2 + \left(\frac{\partial z}{\partial y}\right)^2}\quad[\text{deg}]
```

NaN pixels are filled with the strip mean for the convolution only and set back to NaN afterwards.

### 8.3 Roughness (TRI)

Terrain Ruggedness Index as the mean absolute height difference to the 8 neighbours $`\mathcal{N}_8`$
(valid neighbours only):

```math
\text{TRI} = \frac{1}{|\mathcal{N}_8|}\sum_{q \in \mathcal{N}_8} |z - z_q|\quad[\text{m}]
```

(Riley et al. 1999 use the root of the sum of squares. The mean absolute version is in metres per step and
easier to read as a threshold.)

### 8.4 Cell statistics

For each cell, over its pixels $`P(c)`$, with $`Q_q`$ the $`q`$-th percentile (linear interpolation, NaN ignored):

| Column | Formula |
|---|---|
| `slope_mean`, `slope_p50`, `slope_p90` | $`\overline{\text{slope}},\ Q_{50}(\text{slope}),\ Q_{90}(\text{slope})`$ |
| `rough_p10`, `rough_p50` | $`Q_{10}(\text{TRI}),\ Q_{50}(\text{TRI})`$ |
| `elev_min`, `elev_max`, `elev_mean` | $`\min z,\ \max z,\ \bar z`$ |
| `elev_p05`, `elev_p95` | $`Q_{5}(z),\ Q_{95}(z)`$ |
| `elev_range` | $`\max z - \min z`$ |
| `relief_p90` | $`Q_{95}(z) - Q_{5}(z)`$ |
| `hyps` | $`\dfrac{\bar z - \min z}{\max z - \min z}`$ (0.5 if flat) |
| `elevation` | $`\max(\bar z,\ -430\ \text{m})`$, plus `elev_p` |

**Why.**
- A rover or a suited astronaut fails on the steep and rough part of a cell, not on its average, so the
  filters use upper slope (`slope_p90`) and the *smoothest* part of the roughness distribution
  (`rough_p10`: "is there at least some drivable ground").
- `relief_p90` is relief without the single highest and lowest pixels, so one cliff or pit does not
  dominate.
- `hyps` (hypsometric integral) tells plains with isolated peaks (near 0) from plateaus cut by pits and
  craters (near 1). It is the one feature that captures the *shape* of cratered terrain.
- `elevation` is clipped at the Dead Sea shore (about −430 m) because coastal cells average in sea floor.
  High elevation is a proxy for thin air and higher radiation in the spacewalk profiles.
- ETOPO is not NASA but includes NASA SRTM. Its 15″ resolution resolves slopes that 0.5° data cannot.

---

## 9. Polar flag

```math
\text{polar}_c = \left[\,|\varphi_c| > 75°\,\right]
```

**Why.** Near the poles the lat/lon cells become thin wedges (east–west size scales with $`\cos\varphi`$), so
terrain statistics there are less comparable. The flag marks lower confidence instead of removing cells.

---

## 10. Screening filters

**Math.** Each filter is a boolean column; missing values count as 0 (pass):

| Filter | Rule |
|---|---|
| `pass_forest` | $`\mathrm{forest\_pct} \le 10`$ |
| `pass_urban` | $`\mathrm{urban\_pct} \le 2`$ |
| `pass_water` | $`\mathrm{water\_pct} \le 25`$ |
| `pass_slope` | $`\mathrm{slope\_p90} \le 15°`$ |
| `pass_rough` | $`\mathrm{rough\_p10} \le 15\ \text{m}`$ |

```math
\mathrm{passes\_all}_c = \bigwedge_{f}\ \text{pass}_f(c)
```

`excluded_by` lists the filters a cell fails.

**Why.** These remove places that are physically unlike the Moon or Mars (forest, city, lake) or
unusable for surface tests (too steep or too rough). Thresholds are judgement calls for a hackathon
prototype. Applications pick the filters that make sense for them (caves ignore water and terrain, see
Section 13).

---

## 11. Distance and proximity to point features

Used for basaltic volcanoes (caves) and impact structures (craters).

### 11.1 Great-circle distance to the nearest point

In `analog_engine/layers/points.py` (`nearest_km`, used for both point sources) points go to unit vectors
and a KD-tree finds the nearest chord length $`\ell`$:

```math
\mathbf{u}(\varphi,\lambda) = (\cos\varphi\cos\lambda,\ \cos\varphi\sin\lambda,\ \sin\varphi),\qquad
d = 2R_\oplus \arcsin\!\left(\tfrac{\ell}{2}\right)
```

This equals the haversine distance (used in `likeness.py` to space out site matches):

```math
d = 2R_\oplus \arcsin\sqrt{\sin^2\tfrac{\Delta\varphi}{2} + \cos\varphi_1\cos\varphi_2\sin^2\tfrac{\Delta\lambda}{2}}
```

### 11.2 Proximity ramp

```math
\text{prox} = \mathrm{clip}\!\left(1 - \frac{d - d_{\text{full}}}{d_{\text{zero}} - d_{\text{full}}},\ 0,\ 1\right),
\qquad d_{\text{full}} = 25\ \text{km},\ d_{\text{zero}} = 100\ \text{km}
```

So proximity is 1 up to 25 km (the feature is about inside the cell, half-diagonal ≈ 39 km), then falls
linearly to 0 at 100 km.

### 11.3 Point sources

- **Basaltic volcanoes** (`dist_basalt_volc_km`, `volc_prox`): Smithsonian GVP Holocene volcanoes whose
  `VolcanoType` matches `shield | volcanic field | fissure | lava cone | lava field | pyroclastic cone`.
- **Impact structures** (`dist_crater_km`, `crater_prox`): Wikidata items that are instances of "impact
  crater" (Q55818) with Earth coordinates.

**Why.** Lava tubes form in low-viscosity basaltic lava, and the GVP data has no rock-type column, so
volcano type is our basalt proxy (shields and fields are effusive; stratovolcanoes and domes are mostly
explosive and andesitic). A ramp instead of a hard cut means "next to a volcano" and "at a volcano" both
score high, while distance still ranks the cells. Wikidata stands in for the Earth Impact Database, which
has no API.

---

## 12. Moon / Mars terrain likeness

Built from the same terrain statistics on three DEMs: ETOPO 2022 (Earth), LOLA LDEM64 (Moon, NASA GSFC)
and MOLA 463 m (Mars, NASA/USGS). Each uses blocks of 120 × 120 pixels, which is about 55 km on all three
bodies, so cells are comparable in size. Slope and TRI follow Section 8 with the body's radius:

```math
\Delta y = \Delta\varphi_{\text{px}} \cdot \frac{\pi R_{\text{body}}}{180},\qquad
\Delta x = \Delta y \cos\varphi
```

### 12.1 Feature vector

```math
\mathbf{f} = \big(\log(1+\mathrm{slope\_p50}),\ \log(1+\mathrm{slope\_p90}),\ \log(1+\mathrm{rough\_p50}),\ \log(1+\mathrm{relief\_p90}),\ \text{hyps}\big)
```

Earth candidates are the land cells that pass the forest, urban and water filters (terrain filters are
not applied here).

### 12.2 Shared scale, equal weight per body

With $`\boldsymbol\mu_b, \boldsymbol\sigma^2_b`$ the mean and variance of $`\mathbf f`$ on body
$`b \in \{\text{earth}, \text{moon}, \text{mars}\}`$:

```math
\boldsymbol\mu = \frac13 \sum_b \boldsymbol\mu_b,\qquad
\boldsymbol\sigma^2 = \frac13 \sum_b \left[\boldsymbol\sigma_b^2 + (\boldsymbol\mu_b - \boldsymbol\mu)^2\right]
```

```math
z_j = \sqrt{w_j}\,\frac{f_j - \mu_j}{\sigma_j},\qquad
w = (1, 1, 1, 1, 2)\ \text{for}\ (\mathrm{slope\_p50}, \mathrm{slope\_p90}, \mathrm{rough\_p50}, \mathrm{relief\_p90}, \text{hyps})
```

So Euclidean distance in $`z`$ is the weighted distance $`\sqrt{\sum_j w_j \Delta_j^2}`$ in standardised units.

### 12.3 Similarity

```math
s(d) = e^{-d}
```

- **Likeness of an Earth cell** to body $`b`$: mean distance to its $`K = 25`$ nearest cells on $`b`$,
  $`\mathrm{b\_like} = e^{-\bar d_K}`$, and its rank `b_like_p` (Section 4).
- **Best Earth match for a Moon/Mars cell**: nearest Earth cell, `earth_match_sim` $`= e^{-d_1}`$.
- **Reference sites** (Apollo, Jezero, Gale, …): the 10 nearest Earth cells in $`z`$, greedily thinned so no
  two picks are closer than 300 km on the ground.

**Why.**
- Slope, roughness and relief are heavily right-skewed; $`\log(1+x)`$ keeps flat plains from being crushed
  together. `hyps` is already 0–1 and stays linear.
- Pooling the scale over the three bodies with equal weight stops Earth's many cells (or Mars' large
  area) from deciding what "one standard deviation" means. The pooled variance is the variance of the
  equal-weight mixture.
- `hyps` gets double weight because it is the feature that separates cratered terrain from other rough
  terrain.
- Using the mean of the 25 nearest cells, not only the nearest, means a cell must look like a *typical*
  patch of the Moon or Mars, not one odd cell.
- Raw `mars_like` is higher than `moon_like` almost everywhere (Earth relief is closer to Mars), so scoring
  uses the percentiles `moon_like_p` / `mars_like_p` to keep the two bodies comparable.
- The 300 km separation keeps the match list from being ten neighbouring cells of one desert.

---

## 13. Application scoring

### 13.1 Directional weighted RMS

For one application and body, a profile gives per feature $`j`$ a target $`t_j`$, weight $`w_j`$ and direction.
The signed miss is

```math
\delta_j =
\begin{cases}
\max(x_j - t_j,\ 0) & \texttt{max}\ \ \text{(only too high is bad, e.g. dryness, cold)}\\
\min(x_j - t_j,\ 0) & \texttt{min}\ \ \text{(only too low is bad, e.g. proximity, barren)}\\
x_j - t_j & \texttt{eq}\ \ \text{(both ways)}
\end{cases}
```

```math
D_c = \sqrt{\frac{\sum_{j \in V_c} w_j\,\delta_j^2}{\sum_{j \in V_c} w_j}},\qquad
\text{score}_c = \begin{cases}1 - D_c & c \in \text{gate}\\ 0 & \text{otherwise}\end{cases}
```

$`V_c`$ is the set of features with a value in cell $`c`$, so a missing feature drops out of both sums instead
of counting as a miss. All features are on 0–1, so $`D_c \in [0, 1]`$.

### 13.2 Label and quality

```math
\text{label}_c =
\begin{cases}
\text{"both"} & |s^{\text{moon}}_c - s^{\text{mars}}_c| < 0.03\\
\text{"moon"} & s^{\text{moon}}_c > s^{\text{mars}}_c\\
\text{"mars"} & \text{otherwise}
\end{cases}
\quad\text{if } c \text{ is a site, else ""}
```

```math
\text{quality}_c = \max\!\left(s^{\text{moon}}_c,\ s^{\text{mars}}_c\right)\quad\text{(sites only, used for ranking)}
```

**Why.**
- Suitability (gate + hard condition) and body (Moon vs Mars) are separate questions. A cell is first
  "possible for this activity", then we ask which body it imitates better.
- One-sided directions match how analogs work: a place drier than the target is not worse, a place
  closer to a volcano is not worse. A plain distance would punish those.
- RMS punishes one large miss more than several small ones, so a cell cannot hide a bad feature behind
  good ones. Normalising by the weights keeps the score on 0–1 whatever the number of features.
- The 0.03 margin avoids flipping a label on noise when both bodies fit equally well.

### 13.3 Profiles

Targets are Earth percentiles unless noted (`barren`, `*_prox` are 0–1 fractions). Format:
target / weight / direction.

**Cave exploration (lava tubes)**
- Gate: `pass_forest` ∧ `pass_urban` ∧ $`d_{\text{volc}} \le 100`$ km. Site: $`d_{\text{volc}} \le 50`$ km.
- Water and terrain filters are ignored: the ocean does not affect a tube underground (keeps Lanzarote),
  and lava fields are rough by nature.

| Feature | Moon | Mars |
|---|---|---|
| `volc_prox` | 1.0 / 3 / min | 1.0 / 3 / min |
| `precip_p` | 0.20 / 1 / max | 0.20 / 1 / max |
| `temp_p` | | 0.10 / 2 / max |
| `barren` | 1.0 / 0.5 / min | 1.0 / 0.5 / min |

**Rover testing**
- Gate: land-cover filters ∧ $`\text{barren} \ge 0.5`$. Site: gate ∧ `pass_slope` ∧ `pass_rough`.

| Feature | Moon | Mars |
|---|---|---|
| `moon_like_p` / `mars_like_p` | 0.90 / 3 / min | 0.90 / 3 / min |
| `precip_p` | 0.20 / 1 / max | 0.10 / 2 / max |
| `barren` | 1.0 / 1 / min | 1.0 / 1 / min |
| `temp_p` | | 0.40 / 1 / max |

**Spacewalk / EVA**
- Gate: land-cover filters ∧ $`\text{barren} \ge 0.3`$. Site: gate ∧ `pass_slope`.

| Feature | Moon | Mars |
|---|---|---|
| `temp_range_p` | 0.90 / 2 / min | 0.70 / 0.5 / min |
| `precip_p` | 0.20 / 1 / max | 0.10 / 2 / max |
| `barren` | 1.0 / 1 / min | 1.0 / 1 / min |
| `elev_p` | 0.80 / 1 / min | 0.80 / 1.5 / min |
| `temp_p` | | 0.40 / 1 / max |

**Craters**
- Gate: land-cover filters ∧ $`d_{\text{crater}} \le 100`$ km. Site: $`d_{\text{crater}} \le 50`$ km.
- Terrain filters are ignored: crater rims are steep by nature.

| Feature | Moon | Mars |
|---|---|---|
| `crater_prox` | 1.0 / 3 / min | 1.0 / 3 / min |
| `precip_p` | 0.20 / 1 / max | 0.10 / 2 / max |
| `barren` | 1.0 / 1 / min | 1.0 / 1 / min |
| `temp_p` | | 0.40 / 1 / max |

**Why these profiles.**
- Every profile leads with the feature that makes the activity possible (proximity for caves and
  craters, terrain likeness for rovers, thermal swing for Moon EVA), weight 2–3.
- Mars surface profiles are led by dryness (`precip_p` 0.10, weight 2) with a looser cold target
  (`temp_p` 0.40), so hyperarid warm deserts like Atacama still count as Mars analogs. Caves keep the
  cold-led v1 Mars profile because surface dryness matters less underground.
- Moon EVA uses `temp_range_p` because the Moon's defining surface stress is thermal cycling, and
  `elev_p` as a proxy for thinner atmosphere and more radiation.

---

## 14. Known limits

- Thresholds, targets and weights are informed guesses, checked against the validation sites in
  `validation.py`, not fitted.
- 0.5° cells average away small features (a single lava tube or a 1 km crater), which is why point
  features enter as distances, not as cell content.
- Terrain statistics near the poles ($`|\varphi| > 75°`$) are flagged as lower confidence.
- Not NASA: WorldClim, Smithsonian GVP, Wikidata craters, ETOPO (NOAA, includes NASA SRTM). NASA: MODIS,
  GEDI, LOLA, MOLA.
