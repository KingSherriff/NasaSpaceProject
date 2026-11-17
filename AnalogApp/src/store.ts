import { create } from 'zustand';
import type { AppKey, Meta } from './data';
export type Target = 'moon' | 'mars' | 'both';
export type Projection = 'globe' | 'flat';
export const MAP_PROJECTION: Record<Projection, 'globe' | 'mercator'> = { globe: 'globe', flat: 'mercator' };
type R = [number, number];
interface State {
  targets: Target[]; apps: AppKey[]; temp: R; elev: R; ranges: { temp: R; elev: R };
  selected: number | null; hovered: number | null; flyReq: { idx: number; t: number } | null;
  sidebar: boolean; about: boolean; top: boolean;
  site: number | null; sitesOpen: boolean; // selected Moon/Mars reference site (index into compare.sites)
  view: 'earth' | 'moon' | 'mars'; pcell: number | null; // which globe is showing, and the selected cell_id on the Moon/Mars globe
  projection: Projection; // 3D globe or flat (web-mercator) map, shared by Earth, Moon and Mars
  showOn: (body: 'moon' | 'mars', cell: number) => void; // jump to a cell on the Moon/Mars globe
  pickSite: (k: number, body: 'moon' | 'mars', cell: number) => void;
  init: (m: Meta) => void; toggleTarget: (t: Target) => void; toggleApp: (a: AppKey) => void;
  setTemp: (r: R) => void; setElev: (r: R) => void; reset: () => void;
  select: (i: number | null) => void; hover: (i: number | null) => void; focus: (i: number) => void;
  set: (p: Partial<State>) => void;
}
const tog = <T,>(a: T[], v: T) => (a.includes(v) ? a.filter((x) => x !== v) : [...a, v]);
export const useStore = create<State>((set, get) => ({
  targets: [], apps: [], temp: [-60, 40], elev: [-100, 4200], ranges: { temp: [-60, 40], elev: [-100, 4200] },
  selected: null, hovered: null, flyReq: null, sidebar: true, about: false, top: true, site: null, sitesOpen: true,
  init: (m) => {
    const t: R = [Math.floor(m.ranges.temp[0]), Math.ceil(m.ranges.temp[1])];
    const e: R = [Math.floor(m.ranges.elevation[0]), Math.ceil(m.ranges.elevation[1])];
    set({ ranges: { temp: t, elev: e }, temp: t, elev: e });
  },
  toggleTarget: (t) => set({ targets: tog(get().targets, t) }),
  toggleApp: (a) => set({ apps: tog(get().apps, a) }),
  setTemp: (temp) => set({ temp }), setElev: (elev) => set({ elev }),
  reset: () => set({ targets: [], apps: [], temp: get().ranges.temp, elev: get().ranges.elev }),
  select: (selected) => set({ selected }), hover: (hovered) => set({ hovered }),
  focus: (idx) => set({ view: 'earth', selected: idx, flyReq: { idx, t: Date.now() } }),
  view: 'earth', pcell: null, projection: 'globe',
  showOn: (body, cell) => set({ view: body, pcell: cell }),
  // toggles the site; on Earth the view stays put (pins appear), on a Moon/Mars globe it jumps to the site itself
  pickSite: (k, body, cell) => { const s = get();
    if (s.site === k) set({ site: null }); else if (s.view === 'earth') set({ site: k }); else set({ site: k, view: body, pcell: cell }); },
  set: (p) => set(p),
}));
