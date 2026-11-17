import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { BODY_COLOR, BODY_NAME, fmtLat, fmtLon, type Compare, type Dataset } from './data';
import type { Result } from './filter';
import { MAP_PROJECTION, useStore } from './store';

const W = 4096; // canvas covers the whole web-mercator world; each cell is ~5.7 px
const COORDS: [[number, number], [number, number], [number, number], [number, number]] = [[-180, 85.0511], [180, 85.0511], [180, -85.0511], [-180, -85.0511]];
const yN =(lat: number) => { const s = Math.sin((Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI) / 180); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };
const xN = (lon: number) => (lon + 180) / 360;
const BASE = [[190, 205, 225], [240, 165, 0], [193, 68, 14], [123, 63, 160]];
const FILLS = BASE.map(([r, g, b], l) => Array.from({ length: 16 }, (_, k) => `rgba(${r},${g},${b},${l === 0 ? 0.38 : 0.3 + 0.7 * (k / 15)})`));
const poly = (ds: Dataset, i: number) => { const la = ds.lat[i], lo = ds.lon[i];
  return [[[lo - 0.25, la - 0.25], [lo + 0.25, la - 0.25], [lo + 0.25, la + 0.25], [lo - 0.25, la + 0.25], [lo - 0.25, la - 0.25]]]; };

