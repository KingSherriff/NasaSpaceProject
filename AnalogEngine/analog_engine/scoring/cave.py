"""Application 1: cave exploration (lava tubes).

Gate: forest + urban screening + basaltic volcano within 100 km.
Water is ignored for caves: nearby ocean doesn't affect a lava tube underground (keeps island sites
like Lanzarote). Terrain rules are ignored too: lava fields are rough.
Site: basaltic volcano within 50 km (in or next to the cell).
Mars profile is cold-led (v1): surface dryness matters less underground.
"""

from .core import Application

GATE_KM = 100
SITE_KM = 50

CAVE = Application(
    name="cave",
    gate=lambda df: df.pass_forest & df.pass_urban & (df.dist_basalt_volc_km <= GATE_KM),
    site=lambda df: df.dist_basalt_volc_km <= SITE_KM,
    profiles={
        "moon": {"target":  {"volc_prox": 1.0,   "precip_p": 0.20,  "barren": 1.0},
                 "weights": {"volc_prox": 3,     "precip_p": 1,     "barren": 0.5},
                 "dir":     {"volc_prox": "min", "precip_p": "max", "barren": "min"}},
        "mars": {"target":  {"volc_prox": 1.0,   "precip_p": 0.20,  "temp_p": 0.10,  "barren": 1.0},
                 "weights": {"volc_prox": 3,     "precip_p": 1,     "temp_p": 2,     "barren": 0.5},
                 "dir":     {"volc_prox": "min", "precip_p": "max", "temp_p": "max", "barren": "min"}},
    },
    show=["dist_basalt_volc_km", "precip_p", "temp_p", "barren"],
    requires=["dist_basalt_volc_km", "volc_prox"],
)
