import { useEffect, useMemo, useState } from 'react';
import { BODY_COLOR, BODY_NAME, loadCompare, loadData, type Body, type Compare, type Dataset } from './data';
import PlanetView from './PlanetView';
import { computeFilter } from './filter';
import { useStore } from './store';
import MapView from './MapView';
import Sidebar from './Sidebar';
import { AboutModal, DetailCard, Legend } from './Panels';

export default function App() {
  const [ds, setDs] = useState<Dataset | null>(null);
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [err, setErr] = useState('');
  const { targets, apps, temp, elev, init, view, set: setState } = useStore();
  useEffect(() => {
    const base = `${import.meta.env.BASE_URL}data/`;
    loadData(`${base}frontend_cells.json`).then((d) => {
      init(d.meta); setDs(d);
      // the comparison layer is optional: the map still works if compare.json has not been exported
      loadCompare(`${base}compare.json`, d).then(setCmp).catch((e) => console.warn('Moon/Mars comparison unavailable:', e));
    }).catch((e) => setErr(String(e)));
  }, [init]);
  const res = useMemo(() => (ds ? computeFilter(ds, targets, apps, temp, elev) : null), [ds, targets, apps, temp, elev]);
  if (err) return <p className="p-6 text-red-400">Could not load data: {err}</p>;
  if (!ds || !res) return <div className="grid h-full place-items-center font-mono text-sm text-mute">Loading cells…</div>;
  const onEarth = view === 'earth' || !cmp;
  return (<>
    {/* the Earth globe stays mounted (just hidden) so it keeps its position and pins while you look at the Moon or Mars */}
    <MapView ds={ds} res={res} cmp={cmp} hidden={!onEarth} />
    {!onEarth && cmp && <PlanetView key={view} body={view as Body} cmp={cmp} ds={ds} />}
    <Sidebar ds={ds} res={res} cmp={cmp} />
    {cmp && <div role="group" aria-label="Choose a globe" className="fixed left-1/2 top-3 z-20 flex -translate-x-1/2 overflow-hidden rounded-md border border-line bg-panel/90 backdrop-blur md:left-[calc(50%+10rem)]">
      {(['earth', 'moon', 'mars'] as const).map((v) => (
        <button key={v} aria-pressed={view === v} onClick={() => setState({ view: v, pcell: null })}
          className={`flex items-center gap-1.5 border-r border-line px-3 py-1.5 text-sm last:border-r-0 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal ${view === v ? 'bg-white/10 text-white' : 'text-mute hover:text-white'}`}>
          <span className="size-2 rounded-full" style={{ background: v === 'earth' ? '#5eead4' : BODY_COLOR[v] }} />{v === 'earth' ? 'Earth' : BODY_NAME[v]}</button>))}
    </div>}
    {onEarth && <Legend ds={ds} res={res} />}
    {onEarth && <DetailCard ds={ds} cmp={cmp} />}
    <AboutModal ds={ds} />
  </>);
}
