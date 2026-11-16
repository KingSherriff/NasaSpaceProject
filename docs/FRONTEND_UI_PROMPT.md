# Prompt: generate the frontend UI

Copy everything below the line into your UI generator (or give it to a teammate as the brief).
Data file: `public/data/frontend_cells.json` (produced by `scripts/export_frontend.py`).

---

Build a single-page web app: an interactive world map for **NASA Space Apps 2026 (Edmonton)**, challenge: *find and characterise terrestrial analogs for the Moon and Mars from open NASA data*. App name: **Analog**.

## What the user does
They look for places on Earth that are good analogs for the Moon and/or Mars, for a chosen activity. They pick filters on the left, and the map shows only the cells that satisfy all of them.

## Layout
- **Full-screen map** (dark, space-like basemap; MapLibre GL or Leaflet, no API key required). The map is the hero.
- **Left sidebar** (about 320 px, collapsible, becomes a bottom sheet on mobile) with the filters.
- **Right-side detail card** that appears when a cell is clicked.
- **Bottom-left legend** and a small counter: "1,204 matching cells".
- Dark theme, clean and modern, mission-control feel. Accent colours: Moon = amber `#f0a500`, Mars = rust `#c1440e`, Both = purple `#7b3fa0`.

## Sidebar filters
1. **Target** (segmented control, multi-select): `Moon` · `Mars` · `Both`
   - Selecting several means "match any of the selected".
2. **Applications** (toggle chips, multi-select; a cell must match ALL selected):
   - Spacewalk (EVA)
   - Rover testing
   - Craters
   - Cave exploration
   - Each chip has a small icon and a one-line tooltip (e.g. Cave: "Lava tubes near basaltic volcanoes").
3. **Avg. temperature**: range slider (°C), bounds from `meta.ranges.temp`.
4. **Avg. elevation**: range slider (m), bounds from `meta.ranges.elevation`.
5. **Reset filters** button.
6. A small "About the data" link that opens a modal: which layers are real and which are mocked (read `meta.mocked`; show a "demo data" badge on mocked ones).

If no application is selected, show all land cells, shaded by the temperature slider only (a light neutral colour).

## Map rendering
- Draw the data as a **0.5° grid of squares** (each cell is `lat ± 0.25`, `lon ± 0.25`), not as points. Use a canvas or a GeoJSON/raster layer. About 95,000 cells, so it must stay smooth.
- Only cells matching all active filters are drawn highlighted. Non-matching cells are hidden or very faint.
- **Colour by body:** amber = Moon, rust = Mars, purple = Both (from the `label` of the selected application).
- **Opacity or brightness by `quality`** (0–1): higher quality is brighter, so best sites stand out.
- With several applications selected, colour by the combined label and use the minimum quality across them.

## Interactions
- Hover: highlight the cell and show lat/lon.
- Click: open the detail card with
  - coordinates and cell id,
  - temperature and elevation,
  - one row per application: label (Moon / Mars / Both / not a site), quality as a small bar, `score_moon` and `score_mars`,
  - a "demo data" badge for mocked applications.
- "Top sites" list (collapsible panel): the 10 best matching cells by quality, click to fly to the cell.
- Smooth fly-to and zoom animations. Filters update the map instantly (client-side, no server).

## Data contract
Load `/data/frontend_cells.json` once. It is **columnar**: every array has `meta.n_cells` entries and the same index means the same cell.

```
meta         { n_cells, mocked: [...], label_codes, filter_semantics, ranges: {temp:[min,max], elevation:[min,max]}, units }
cell_id[]  lat[]  lon[]  passes_all[]  temp[]  elevation[]
apps: {
  spacewalk | rover | craters | cave: {
    label[]       0 = not a site, 1 = moon, 2 = mars, 3 = both
    quality[]     0..1, for ranking
    score_moon[]  0..1
    score_mars[]  0..1
  }
}
```

Filter logic, per cell, per selected application:
- target Moon: `label & 1`
- target Mars: `label & 2`
- target Both: `label === 3`
- several targets selected: any of them matches
- several applications selected: all must match
- temperature and elevation: `min <= value <= max`

Build index arrays once (typed arrays) and re-filter on slider input, so dragging stays responsive.

## Tech
React + TypeScript + Vite, MapLibre GL JS, Tailwind. No backend. State in a small store (Zustand or React state). Accessible controls (keyboard, labels), colours not the only cue (also show text labels in the detail card).

## Out of scope
Auth, user accounts, saving, backend, real-time data, 3D globe.
