import { useEffect, useMemo, useState } from 'react';
import { loadData, type Dataset } from './data';
import { computeFilter } from './filter';
import { useStore } from './store';
import MapView from './MapView';
import Sidebar from './Sidebar';
import { AboutModal, DetailCard, Legend } from './Panels';

export default function App() {
  const [ds, setDs] = useState<Dataset | null>(null);
  const [err, setErr] = useState('');
  const { targets, apps, temp, elev, init } = useStore();
  useEffect(() => { loadData(`${import.meta.env.BASE_URL}data/frontend_cells.json`).then((d) => { init(d.meta); setDs(d); }).catch((e) => setErr(String(e))); }, [init]);
  const res = useMemo(() => (ds ? computeFilter(ds, targets, apps, temp, elev) : null), [ds, targets, apps, temp, elev]);
  if (err) return <p className="p-6 text-red-400">Could not load data: {err}</p>;
  if (!ds || !res) return <div className="grid h-full place-items-center font-mono text-sm text-mute">Loading cells…</div>;
  return (<>
    <MapView ds={ds} res={res} />
    <Sidebar ds={ds} res={res} />
    <Legend ds={ds} res={res} />
    <DetailCard ds={ds} />
    <AboutModal ds={ds} />
  </>);
}
