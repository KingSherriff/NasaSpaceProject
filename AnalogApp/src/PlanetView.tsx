import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { X } from 'lucide-react';
import { BODY_COLOR, BODY_NAME, bodyCellAt, bodyLat, bodyLon, bodyVal, fmtLat, fmtLon, fmtVal, type Body, type Compare, type Dataset } from './data';
import { MAP_PROJECTION, useStore } from './store';

// NASA Solar System Treks imagery. These tiles are equirectangular (2 x 1 tiles at level 0), MapLibre wants web-mercator,
// so the "trek://" protocol below builds each mercator tile from the Trek tiles that cover it.
const TREK: Record<Body, { layer: string; credit: string }> = {
  moon: { layer: 'Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02', credit: 'Moon imagery: NASA / GSFC / Arizona State University (LRO WAC), via NASA Solar System Treks' },
  mars: { layer: 'Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m', credit: 'Mars imagery: NASA / JPL / USGS (Viking MDIM 2.1), via NASA Solar System Treks' },
};
const TREK_MAX_LEVEL = 7, T = 256;
const mercLat = (ty: number, n: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * ty) / n))) * 180) / Math.PI;

let registered = false;
function registerTrek() {
  if (registered) return; registered = true;
  maplibregl.addProtocol('trek', async (params, abort) => {
    const m = /^trek:\/\/(.+)\/(\d+)\/(\d+)\/(\d+)$/.exec(params.url); if (!m) throw new Error(`Bad trek url ${params.url}`);
    const layer = m[1], z = +m[2], x = +m[3], y = +m[4], n = 2 ** z;
    const L = Math.max(0, z - 1), deg = 180 / 2 ** L, rows = 2 ** L; // Trek level with the same pixels-per-degree
    const lon0 = (x / n) * 360 - 180, lonSpan = 360 / n;
    const c0 = Math.floor((lon0 + 180) / deg + 1e-9), c1 = Math.ceil((lon0 + lonSpan + 180) / deg - 1e-9) - 1;
    const r0 = Math.max(0, Math.floor((90 - mercLat(y, n)) / deg)), r1 = Math.min(rows - 1, Math.floor((90 - mercLat(y + 1, n)) / deg - 1e-9));
    const src = new OffscreenCanvas((c1 - c0 + 1) * T, (r1 - r0 + 1) * T), sctx = src.getContext('2d')!;
    await Promise.all(Array.from({ length: (c1 - c0 + 1) * (r1 - r0 + 1) }, async (_, k) => {
      const c = c0 + (k % (c1 - c0 + 1)), r = r0 + Math.floor(k / (c1 - c0 + 1));
      const res = await fetch(`https://trek.nasa.gov/tiles/${layer}/1.0.0/default/default028mm/${L}/${r}/${c}.jpg`, { signal: abort.signal });
      if (!res.ok) return; // leave a gap rather than failing the whole tile
      sctx.drawImage(await createImageBitmap(await res.blob()), (c - c0) * T, (r - r0) * T);
    }));
    const out = new OffscreenCanvas(T, T), octx = out.getContext('2d')!;
    const sx = ((lon0 + 180) / deg - c0) * T, sw = (lonSpan / deg) * T;
    for (let j = 0; j < T; j++) { // one output row at a time: mercator rows are not evenly spaced in latitude
      const sy = Math.min(src.height - 1, Math.max(0, ((90 - mercLat(y + (j + 0.5) / T, n)) / deg - r0) * T));
      octx.drawImage(src, sx, Math.floor(sy), sw, 1, 0, j, T, 1);
    }
    return { data: await (await out.convertToBlob({ type: 'image/jpeg', quality: 0.9 })).arrayBuffer() };
  });
}

