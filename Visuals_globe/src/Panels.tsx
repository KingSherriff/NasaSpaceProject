import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { APPS, BODY_COLOR, BODY_NAME, LABEL_TEXT, bodyLat, bodyLon, bodyVal, fmtLat, fmtLon, fmtVal, type Body, type Compare, type Dataset } from './data';
import { useStore } from './store';
import type { Result } from './filter';

const COLORS = ['#9fb0c8', '#f0a500', '#c1440e', '#7b3fa0'];
const Demo = () => <span className="rounded-sm border border-amber-400/40 bg-amber-400/10 px-1.5 py-px text-[10px] text-amber-300">demo data</span>;

export function Legend({ res, ds }: { res: Result; ds: Dataset }) {
  const { sidebar, apps, hovered } = useStore();
  return (
    <div className={`fixed bottom-4 z-10 rounded-lg border border-line bg-panel/90 px-3 py-2.5 backdrop-blur transition-[left] duration-300 max-md:bottom-16 ${sidebar ? 'md:left-84' : 'md:left-4'} left-3`}>
      <p aria-live="polite" className="font-mono text-sm"><span className="text-signal">{res.n.toLocaleString()}</span> matching cells</p>
      <ul className="mt-1.5 flex gap-3 text-xs text-mute">
        {apps.length ? [1, 2, 3].map((l) => <li key={l} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: COLORS[l] }} />{LABEL_TEXT[l]}</li>)
          : <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: COLORS[0] }} />Land cell</li>}
        {apps.length > 0 && <li>brighter = higher quality</li>}
      </ul>
      <p className="mt-1 h-4 font-mono text-xs text-mute">{hovered != null ? `${fmtLat(ds.lat[hovered])}  ${fmtLon(ds.lon[hovered])}` : 'hover a cell'}</p>
    </div>);
}

// Earth cell next to its Moon and Mars counterparts, on the five terrain features the matching uses.
// A column shows the selected reference site when this cell is one of its analogs, otherwise the cell's closest match on that body.
function TerrainCompare({ ds, cmp, i }: { ds: Dataset; cmp: Compare; i: number }) {
  const siteIdx = useStore((s) => s.site), showOn = useStore((s) => s.showOn);
  const site = siteIdx == null ? null : cmp.sites[siteIdx];
  const viaSite = site?.matches.find((m) => m.cell_id === ds.id[i]);
  const cols = (['moon', 'mars'] as Body[]).map((b) => {
    if (site && viaSite && site.body === b) return { b, title: site.name, where: `${fmtLat(site.lat)} ${fmtLon(site.lon)}`, sim: viaSite.similarity as number | null, values: site.values, rank: viaSite.rank, cell: site.cell };
    const k = cmp.earth[`${b}_match`][i] ?? -1; if (k < 0) return null;
    return { b, title: 'closest cell', where: `${fmtLat(bodyLat(cmp[b], k))} ${fmtLon(bodyLon(cmp[b], k))}`, sim: cmp.earth[`${b}_like`][i], values: cmp.meta.features.map((f) => bodyVal(cmp[b], f.key, k)), rank: 0, cell: k };
  });
  const head = 'mt-3 border-t border-line pt-3';
  if (!cols[0] && !cols[1]) return <div className={head}><h3 className="text-sm font-medium">Moon / Earth / Mars terrain</h3><p className="mt-1 text-xs text-mute">No Moon or Mars terrain match was computed for this cell.</p></div>;
  const earth = cmp.meta.features.map((f) => cmp.earth[f.key][i]);
  const Bar = ({ v, max, c }: { v: number | null; max: number; c: string }) => <div className="mt-1 h-1 rounded-full bg-line"><div className="h-full rounded-full" style={{ width: `${v == null || max <= 0 ? 0 : Math.max(2, (v / max) * 100)}%`, background: c }} /></div>;
  return (
    <div className={head}>
      <h3 className="text-sm font-medium">Moon / Earth / Mars terrain</h3>
      <table className="mt-2 w-full table-fixed border-separate border-spacing-x-2 text-xs" style={{ marginInline: '-0.5rem', width: 'calc(100% + 1rem)' }}>
        <thead><tr className="align-top text-left">
          <th className="font-normal"><span className="flex items-center gap-1.5 font-medium"><span className="size-2 rounded-full bg-signal" />Earth</span><span className="block text-[11px] text-mute">this cell</span></th>
          {cols.map((c, k) => { const b = (['moon', 'mars'] as Body[])[k]; return (
            <th key={b} className="font-normal"><span className="flex items-center gap-1.5 font-medium"><span className="size-2 rounded-full" style={{ background: BODY_COLOR[b] }} />{BODY_NAME[b]}</span>
              {c ? <><span className="block text-[11px] text-mute">{c.rank ? `${c.title} (analog #${c.rank})` : c.title}</span><span className="block font-mono text-[10px] text-mute">{c.where}</span>
                <span className="block font-mono text-[11px]">{c.sim == null ? 'n/a' : `${Math.round(c.sim * 100)}% similar`}</span>
                <button onClick={() => showOn(b, c.cell)} className="mt-1 rounded border border-line px-1.5 py-0.5 text-[11px] font-normal text-mute hover:text-white focus-visible:outline-2 focus-visible:outline-signal">View on {BODY_NAME[b]}</button></> : <span className="block text-[11px] text-mute">no match</span>}</th>); })}
        </tr></thead>
        <tbody>
          {cmp.meta.features.map((f, r) => { const vals = [earth[r], cols[0]?.values[r] ?? null, cols[1]?.values[r] ?? null]; const max = Math.max(...vals.map((v) => v ?? 0)); return [
            <tr key={f.key}><th colSpan={3} scope="rowgroup" className="pt-2.5 text-left text-[11px] font-normal text-mute">{f.label}</th></tr>,
            <tr key={f.key + 'v'}>{vals.map((v, k) => <td key={k} className="font-mono">{k > 0 && !cols[k - 1] ? '' : fmtVal(v, f)}<Bar v={v} max={max} c={k === 0 ? '#5eead4' : BODY_COLOR[k === 1 ? 'moon' : 'mars']} /></td>)}</tr>]; })}
        </tbody>
      </table>
    </div>);
}