export default function MapView({ ds, res, cmp, hidden = false }: { ds: Dataset; res: Result; cmp: Compare | null; hidden?: boolean }) {
  const el = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const canvas = useRef<HTMLCanvasElement>(document.createElement('canvas'));
  const resRef = useRef(res); resRef.current = res;
  const [ready, setReady] = useState(false);
  const busy = useRef(false), dirty = useRef(false), lastUrl = useRef<string | null>(null);
  const { hovered, selected, flyReq, site, projection, hover, select } = useStore();

  useEffect(() => {
    canvas.current.width = canvas.current.height = W;
    const map = new maplibregl.Map({
      container: el.current!, center: [-60, 25], zoom: 1.6, minZoom: 0.5, maxZoom: 9, renderWorldCopies: false,
      attributionControl: { compact: true },
      style: { version: 8, projection: { type: MAP_PROJECTION[useStore.getState().projection] },
        sky: { 'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0] },
        sources: { base: { type: 'raster', tileSize: 256, maxzoom: 18,
        attribution: 'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'] } },
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#05070d' } },
          // slightly dimmed so the coloured analog cells stay readable on top of the imagery
          { id: 'base', type: 'raster', source: 'base', paint: { 'raster-brightness-max': 0.85, 'raster-saturation': -0.15 } }] },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('load', () => {
      map.addSource('cells', { type: 'image', url: canvas.current.toDataURL(), coordinates: COORDS });
      // no 'raster-resampling': 'nearest' here: in maplibre-gl 5.24 it turns this overlay into an opaque black sheet
      map.addLayer({ id: 'cells', type: 'raster', source: 'cells', paint: { 'raster-fade-duration': 0 } });
      map.addSource('hl', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'hl-h', type: 'line', source: 'hl', filter: ['==', ['get', 'k'], 'h'], paint: { 'line-color': '#fff', 'line-width': 2 } });
      map.addLayer({ id: 'hl-s', type: 'line', source: 'hl', filter: ['==', ['get', 'k'], 's'], paint: { 'line-color': '#5eead4', 'line-width': 3 } });
      setReady(true);
    });
    const cellAt = (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat; if (!Number.isFinite(lat) || lat > 90 || lat < -90) return null;
      const id = Math.floor((90 - lat) / 0.5) * 720 + Math.floor((lng + 180) / 0.5);
      const i = ds.byCellId[id] ?? -1; return i >= 0 && resRef.current.match[i] ? i : null;
    };
    map.on('mousemove', (e) => { const i = cellAt(e); map.getCanvas().style.cursor = i == null ? '' : 'pointer'; hover(i); });
    map.on('mouseout', () => hover(null));
    map.on('click', (e) => select(cellAt(e)));
    return () => { mapRef.current = null; setReady(false); map.remove(); };
  }, [ds]);

  useEffect(() => { // redraw matching cells whenever filters change
    const map = mapRef.current; if (!ready || !map) return;
    const draw = () => {
      const r = resRef.current, ctx = canvas.current.getContext('2d')!; ctx.clearRect(0, 0, W, W);
      for (let k = 0; k < r.n; k++) {
        const i = r.idx[k], la = ds.lat[i], lo = ds.lon[i];
        const x0 = Math.round(xN(lo - 0.25) * W), x1 = Math.round(xN(lo + 0.25) * W);
        const y0 = Math.round(yN(la + 0.25) * W), y1 = Math.round(yN(la - 0.25) * W);
        ctx.fillStyle = FILLS[r.label[k]][Math.round(r.q[k] * 15)];
        ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      }
    };
    // Encoding the canvas is async, so keep only the newest frame in flight (sliders fire many updates).
    if (busy.current) { dirty.current = true; return; }
    busy.current = true;
    const push = () => {
      dirty.current = false; draw();
      canvas.current.toBlob((blob) => {
        if (blob && mapRef.current === map) {
          const url = URL.createObjectURL(blob), old = lastUrl.current; lastUrl.current = url;
          (map.getSource('cells') as maplibregl.ImageSource | undefined)?.updateImage({ url, coordinates: COORDS });
          if (old) setTimeout(() => URL.revokeObjectURL(old), 2000);
        }
        if (dirty.current) push(); else busy.current = false;
      });
    };
    push();
  }, [res, ready, ds]);

  useEffect(() => {
    const map = mapRef.current; if (!ready || !map) return;
    const f = (i: number | null, k: string) => i == null ? [] : [{ type: 'Feature' as const, properties: { k }, geometry: { type: 'Polygon' as const, coordinates: poly(ds, i) } }];
    (map.getSource('hl') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: [...f(hovered, 'h'), ...f(selected, 's')] });
  }, [hovered, selected, ready, ds]);

  useEffect(() => { // numbered pins on the Earth analogs of the selected Moon/Mars reference site
    const map = mapRef.current; if (!ready || !map || !cmp || site == null) return;
    const s = cmp.sites[site], pins: maplibregl.Marker[] = [];
    for (const m of s.matches) {
      const i = ds.byCellId[m.cell_id] ?? -1; if (i < 0) continue;
      const b = document.createElement('button'); b.type = 'button'; b.className = 'site-pin'; b.textContent = String(m.rank);
      b.style.background = BODY_COLOR[s.body]; b.style.color = s.body === 'moon' ? '#1a1200' : '#fff';
      b.title = `#${m.rank} Earth analog of ${s.name} (${BODY_NAME[s.body]}): ${fmtLat(ds.lat[i])} ${fmtLon(ds.lon[i])}, ${Math.round(m.similarity * 100)}% similar`;
      b.setAttribute('aria-label', b.title);
      b.addEventListener('click', (e) => { e.stopPropagation(); select(i); });
      pins.push(new maplibregl.Marker({ element: b, opacityWhenCovered: '0' /* hide pins on the far side of the globe */ }).setLngLat([ds.lon[i], ds.lat[i]]).addTo(map));
    }
    const first = s.matches.length ? ds.byCellId[s.matches[0].cell_id] ?? -1 : -1;
    if (first >= 0) map.flyTo({ center: [ds.lon[first], ds.lat[first]], zoom: 2.4, speed: 1.2, essential: true });
    return () => pins.forEach((p) => p.remove());
  }, [site, cmp, ready, ds, select]);

  useEffect(() => { // Globe / Flat toggle: switch projection in place, keeping the view, overlay and pins
    const map = mapRef.current; if (!ready || !map) return;
    map.setProjection({ type: MAP_PROJECTION[projection] });
  }, [projection, ready]);

  useEffect(() => {
    const map = mapRef.current; if (!flyReq || !map) return;
    map.flyTo({ center: [ds.lon[flyReq.idx], ds.lat[flyReq.idx]], zoom: Math.max(map.getZoom(), 5), speed: 1.3, essential: true });
  }, [flyReq, ds]);

  // inline style: maplibre-gl.css sets .maplibregl-map{position:relative}, which beats Tailwind's layered `absolute` and collapses the map to 0 height
  return <div ref={el} style={{ position: 'absolute', inset: 0, visibility: hidden ? 'hidden' : 'visible' }} aria-hidden={hidden} role="application" aria-label="World map of analog cells" />;
}
