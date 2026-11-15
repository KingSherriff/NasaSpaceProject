import { create } from 'zustand';
import type { AppKey, Meta } from './data';
export type Target = 'moon' | 'mars' | 'both';
type R = [number, number];
interface State {
  targets: Target[]; apps: AppKey[]; temp: R; elev: R; ranges: { temp: R; elev: R };
  selected: number | null; hovered: number | null; flyReq: { idx: number; t: number } | null;
  sidebar: boolean; about: boolean; top: boolean;
  init: (m: Meta) => void; toggleTarget: (t: Target) => void; toggleApp: (a: AppKey) => void;
  setTemp: (r: R) => void; setElev: (r: R) => void; reset: () => void;
  select: (i: number | null) => void; hover: (i: number | null) => void; focus: (i: number) => void;
  set: (p: Partial<State>) => void;
}
const tog = <T,>(a: T[], v: T) => (a.includes(v) ? a.filter((x) => x !== v) : [...a, v]);
export const useStore = create<State>((set, get) => ({
  targets: [], apps: [], temp: [-60, 40], elev: [-100, 4200], ranges: { temp: [-60, 40], elev: [-100, 4200] },
  selected: null, hovered: null, flyReq: null, sidebar: true, about: false, top: true,
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
  focus: (idx) => set({ selected: idx, flyReq: { idx, t: Date.now() } }),
  set: (p) => set(p),
}));