export function DetailCard({ ds, cmp }: { ds: Dataset; cmp: Compare | null }) {
  const { selected: i, select } = useStore();
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && select(null); addEventListener('keydown', k); return () => removeEventListener('keydown', k); }, [select]);
  if (i == null) return null;
  const mocked = ds.meta.mocked;
  return (
    <section aria-label="Cell details" className="fixed right-4 top-4 z-20 max-h-[calc(100vh-2rem)] w-[22rem] overflow-y-auto rounded-lg border border-line bg-panel/95 p-4 backdrop-blur max-md:inset-x-3 max-md:top-3 max-md:w-auto">
      <div className="flex items-start justify-between">
        <div><h2 className="font-mono text-sm">{fmtLat(ds.lat[i])}, {fmtLon(ds.lon[i])}</h2><p className="font-mono text-xs text-mute">cell id {ds.id[i]}</p></div>
        <button onClick={() => select(null)} aria-label="Close details" className="rounded p-1 text-mute hover:text-white"><X size={16} /></button>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-xs text-mute">Avg. temperature</dt><dd className="font-mono">{ds.temp[i].toFixed(1)} °C</dd></div>
        <div><dt className="flex items-center gap-1.5 text-xs text-mute">Avg. elevation {mocked.includes('elevation') && <Demo />}</dt><dd className="font-mono">{Math.round(ds.elev[i])} m</dd></div>
      </dl>
      {cmp && <TerrainCompare ds={ds} cmp={cmp} i={i} />}
      <ul className="mt-4 space-y-3 border-t border-line pt-3">
        {APPS.map((a) => { const d = ds.apps[a.key], l = d.label[i]; return (
          <li key={a.key} className="text-sm">
            <div className="flex items-center justify-between gap-2"><span>{a.name}</span>
              <span className="flex items-center gap-1.5">{mocked.includes(a.key) && <Demo />}
                <span className="rounded px-1.5 py-px text-xs font-medium" style={{ background: l ? COLORS[l] : '#1b2331', color: l === 1 ? '#1a1200' : l ? '#fff' : '#8a95a8' }}>{LABEL_TEXT[l]}</span></span></div>
            <div className="mt-1.5 flex items-center gap-2"><div role="meter" aria-label={`${a.name} quality`} aria-valuemin={0} aria-valuemax={1} aria-valuenow={d.quality[i]} className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
              <div className="h-full" style={{ width: `${d.quality[i] * 100}%`, background: COLORS[l] }} /></div><span className="w-9 text-right font-mono text-xs">{d.quality[i].toFixed(2)}</span></div>
            <p className="mt-1 font-mono text-xs text-mute">score moon {d.scoreMoon[i].toFixed(2)} · score mars {d.scoreMars[i].toFixed(2)}</p>
          </li>); })}
      </ul>
    </section>);
}

export function AboutModal({ ds }: { ds: Dataset }) {
  const { about, set } = useStore(); const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; if (!d) return; if (about && !d.open) d.showModal(); if (!about && d.open) d.close(); }, [about]);
  const layers = [
    { k: 'temp', name: 'Avg. temperature', note: ds.meta.units.temp }, { k: 'elevation', name: 'Avg. elevation', note: ds.meta.units.elevation ?? ds.meta.units.temp },
    ...APPS.map((a) => ({ k: a.key as string, name: a.name, note: 'Analog label, quality and per-body scores' }))];
  return (
    <dialog ref={ref} onClose={() => set({ about: false })} className="m-auto w-[min(32rem,92vw)] rounded-lg border border-line bg-panel p-5 text-[#d7dde8]">
      <div className="flex items-center justify-between"><h2 className="text-base font-semibold">About the data</h2>
        <button onClick={() => set({ about: false })} aria-label="Close" className="text-mute hover:text-white"><X size={16} /></button></div>
      <p className="mt-2 text-sm text-mute">{ds.n.toLocaleString()} land cells on a 0.5° grid. Layers marked demo data are placeholders for the hackathon and not real measurements.</p>
      <ul className="mt-3 divide-y divide-line text-sm">
        {layers.map((l) => <li key={l.k} className="flex items-start justify-between gap-3 py-2"><div><p>{l.name}</p><p className="text-xs text-mute">{l.k === 'elevation' ? 'Meters (mock)' : l.note}</p></div>
          {ds.meta.mocked.includes(l.k) ? <Demo /> : <span className="text-xs text-signal">real data</span>}</li>)}
      </ul>
    </dialog>);
}
