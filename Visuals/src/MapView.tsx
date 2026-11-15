import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { Dataset } from './data';
import type { Result } from './filter';
import { useStore } from './store';

const W = 2880; // offscreen canvas covers the whole web-mercator world; each cell is 4 px wide
const COORDS: [[number, number], [number, number], [number, number], [number, number]] = [[-180, 85.0511], [180, 85.0511], [180, -85.0511], [-180, -85.0511]];
const yN = (lat: number) => { const s = Math.sin((Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI) / 180); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };
const xN = (lon: number) => (lon + 180) / 360;
const BASE = [[190, 205, 225], [240, 165, 0], [193, 68, 14], [123, 63, 160]];
const FILLS = BASE.map(([r, g, b], l) => Array.from({ length: 16 }, (_, k) => `rgba(${r},${g},${b},${l === 0 ? 0.38 : 0.3 + 0.7 * (k / 15)})`));
const poly = (ds: Dataset, i: number) => { const la = ds.lat[i], lo = ds.lon[i];
  return [[[lo - 0.25, la - 0.25], [lo + 0.25, la - 0.25], [lo + 0.25, la + 0.25], [lo - 0.25, la + 0.25], [lo - 0.25, la - 0.25]]]; };

export default function MapView({ ds, res }: { ds: Dataset; res: Result }) {
  const el = useRef<HTMLDivElement>(null), mapRef = useRef<maplibregl.Map | null>(null);
  const canvas = useRef<HTMLCanvasElement>(document.createElement('canvas'));
  const resRef = useRef(res); resRef.current = res;
  const [ready, setReady] = useState(false);
  const base = useRef<HTMLCanvasElement | null>(null);
  const busy = useRef(false), dirty = useRef(false), lastUrl = useRef<string | null>(null);
  const { hovered, selected, flyReq, hover, select } = useStore();

  useEffect(() => {
    canvas.current.width = canvas.current.height = W;
    const map = new maplibregl.Map({
      container: el.current!, center: [-60, 25], zoom: 1.6, minZoom: 1, maxZoom: 9, renderWorldCopies: false,
      attributionControl: { compact: true },
      style: { version: 8, sources: { base: { type: 'raster', tileSize: 256, attribution: '© OpenStreetMap contributors', maxzoom: 19,
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'] } },
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#05070d' } },
          { id: 'base', type: 'raster', source: 'base', paint: { 'raster-brightness-min': 1, 'raster-brightness-max': 0.08, 'raster-hue-rotate': 180, 'raster-saturation': -0.5, 'raster-contrast': 0.1 } }] },
    });
    mapRef.current = map; map.on('error', (e) => console.error('map error', e.error?.message ?? e));
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('load', () => {
      map.addSource('cells', { type: 'image', url: canvas.current.toDataURL(), coordinates: COORDS });
      map.addLayer({ id: 'cells', type: 'raster', source: 'cells', paint: { 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } });
      map.addSource('hl', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'hl-h', type: 'line', source: 'hl', filter: ['==', ['get', 'k'], 'h'], paint: { 'line-color': '#fff', 'line-width': 2 } });
      map.addLayer({ id: 'hl-s', type: 'line', source: 'hl', filter: ['==', ['get', 'k'], 's'], paint: { 'line-color': '#5eead4', 'line-width': 3 } });
      setReady(true);
    });
    const cellAt = (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat; if (lat > 90 || lat < -90) return null;
      const id = Math.floor((90 - lat) / 0.5) * 720 + Math.floor((lng + 180) / 0.5);
      const i = ds.byCellId[id] ?? -1; return i >= 0 && resRef.current.match[i] ? i : null;
    };
    map.on('mousemove', (e) => { const i = cellAt(e); map.getCanvas().style.cursor = i == null ? '' : 'pointer'; hover(i); });
    map.on('mouseout', () => hover(null));
    map.on('click', (e) => select(cellAt(e)));
    return () => map.remove();
  }, [ds]);

  useEffect(() => { // redraw matching cells whenever filters change
    const map = mapRef.current; if (!ready || !map) return;
    if (!base.current) { // faint land context, drawn once
      const c = document.createElement('canvas'); c.width = c.height = W; const x = c.getContext('2d')!; x.fillStyle = 'rgba(160,175,200,0.2)';
      for (let i = 0; i < ds.n; i++) {
        const la = ds.lat[i], lo = ds.lon[i], x0 = Math.round(xN(lo - 0.25) * W), y0 = Math.round(yN(la + 0.25) * W);
        x.fillRect(x0, y0, Math.round(xN(lo + 0.25) * W) - x0, Math.round(yN(la - 0.25) * W) - y0);
      }
      base.current = c;
    }
    const draw = () => { const r = resRef.current;
    const ctx = canvas.current.getContext('2d')!; ctx.clearRect(0, 0, W, W); ctx.drawImage(base.current!, 0, 0);
    for (let k = 0; k < r.n; k++) {
      const i = r.idx[k], la = ds.lat[i], lo = ds.lon[i];
      const x0 = Math.round(xN(lo - 0.25) * W), x1 = Math.round(xN(lo + 0.25) * W);
      const y0 = Math.round(yN(la + 0.25) * W), y1 = Math.round(yN(la - 0.25) * W);
      ctx.fillStyle = FILLS[r.label[k]][Math.round(r.q[k] * 15)];
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
    } };
    draw();
    // Push the canvas to the map as an image. Encoding is async, so keep only the newest frame in flight.
    if (busy.current) { dirty.current = true; return; }
    busy.current = true;
    const push = () => {
      dirty.current = false;
      canvas.current.toBlob((blob) => {
        if (blob) {
          const url = URL.createObjectURL(blob), old = lastUrl.current; lastUrl.current = url;
          (map.getSource('cells') as maplibregl.ImageSource).updateImage({ url, coordinates: COORDS });
          if (old) setTimeout(() => URL.revokeObjectURL(old), 2000);
        }
        if (dirty.current) { draw(); push(); } else busy.current = false;
      });
    };
    push();
  }, [res, ready, ds]);

  useEffect(() => {
    const map = mapRef.current; if (!ready || !map) return;
    const f = (i: number | null, k: string) => i == null ? [] : [{ type: 'Feature' as const, properties: { k }, geometry: { type: 'Polygon' as const, coordinates: poly(ds, i) } }];
    (map.getSource('hl') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: [...f(hovered, 'h'), ...f(selected, 's')] });
  }, [hovered, selected, ready, ds]);

  useEffect(() => {
    const map = mapRef.current; if (!flyReq || !map) return;
    map.flyTo({ center: [ds.lon[flyReq.idx], ds.lat[flyReq.idx]], zoom: Math.max(map.getZoom(), 5), speed: 1.3, essential: true });
  }, [flyReq, ds]);

  return <div ref={el} style={{ position: 'absolute', inset: 0 }} role="application" aria-label="World map of analog cells" />;
}
