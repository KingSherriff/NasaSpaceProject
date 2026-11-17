import type { AppKey, Dataset } from './data';
import type { Target } from './store';
export interface Result { n: number; idx: Uint32Array; label: Uint8Array; q: Float32Array; match: Uint8Array; top: number[] }
export function computeFilter(ds: Dataset, targets: Target[], apps: AppKey[], temp: [number, number], elev: [number, number]): Result {
  // label -> passes? (none selected = any site; several = match any)
  const ok = [false, false, false, false];
  for (let l = 1; l < 4; l++)
    ok[l] = targets.length === 0 || targets.some((t) => (t === 'moon' ? (l & 1) !== 0 : t === 'mars' ? (l & 2) !== 0 : l === 3));
  const idx = new Uint32Array(ds.n), label = new Uint8Array(ds.n), q = new Float32Array(ds.n), match = new Uint8Array(ds.n);
  const A = apps.map((a) => ds.apps[a]);
  const top: number[] = [], topQ: number[] = [];
  let n = 0;
  for (let i = 0; i < ds.n; i++) {
    const t = ds.temp[i], e = ds.elev[i];
    if (t < temp[0] || t > temp[1] || e < elev[0] || e > elev[1]) continue;
    let and = 3, or = 0, mq = A.length ? 1 : 0.5, pass = true;
    for (let k = 0; k < A.length; k++) {
      const l = A[k].label[i];
      if (!ok[l]) { pass = false; break; }
      and &= l; or |= l;
      if (A[k].quality[i] < mq) mq = A[k].quality[i];
    }
    if (!pass) continue;
    idx[n] = i; label[n] = A.length ? and || or : 0; q[n] = mq; match[i] = 1; n++;
    if (A.length && (top.length < 10 || mq > topQ[topQ.length - 1])) {
      let p = topQ.length;
      while (p > 0 && topQ[p - 1] < mq) p--;
      top.splice(p, 0, i); topQ.splice(p, 0, mq);
      if (top.length > 10) { top.pop(); topQ.pop(); }
    }
  }
  return { n, idx, label, q, match, top };
}
