import { useEffect, useMemo, useState } from 'react';
import { Globe, Map as MapIcon } from 'lucide-react';
import { BODY_COLOR, BODY_NAME, loadCompare, loadData, type Body, type Compare, type Dataset } from './data';
import PlanetView from './PlanetView';
import { computeFilter } from './filter';
import { useStore } from './store';
import MapView from './MapView';
import Sidebar from './Sidebar';
import { AboutModal, DetailCard, Legend } from './Panels';

const GROUP = 'flex overflow-hidden rounded-md border border-line bg-panel/90 backdrop-blur';
const btn = (on: boolean) => `flex items-center gap-1.5 border-r border-line px-3 py-1.5 text-sm last:border-r-0 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal ${on ? 'bg-white/10 text-white' : 'text-mute hover:text-white'}`;

export default function App() {
  const [ds, setDs] = useState<Dataset | null>(null);
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [err, setErr] = useState('');
  const { targets, apps, temp, elev, init, view, projection, set: setState } = useStore();
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
    <div className="fixed left-1/2 top-3 z-20 flex -translate-x-1/2 gap-2 md:left-[calc(50%+10rem)]">
      {cmp && <div role="group" aria-label="Choose a globe" className={GROUP}>
        {(['earth', 'moon', 'mars'] as const).map((v) => (
          <button key={v} aria-pressed={view === v} onClick={() => setState({ view: v, pcell: null })} className={btn(view === v)}>
            <span className="size-2 rounded-full" style={{ background: v === 'earth' ? '#5eead4' : BODY_COLOR[v] }} />{v === 'earth' ? 'Earth' : BODY_NAME[v]}</button>))}
      </div>}
      <div role="group" aria-label="Map projection" className={GROUP}>
        {([['globe', 'Globe', Globe], ['flat', 'Flat', MapIcon]] as const).map(([p, name, Icon]) => (
          <button key={p} aria-pressed={projection === p} onClick={() => setState({ projection: p })} className={btn(projection === p)}>
            <Icon size={14} aria-hidden />{name}</button>))}
      </div>
    </div>
    {onEarth && <Legend ds={ds} res={res} />}
    {onEarth && <DetailCard ds={ds} cmp={cmp} />}
    <AboutModal ds={ds} />
  </>);
}
