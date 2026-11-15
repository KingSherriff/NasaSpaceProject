// Builds public/data/compare.json (Moon / Earth / Mars terrain comparison) from the pipeline's parquet files.
//   node scripts/export_compare.mjs [dir with the .parquet files] [frontend_cells.json] [output json]
// Needs: cells, moon_cells_matched, mars_cells_matched, planet_sites, site_matches (.parquet).
// Earth columns are written in the same order as frontend_cells.json, so index i is the same cell in both files.
import { asyncBufferFromFile, parquetReadObjects } from 'hyparquet';
import { compressors } from 'hyparquet-compressors';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const dir = resolve(process.argv[2] ?? 'public/data');
const cellsJson = resolve(process.argv[3] ?? 'public/data/frontend_cells.json');
const out = resolve(process.argv[4] ?? 'public/data/compare.json');

// The five terrain features the matching was done on (same ones site_matches reports dz_* for).
const FEATURES = [
  { key: 'slope_p50', label: 'Typical slope', unit: '°', digits: 2 },
  { key: 'slope_p90', label: 'Steep slope (p90)', unit: '°', digits: 2 },
  { key: 'rough_p50', label: 'Roughness (median)', unit: '', digits: 1 },
  { key: 'relief_p90', label: 'Relief (p90)', unit: 'm', digits: 0 },
  { key: 'hyps', label: 'Hypsometric integral', unit: '', digits: 3 },
];
const BODIES = ['moon', 'mars'];

const read = async (name, columns) => parquetReadObjects({ file: await asyncBufferFromFile(`${dir}/${name}.parquet`), compressors, columns });
const num = (v) => (typeof v === 'bigint' ? Number(v) : v);
const round = (v, d) => (v == null || Number.isNaN(v) ? null : +num(v).toFixed(d));
const fkeys = FEATURES.map((f) => f.key);

const frontend = JSON.parse(readFileSync(cellsJson, 'utf8'));
const earthRows = await read('cells', ['cell_id', ...fkeys, 'moon_like', 'mars_like', 'moon_match_id', 'mars_match_id']);
if (earthRows.length !== frontend.cell_id.length || earthRows.some((r, i) => num(r.cell_id) !== frontend.cell_id[i]))
  throw new Error('cells.parquet and frontend_cells.json do not list the same cells in the same order. Re-export both from the same pipeline run.');

const sites = await read('planet_sites');
const matches = await read('site_matches');

// Moon / Mars: the whole grid, so the app can show those globes and look up any cell you click.
// Columns are indexed by cell_id (= row * ncols + col); lat/lon are stored once per row/column.
const earthIndex = new Map(frontend.cell_id.map((id, i) => [id, i]));
const bodies = {};
for (const b of BODIES) {
  const rows = await read(`${b}_cells_matched`, ['cell_id', 'lat', 'lon', 'earth_match_id', 'earth_match_sim', ...fkeys]);
  const lats = [...new Set(rows.map((r) => r.lat))], lons = [...new Set(rows.map((r) => r.lon))];
  const ok = rows.length === lats.length * lons.length && rows.every((r, i) => num(r.cell_id) === i && r.lat === lats[Math.floor(i / lons.length)] && r.lon === lons[i % lons.length]);
  if (!ok) throw new Error(`${b}_cells_matched.parquet is not a regular row-major lat/lon grid with cell_id = row * ncols + col`);
  const col = { nrows: lats.length, ncols: lons.length, lats: lats.map((v) => round(v, 4)), lons: lons.map((v) => round(v, 4)),
    earth_match: rows.map((r) => earthIndex.get(num(r.earth_match_id)) ?? -1), // index into earth.* columns
    earth_sim: rows.map((r) => round(r.earth_match_sim, 3)) };
  FEATURES.forEach((f) => { col[f.key] = rows.map((r) => round(r[f.key], f.digits)); });
  bodies[b] = col;
}

const earth = {};
FEATURES.forEach((f) => { earth[f.key] = earthRows.map((r) => round(r[f.key], f.digits)); });
for (const b of BODIES) {
  earth[`${b}_like`] = earthRows.map((r) => round(r[`${b}_like`], 3)); // null = no match computed for this cell
  earth[`${b}_match`] = earthRows.map((r) => (r[`${b}_match_id`] == null ? -1 : num(r[`${b}_match_id`]))); // cell_id on that body
}

const siteList = sites.map((s) => ({
  body: s.body, name: s.name, lat: round(s.lat, 2), lon: round(s.lon, 2), polar: !!s.polar,
  cell: num(s.cell_id), // cell_id on that body's grid
  values: FEATURES.map((f) => round(s[f.key], f.digits)),
  matches: matches.filter((m) => m.body === s.body && m.site === s.name).sort((a, b) => num(a.rank) - num(b.rank)).map((m) => ({
    rank: num(m.rank), cell_id: num(m.earth_cell_id), similarity: round(m.similarity, 3), distance: round(m.distance, 3),
    dz: FEATURES.map((f) => round(m[`dz_${f.key}`], 2)), // Earth minus site, in standard deviations
  })),
}));
const noMatches = siteList.filter((s) => !s.matches.length).map((s) => s.name);
if (noMatches.length) console.warn('No rows in site_matches for:', noMatches.join(', '));

const payload = {
  meta: {
    generated: new Date().toISOString().slice(0, 10), features: FEATURES,
    n_earth: earthRows.length, n_earth_matched: earthRows.filter((r) => r.moon_like != null).length,
        notes: 'earth.*: same order as frontend_cells.json. earth.<body>_match: cell_id on that body, -1 = none. <body>.*: indexed by cell_id = row * ncols + col. <body>.earth_match: index into earth.*. sites[].matches[].dz: Earth minus site, in standard deviations.',
  },
  earth, moon: bodies.moon, mars: bodies.mars, sites: siteList,
};
const json = JSON.stringify(payload);
writeFileSync(out, json);
console.log(`Wrote ${out} (${(json.length / 1e6).toFixed(1)} MB): ${siteList.length} sites, ${payload.meta.n_earth_matched} of ${earthRows.length} Earth cells matched, ${bodies.moon.earth_match.length} Moon and ${bodies.mars.earth_match.length} Mars cells.`);