export default function PlanetView({ body, cmp, ds }: { body: Body; cmp: Compare; ds: Dataset }) {
  const el = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const { pcell, site, projection, set, focus } = useStore();
  const g = cmp[body];

  useEffect(() => {
    registerTrek();
    const start = useStore.getState().pcell;
    const map = new maplibregl.Map({
      container: el.current!, center: start == null ? [20, 10] : [bodyLon(g, start), bodyLat(g, start)], zoom: 1.6, minZoom: 0.5, maxZoom: 7.5, renderWorldCopies: false,
      attributionControl: { compact: true },
      style: { version: 8, projection: { type: MAP_PROJECTION[useStore.getState().projection] },
        sources: { base: { type: 'raster', tileSize: 256, maxzoom: TREK_MAX_LEVEL + 1, attribution: TREK[body].credit, tiles: [`trek://${TREK[body].layer}/{z}/{x}/{y}`] } },
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#05070d' } }, { id: 'base', type: 'raster', source: 'base' }] },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('load', () => {
      map.addSource('hl', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'hl', type: 'line', source: 'hl', paint: { 'line-color': '#5eead4', 'line-width': 3 } });
      setReady(true);
    });
    map.getCanvas().style.cursor = 'crosshair';
    map.on('click', (e) => { const { lng, lat } = e.lngLat; if (Number.isFinite(lat) && Math.abs(lat) <= 90) set({ pcell: bodyCellAt(g, lat, lng) }); });
    // reference sites on this body
    const pins = cmp.sites.map((s, k) => { if (s.body !== body) return null;
      const b = document.createElement('button'); b.type = 'button'; b.className = 'site-flag'; b.textContent = s.name.replace(/\s*\(.*\)/, '');
      b.style.setProperty('--c', BODY_COLOR[body]); b.title = `${s.name}: show its Earth analogs`; b.dataset.k = String(k);
      b.addEventListener('click', (ev) => { ev.stopPropagation(); set({ site: k, pcell: s.cell }); });
      // the grid stops short of the poles on a web-mercator globe, so polar sites are pinned at its edge
      return new maplibregl.Marker({ element: b, anchor: 'bottom', offset: [0, -9], opacityWhenCovered: '0' }).setLngLat([s.lon, Math.max(-84.5, Math.min(84.5, s.lat))]).addTo(map);
    });
    return () => { pins.forEach((p) => p?.remove()); mapRef.current = null; setReady(false); map.remove(); };
  }, [body, cmp, g, set]);

  useEffect(() => { // Globe / Flat toggle
    const map = mapRef.current; if (!ready || !map) return;
    map.setProjection({ type: MAP_PROJECTION[projection] });
  }, [projection, ready]);

  useEffect(() => { // outline + fly to the selected cell
    const map = mapRef.current; if (!ready || !map) return;
    const src = map.getSource('hl') as maplibregl.GeoJSONSource;
    if (pcell == null) { src.setData({ type: 'FeatureCollection', features: [] }); return; }
    const la = bodyLat(g, pcell), lo = bodyLon(g, pcell), h = 90 / g.nrows, w = 180 / g.ncols;
    const cl = (v: number) => Math.max(-85, Math.min(85, v));
    src.setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[lo - w, cl(la - h)], [lo + w, cl(la - h)], [lo + w, cl(la + h)], [lo - w, cl(la + h)], [lo - w, cl(la - h)]]] } });
    map.flyTo({ center: [lo, cl(la)], zoom: Math.max(map.getZoom(), 3.2), speed: 1.2, essential: true });
  }, [pcell, ready, g]);

  useEffect(() => { el.current?.querySelectorAll<HTMLElement>('.site-flag').forEach((b) => b.classList.toggle('on', b.dataset.k === String(site))); }, [site, ready]);

  const here = pcell == null ? null : cmp.sites.find((s) => s.body === body && s.cell === pcell);
  // a reference site uses its own ranked analog list (same as the sidebar); any other cell uses the grid's closest match
  const top = here?.matches[0];
  const e = pcell == null ? -1 : top ? ds.byCellId[top.cell_id] ?? -1 : g.earth_match[pcell];
  const sim = pcell == null ? null : top ? top.similarity : g.earth_sim[pcell];
  return (<>
    <div ref={el} style={{ position: 'absolute', inset: 0 }} role="application" aria-label={`Globe of ${BODY_NAME[body]}`} />
    {pcell == null
      ? <p className="pointer-events-none fixed bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-lg border border-line bg-panel/90 px-3 py-2 text-xs text-mute backdrop-blur max-md:bottom-16">Click anywhere on {BODY_NAME[body]} to find its closest terrain match on Earth.</p>
      : <section aria-label={`${BODY_NAME[body]} cell details`} className="fixed right-4 top-4 z-20 max-h-[calc(100vh-2rem)] w-[22rem] overflow-y-auto rounded-lg border border-line bg-panel/95 p-4 backdrop-blur max-md:inset-x-3 max-md:top-14 max-md:w-auto">
        <div className="flex items-start justify-between">
          <div><h2 className="flex items-center gap-2 font-mono text-sm"><span className="size-2 rounded-full" style={{ background: BODY_COLOR[body] }} />{fmtLat(bodyLat(g, pcell))}, {fmtLon(bodyLon(g, pcell))}</h2>
            <p className="text-xs text-mute">{here ? here.name : `${BODY_NAME[body]} grid cell ${pcell}`}</p></div>
          <button onClick={() => set({ pcell: null })} aria-label="Close details" className="rounded p-1 text-mute hover:text-white"><X size={16} /></button>
        </div>
        {e < 0 ? <p className="mt-3 text-xs text-mute">No Earth match for this cell.</p> : <>
          <p className="mt-3 text-xs text-mute">Closest terrain on Earth</p>
          <p className="font-mono text-sm">{fmtLat(ds.lat[e])}, {fmtLon(ds.lon[e])} <span className="text-signal">{sim == null ? '' : `${Math.round(sim * 100)}% similar`}</span></p>
          <table className="mt-2 w-full table-fixed text-xs">
            <thead><tr className="text-left"><th className="w-[40%]" />
              <th className="font-medium"><span className="mr-1.5 inline-block size-2 rounded-full" style={{ background: BODY_COLOR[body] }} />{BODY_NAME[body]}</th>
              <th className="font-medium"><span className="mr-1.5 inline-block size-2 rounded-full bg-signal" />Earth</th></tr></thead>
            <tbody>{cmp.meta.features.map((f) => { const a = here ? here.values[cmp.meta.features.indexOf(f)] : bodyVal(g, f.key, pcell), b = cmp.earth[f.key][e], max = Math.max(a ?? 0, b ?? 0); return (
              <tr key={f.key}><th scope="row" className="py-1.5 pr-2 text-left align-top text-[11px] font-normal text-mute">{f.label}</th>
                {[a, b].map((v, k) => <td key={k} className="py-1.5 pr-2 font-mono">{fmtVal(v, f)}
                  <div className="mt-1 h-1 rounded-full bg-line"><div className="h-full rounded-full" style={{ width: `${v == null || max <= 0 ? 0 : Math.max(2, (v / max) * 100)}%`, background: k ? '#5eead4' : BODY_COLOR[body] }} /></div></td>)}</tr>); })}</tbody>
          </table>
          <button onClick={() => focus(e)} className="mt-3 w-full rounded-md border border-signal bg-signal/15 px-3 py-1.5 text-sm hover:bg-signal/25">Show this match on Earth</button>
          {here && <p className="mt-2 text-[11px] text-mute">Reference site: its 10 best Earth analogs are listed in the sidebar and pinned on the Earth globe.</p>}
        </>}
      </section>}
  </>);
}
