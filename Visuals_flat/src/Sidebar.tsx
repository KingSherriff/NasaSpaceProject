import { CircleDot, Car, ChevronDown, Info, ListOrdered, Mountain, PanelLeftClose, PanelLeftOpen, PersonStanding, RotateCcw } from 'lucide-react';
import { useStore, type Target } from './store';
import { APPS, LABEL_TEXT, fmtLat, fmtLon, type AppKey, type Dataset } from './data';
import type { Result } from './filter';

const ICON: Record<AppKey, typeof Car> = { spacewalk: PersonStanding, rover: Car, craters: CircleDot, cave: Mountain };
const TARGETS: { k: Target; name: string; c: string; fg: string }[] = [
  { k: 'moon', name: 'Moon', c: '#f0a500', fg: '#1a1200' }, { k: 'mars', name: 'Mars', c: '#c1440e', fg: '#fff' }, { k: 'both', name: 'Both', c: '#7b3fa0', fg: '#fff' }];

function DualRange({ label, unit, bounds, value, onChange }: { label: string; unit: string; bounds: [number, number]; value: [number, number]; onChange: (v: [number, number]) => void }) {
  const pct = (v: number) => ((v - bounds[0]) / (bounds[1] - bounds[0])) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm"><span>{label}</span>
        <span className="font-mono text-xs text-mute">{value[0]} to {value[1]} {unit}</span></div>
      <div className="dual mt-2">
        <div className="track" style={{ left: `${pct(value[0])}%`, right: `${100 - pct(value[1])}%` }} />
        <input type="range" min={bounds[0]} max={bounds[1]} step={1} value={value[0]} aria-label={`${label} minimum`}
          onChange={(e) => onChange([Math.min(+e.target.value, value[1]), value[1]])} />
        <input type="range" min={bounds[0]} max={bounds[1]} step={1} value={value[1]} aria-label={`${label} maximum`}
          onChange={(e) => onChange([value[0], Math.max(+e.target.value, value[0])])} />
      </div>
    </div>);
}

export default function Sidebar({ ds, res }: { ds: Dataset; res: Result }) {
  const s = useStore();
  return (
    <>
      {!s.sidebar && <button onClick={() => s.set({ sidebar: true })} aria-label="Open filters"
        className="fixed left-3 top-3 z-20 hidden rounded-md border border-line bg-panel/90 p-2 backdrop-blur md:block"><PanelLeftOpen size={18} /></button>}
      <aside aria-label="Filters" className={`fixed z-20 flex flex-col border-line bg-panel/92 backdrop-blur transition-transform duration-300 max-md:inset-x-0 max-md:bottom-0 max-md:max-h-[68vh] max-md:rounded-t-xl max-md:border-t md:inset-y-0 md:left-0 md:w-80 md:border-r ${s.sidebar ? 'translate-x-0 translate-y-0' : 'max-md:translate-y-[calc(100%-3.25rem)] md:-translate-x-full'}`}>
        <header className="flex items-center justify-between px-4 py-3">
          <div><h1 className="text-[15px] font-semibold leading-tight">Analog</h1>
            <p className="text-xs text-mute">NASA Space Apps 2026 · Edmonton</p></div>
          <button onClick={() => s.set({ sidebar: !s.sidebar })} aria-label={s.sidebar ? 'Collapse filters' : 'Expand filters'} aria-expanded={s.sidebar}
            className="rounded p-1.5 text-mute hover:text-white"><PanelLeftClose size={18} className="max-md:hidden" /><ChevronDown size={18} className={`md:hidden ${s.sidebar ? '' : 'rotate-180'}`} /></button>
        </header>
        <div className="flex-1 space-y-6 overflow-y-auto px-4 pb-4">
          <section aria-labelledby="f-target">
            <h2 id="f-target" className="mb-2 text-sm font-medium">Target body</h2>
            <div className="flex overflow-hidden rounded-md border border-line" role="group" aria-label="Target body, match any selected">
              {TARGETS.map((t) => { const on = s.targets.includes(t.k); return (
                <button key={t.k} aria-pressed={on} onClick={() => s.toggleTarget(t.k)}
                  style={on ? { background: t.c, color: t.fg } : undefined}
                  className="flex-1 border-r border-line py-1.5 text-sm last:border-r-0 hover:bg-white/5 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal">
                  <span className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: on ? t.fg : t.c }} />{t.name}</button>); })}
            </div>
            <p className="mt-1.5 text-xs text-mute">{s.targets.length ? 'Matches any selected body.' : 'None selected: any Moon or Mars site.'}</p>
          </section>
          <section aria-labelledby="f-app">
            <h2 id="f-app" className="mb-2 text-sm font-medium">Applications <span className="font-normal text-mute">(must match all)</span></h2>
            <div className="grid grid-cols-2 gap-2">
              {APPS.map((a) => { const I = ICON[a.key], on = s.apps.includes(a.key); return (
                <div key={a.key} className="group relative">
                  <button aria-pressed={on} aria-describedby={`tip-${a.key}`} onClick={() => s.toggleApp(a.key)}
                    className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-[13px] focus-visible:outline-2 focus-visible:outline-signal ${on ? 'border-signal bg-signal/15 text-white' : 'border-line text-mute hover:text-white'}`}>
                    <I size={16} className="shrink-0" />{a.name}</button>
                  <span id={`tip-${a.key}`} role="tooltip" className="pointer-events-none absolute inset-x-0 top-full z-30 mt-1 rounded border border-line bg-ink px-2 py-1 text-xs text-mute opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">{a.tip}</span>
                </div>); })}
            </div>
          </section>
          <DualRange label="Avg. temperature" unit="°C" bounds={s.ranges.temp} value={s.temp} onChange={s.setTemp} />
          <DualRange label="Avg. elevation" unit="m" bounds={s.ranges.elev} value={s.elev} onChange={s.setElev} />
          <div className="flex items-center justify-between">
            <button onClick={s.reset} className="flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm hover:bg-white/5"><RotateCcw size={14} />Reset filters</button>
            <button onClick={() => s.set({ about: true })} className="flex items-center gap-1.5 text-sm text-mute underline-offset-2 hover:text-white hover:underline"><Info size={14} />About the data</button>
          </div>
          <section aria-labelledby="f-top" className="border-t border-line pt-4">
            <button id="f-top" aria-expanded={s.top} onClick={() => s.set({ top: !s.top })} className="flex w-full items-center justify-between text-sm font-medium">
              <span className="flex items-center gap-2"><ListOrdered size={16} />Top sites</span><ChevronDown size={16} className={s.top ? '' : '-rotate-90'} /></button>
            {s.top && (res.top.length ? <ol className="mt-2 space-y-1">
              {res.top.map((i, r) => (
                <li key={i}><button onClick={() => s.focus(i)} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-white/5">
                  <span className="w-5 font-mono text-mute">{r + 1}</span>
                  <span className="flex-1 font-mono">{fmtLat(ds.lat[i])} {fmtLon(ds.lon[i])}</span>
                  <span className="text-mute">{LABEL_TEXT[res.label[res.idx.indexOf(i)] ?? 0]}</span>
                  <span className="font-mono">{Math.min(...s.apps.map((a) => ds.apps[a].quality[i])).toFixed(2)}</span></button></li>))}
            </ol> : <p className="mt-2 text-xs text-mute">Select at least one application to rank sites by quality.</p>)}
          </section>
        </div>
      </aside>
    </>);
}
