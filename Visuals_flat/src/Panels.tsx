import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { APPS, LABEL_TEXT, fmtLat, fmtLon, type Dataset } from './data';
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

export function DetailCard({ ds }: { ds: Dataset }) {
  const { selected: i, select } = useStore();
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && select(null); addEventListener('keydown', k); return () => removeEventListener('keydown', k); }, [select]);
  if (i == null) return null;
  const mocked = ds.meta.mocked;
  return (
    <section aria-label="Cell details" className="fixed right-4 top-4 z-20 max-h-[calc(100vh-2rem)] w-80 overflow-y-auto rounded-lg border border-line bg-panel/95 p-4 backdrop-blur max-md:inset-x-3 max-md:top-3 max-md:w-auto">
      <div className="flex items-start justify-between">
        <div><h2 className="font-mono text-sm">{fmtLat(ds.lat[i])}, {fmtLon(ds.lon[i])}</h2><p className="font-mono text-xs text-mute">cell id {ds.id[i]}</p></div>
        <button onClick={() => select(null)} aria-label="Close details" className="rounded p-1 text-mute hover:text-white"><X size={16} /></button>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-xs text-mute">Avg. temperature</dt><dd className="font-mono">{ds.temp[i].toFixed(1)} °C</dd></div>
        <div><dt className="flex items-center gap-1.5 text-xs text-mute">Avg. elevation {mocked.includes('elevation') && <Demo />}</dt><dd className="font-mono">{Math.round(ds.elev[i])} m</dd></div>
      </dl>
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
    { k: 'temp', name: 'Avg. temperature', note: ds.meta.units.temp }, { k: 'elevation', name: 'Avg. elevation', note: `Meters (${ds.meta.units.elevation})` },
    ...APPS.map((a) => ({ k: a.key as string, name: a.name, note: 'Analog label, quality and per-body scores' }))];
  return (
    <dialog ref={ref} onClose={() => set({ about: false })} className="m-auto w-[min(32rem,92vw)] rounded-lg border border-line bg-panel p-5 text-[#d7dde8]">
      <div className="flex items-center justify-between"><h2 className="text-base font-semibold">About the data</h2>
        <button onClick={() => set({ about: false })} aria-label="Close" className="text-mute hover:text-white"><X size={16} /></button></div>
      <p className="mt-2 text-sm text-mute">{ds.n.toLocaleString()} land cells on a 0.5° grid. Layers marked demo data are placeholders for the hackathon and not real measurements.</p>
      <ul className="mt-3 divide-y divide-line text-sm">
        {layers.map((l) => <li key={l.k} className="flex items-start justify-between gap-3 py-2"><div><p>{l.name}</p><p className="text-xs text-mute">{l.note}</p></div>
          {ds.meta.mocked.includes(l.k) ? <Demo /> : <span className="text-xs text-signal">real data</span>}</li>)}
      </ul>
    </dialog>);
}
