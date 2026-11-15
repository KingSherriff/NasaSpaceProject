export type AppKey = 'spacewalk' | 'rover' | 'craters' | 'cave';
export const APPS: { key: AppKey; name: string; tip: string }[] = [
  { key: 'spacewalk', name: 'Spacewalk (EVA)', tip: 'Walkable, stable ground for suited work' },
  { key: 'rover', name: 'Rover testing', tip: 'Open terrain for wheeled vehicles' },
  { key: 'craters', name: 'Craters', tip: 'Impact craters and ejecta terrain' },
  { key: 'cave', name: 'Cave exploration', tip: 'Lava tubes near basaltic volcanoes' },
];
export const LABEL_TEXT = ['Not a site', 'Moon', 'Mars', 'Both'];
export interface Meta {
  n_cells: number; mocked: string[]; label_codes: Record<string, string>;
  ranges: { temp: [number, number]; elevation: [number, number] }; units: Record<string, string>;
}
export interface AppData { label: Uint8Array; quality: Float32Array; scoreMoon: Float32Array; scoreMars: Float32Array }
export interface Dataset {
  meta: Meta; n: number; id: Int32Array; lat: Float32Array; lon: Float32Array;
  temp: Float32Array; elev: Float32Array; byCellId: Int32Array; apps: Record<AppKey, AppData>;
}
export async function loadData(url: string): Promise<Dataset> {
  const j = await (await fetch(url)).json();
  const n: number = j.meta.n_cells;
  const byCellId = new Int32Array(720 * 360).fill(-1);
  const id = Int32Array.from(j.cell_id as number[]);
  for (let i = 0; i < n; i++) byCellId[id[i]] = i;
  const apps = {} as Record<AppKey, AppData>;
  for (const { key } of APPS) {
    const a = j.apps[key];
    apps[key] = { label: Uint8Array.from(a.label), quality: Float32Array.from(a.quality),
      scoreMoon: Float32Array.from(a.score_moon), scoreMars: Float32Array.from(a.score_mars) };
  }
  return { meta: j.meta, n, id, byCellId, apps, lat: Float32Array.from(j.lat), lon: Float32Array.from(j.lon),
    temp: Float32Array.from(j.temp), elev: Float32Array.from(j.elevation) };
}
export const fmtLat = (v: number) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? 'N' : 'S'}`;
export const fmtLon = (v: number) => `${Math.abs(v).toFixed(2)}°${v >= 0 ? 'E' : 'W'}`;

// ---- Moon / Earth / Mars terrain comparison (public/data/compare.json, built by scripts/export_compare.mjs) ----
export type Body = 'moon' | 'mars';
export const BODY_NAME: Record<Body, string> = { moon: 'Moon', mars: 'Mars' };
export const BODY_COLOR: Record<Body, string> = { moon: '#f0a500', mars: '#c1440e' };
export interface Feature { key: string; label: string; unit: string; digits: number }
type Col = (number | null)[];
// Whole Moon / Mars grid. Columns are indexed by cell_id = row * ncols + col; lats/lons hold the cell centres per row/column.
export type BodyCells = { nrows: number; ncols: number; lats: number[]; lons: number[]; earth_match: number[]; earth_sim: Col } & Record<string, Col | number[] | number>;
export const bodyLat = (g: BodyCells, id: number) => g.lats[Math.floor(id / g.ncols)];
export const bodyLon = (g: BodyCells, id: number) => g.lons[id % g.ncols];
export const bodyVal = (g: BodyCells, key: string, id: number) => (g[key] as Col)[id];
const nearest = (a: number[], v: number, wrap = false) => { let best = 0, d = Infinity;
  for (let k = 0; k < a.length; k++) { let e = Math.abs(a[k] - v); if (wrap && e > 180) e = 360 - e; if (e < d) { d = e; best = k; } } return best; };
export const bodyCellAt = (g: BodyCells, lat: number, lon: number) => nearest(g.lats, lat) * g.ncols + nearest(g.lons, lon, true);
export interface SiteMatch { rank: number; cell_id: number; similarity: number; distance: number; dz: (number | null)[] }
export interface Site { body: Body; name: string; lat: number; lon: number; polar: boolean; cell: number; values: (number | null)[]; matches: SiteMatch[] }
export interface Compare {
  meta: { features: Feature[]; n_earth: number; n_earth_matched: number };
  earth: Record<string, Col>; // same order as the Dataset arrays
  moon: BodyCells; mars: BodyCells; sites: Site[];
}
export async function loadCompare(url: string, ds: Dataset): Promise<Compare> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const c = (await r.json()) as Compare;
  if (!c.moon?.lats || !c.mars?.lats) throw new Error('compare.json is from an older export; run npm run export:compare again');
  if (c.meta.n_earth !== ds.n) throw new Error('compare.json was built from a different frontend_cells.json; run npm run export:compare again');
  return c;
}
export const fmtVal = (v: number | null | undefined, f: Feature) => (v == null ? 'n/a' : `${v.toFixed(f.digits)}${f.unit === '°' ? '°' : f.unit ? ` ${f.unit}` : ''}`);
