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
  ranges: { temp: [number, number]; elevation: [number, number] }; units: { temp: string; elevation: string };
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
