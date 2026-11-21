"""Moon / Mars terrain likeness of Earth cells, and Earth matches for Moon/Mars reference sites.

Terrain statistics are log-scaled, standardised on a scale shared by all bodies (each body weighted
equally), weighted, then compared by Euclidean distance; similarity = exp(-distance).
Formulas and reasons: docs/LAYER_MATH.md §12.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .common import R_EARTH_KM, FloatArray
from .filters import landcover_ok

TOPO_FEATURES: list[str] = ["slope_p50", "slope_p90", "rough_p50", "relief_p90", "hyps"]
LINEAR: set[str] = {"hyps"}  # already 0..1, not log-scaled
WEIGHTS: dict[str, float] = {"slope_p50": 1, "slope_p90": 1, "rough_p50": 1, "relief_p90": 1, "hyps": 2}
TOP_N: int = 10  # Earth matches kept per reference site
MIN_SEP_KM: float = 300  # matches for one site must be this far apart, so the list is not one cluster
K_LIKE: int = 25  # neighbours used for the Moon-/Mars-likeness score
BODIES: tuple[str, ...] = ("moon", "mars")
SCORE_COLUMNS: list[str] = ["moon_like", "mars_like", "moon_match_id", "mars_match_id"]


# ----------------------------------------------------------------------------- feature space
def log_features(df: pd.DataFrame) -> FloatArray:
    X = np.array(df[TOPO_FEATURES], dtype=float)
    k = [j for j, f in enumerate(TOPO_FEATURES) if f not in LINEAR]
    X[:, k] = np.log1p(X[:, k])
    return X


@dataclass
class TerrainSpace:
    """Shared standardisation: one scale for all bodies, each body weighted equally."""

    mu: FloatArray
    sd: FloatArray
    w: FloatArray = field(default_factory=lambda: np.sqrt([WEIGHTS.get(f, 1) for f in TOPO_FEATURES]))

    @classmethod
    def fit(cls, bodies: dict[str, pd.DataFrame]) -> TerrainSpace:
        mus = np.array([log_features(df).mean(axis=0) for df in bodies.values()])
        vrs = np.array([log_features(df).var(axis=0) for df in bodies.values()])
        mu = mus.mean(axis=0)
        sd = np.sqrt((vrs + (mus - mu) ** 2).mean(axis=0))  # variance of the equal-weight mixture
        return cls(mu, sd)

    def z(self, df: pd.DataFrame) -> FloatArray:
        return (log_features(df) - self.mu) / self.sd * self.w

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame({"log_mean": self.mu, "log_sd": self.sd}, index=TOPO_FEATURES)


def similarity(d: FloatArray | float) -> FloatArray:
    """Distance in feature space -> 0..1 score (1 = identical terrain statistics)."""
    return np.exp(-np.asarray(d))


def haversine_km(lat1, lon1, lat2, lon2):  # noqa: ANN001  (scalars or arrays)
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH_KM * np.arcsin(np.sqrt(a))


# ----------------------------------------------------------------------------- result
@dataclass
class Likeness:
    earth: pd.DataFrame  # Earth candidate cells with <body>_like, <body>_dist, <body>_match_id
    bodies: dict[str, pd.DataFrame]  # earth/moon/mars tables; moon/mars get earth_match_*
    matches: pd.DataFrame  # top Earth matches per reference site
    space: TerrainSpace
    Z: dict[str, FloatArray]


def earth_candidates(cells: pd.DataFrame) -> pd.DataFrame:
    """Land cells that pass the land-cover filters (terrain rules NOT applied) and have terrain data."""
    return cells[landcover_ok(cells)].dropna(subset=TOPO_FEATURES).reset_index(drop=True)


def _thinned_matches(
    Z_earth: FloatArray, earth: pd.DataFrame, z_target: FloatArray,
    top_n: int = TOP_N, min_sep_km: float = MIN_SEP_KM,
) -> tuple[np.ndarray, FloatArray]:
    """Closest Earth cells to one target point, thinned so no two are within min_sep_km."""
    dist = np.linalg.norm(Z_earth - z_target, axis=1)
    picked: list[int] = []
    for i in np.argsort(dist):
        if all(haversine_km(earth.lat[i], earth.lon[i], earth.lat[j], earth.lon[j]) >= min_sep_km
               for j in picked):
            picked.append(i)
            if len(picked) == top_n:
                break
    return np.array(picked), dist


def site_matches(lk_earth: pd.DataFrame, bodies: dict[str, pd.DataFrame], Z: dict[str, FloatArray],
                 sites: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for s in sites.itertuples():
        src = bodies[s.body]
        hit = np.flatnonzero(src.cell_id.values == s.cell_id)
        if len(hit) != 1:
            raise ValueError(f"{s.name}: cell {s.cell_id} not found in {s.body} table")
        z_t = Z[s.body][hit[0]]
        picked, dist = _thinned_matches(Z["earth"], lk_earth, z_t)
        for rank, i in enumerate(picked, start=1):
            row = {"body": s.body, "site": s.name, "site_cell_id": int(s.cell_id), "rank": rank,
                   "earth_cell_id": int(lk_earth.cell_id[i]), "earth_lat": lk_earth.lat[i],
                   "earth_lon": lk_earth.lon[i],
                   "site_polar": bool(src.polar.values[hit[0]]), "earth_polar": bool(lk_earth.polar[i]),
                   "distance": dist[i], "similarity": float(similarity(dist[i]))}
            for k, f in enumerate(TOPO_FEATURES):
                row[f"site_{f}"] = src[f].values[hit[0]]
                row[f"earth_{f}"] = lk_earth[f][i]
                row[f"dz_{f}"] = Z["earth"][i, k] - z_t[k]  # + = Earth cell is higher on this feature
            rows.append(row)
    return pd.DataFrame(rows)


def compute(cells: pd.DataFrame, moon: pd.DataFrame, mars: pd.DataFrame, sites: pd.DataFrame) -> Likeness:
    earth = earth_candidates(cells)
    bodies = {"earth": earth, "moon": moon.copy(), "mars": mars.copy()}
    space = TerrainSpace.fit(bodies)
    Z = {body: space.z(df) for body, df in bodies.items()}
    trees = {body: cKDTree(z) for body, z in Z.items()}

    matches = site_matches(earth, bodies, Z, sites)

    for body in BODIES:  # best Earth cell for every Moon / Mars cell
        d, i = trees["earth"].query(Z[body])
        bodies[body]["earth_match_id"] = earth.cell_id.values[i]
        bodies[body]["earth_match_dist"] = d
        bodies[body]["earth_match_sim"] = similarity(d)

    for body in BODIES:  # how Moon-/Mars-like every Earth cell is
        d, _ = trees[body].query(Z["earth"], k=K_LIKE)
        earth[f"{body}_dist"] = d.mean(axis=1)
        earth[f"{body}_like"] = similarity(earth[f"{body}_dist"])
        _, i1 = trees[body].query(Z["earth"])
        earth[f"{body}_match_id"] = bodies[body].cell_id.values[i1]

    return Likeness(earth, bodies, matches, space, Z)


def merge_into(cells: pd.DataFrame, lk: Likeness) -> pd.DataFrame:
    """Add <body>_like, <body>_match_id (NaN for non-candidates) and <body>_like_p to the cells table.

    _like_p are Earth percentiles: raw mars_like is higher than moon_like almost everywhere, so the
    percentiles keep the two bodies comparable in scoring.
    """
    out = cells.drop(columns=SCORE_COLUMNS, errors="ignore").merge(
        lk.earth[["cell_id", *SCORE_COLUMNS]], on="cell_id", how="left"
    )
    for b in BODIES:
        out[f"{b}_like_p"] = out[f"{b}_like"].rank(pct=True)
    return out


def report(lk: Likeness) -> None:
    for body in BODIES:
        d = lk.bodies[body].earth_match_dist
        q = np.percentile(d, [50, 90, 99])
        print(f"{body}: distance to best Earth cell  median {q[0]:.3f} | p90 {q[1]:.3f} | p99 {q[2]:.3f} | "
              f"{(d > 0.5).mean():.1%} of cells have no Earth cell within 0.5")
