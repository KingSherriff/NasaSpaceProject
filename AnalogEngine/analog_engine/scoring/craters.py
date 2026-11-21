"""Application 4: craters.

Gate: land-cover screening (a crater under forest, a city or a lake is not an exposed analog)
+ impact structure within 100 km. Site: within 50 km (crater in or next to the cell).
Terrain rules are not applied: crater rims are steep by nature.
Profiles follow the caves: proximity first, then dryness and bare ground (preserved, visible
morphology); Mars is stricter on dryness (driest 10 %, double weight) and adds cool climate.
"""

from ..filters import landcover_ok
from .core import Application

GATE_KM = 100
SITE_KM = 50

CRATERS = Application(
    name="craters",
    gate=lambda df: landcover_ok(df) & (df.dist_crater_km <= GATE_KM),
    site=lambda df: df.dist_crater_km <= SITE_KM,
    profiles={
        "moon": {"target":  {"crater_prox": 1.0,   "precip_p": 0.20,  "barren": 1.0},
                 "weights": {"crater_prox": 3,     "precip_p": 1,     "barren": 1},
                 "dir":     {"crater_prox": "min", "precip_p": "max", "barren": "min"}},
        "mars": {"target":  {"crater_prox": 1.0,   "precip_p": 0.10,  "temp_p": 0.40,  "barren": 1.0},
                 "weights": {"crater_prox": 3,     "precip_p": 2,     "temp_p": 1,     "barren": 1},
                 "dir":     {"crater_prox": "min", "precip_p": "max", "temp_p": "max", "barren": "min"}},
    },
    show=["dist_crater_km", "precip_p", "temp_p", "barren"],
    requires=["dist_crater_km", "crater_prox"],
)
