"""Application 2: rover testing.

Gate: land-cover screening + mostly bare ground (barren >= 50 %).
Site: a rover can drive it -> passes the terrain rules (slope_p90 <= 15°, rough_p10 <= 15 m).
Moon / Mars: how close the terrain statistics are to the real Moon / Mars DEMs (moon_like_p /
mars_like_p), plus dryness and bare ground.
Mars: stricter dryness (driest 10 % of Earth, double weight) and cooler than the warmest 60 %.
Sand (ASTER GED emissivity) is not in yet.
"""

from ..filters import landcover_ok
from .core import Application

BARREN_MIN = 0.50

ROVER = Application(
    name="rover",
    gate=lambda df: landcover_ok(df) & (df.barren >= BARREN_MIN),
    site=lambda df: df.pass_slope & df.pass_rough,
    profiles={
        "moon": {"target":  {"moon_like_p": 0.90,  "precip_p": 0.20,  "barren": 1.0},
                 "weights": {"moon_like_p": 3,     "precip_p": 1,     "barren": 1},
                 "dir":     {"moon_like_p": "min", "precip_p": "max", "barren": "min"}},
        "mars": {"target":  {"mars_like_p": 0.90,  "precip_p": 0.10,  "barren": 1.0,   "temp_p": 0.40},
                 "weights": {"mars_like_p": 3,     "precip_p": 2,     "barren": 1,     "temp_p": 1},
                 "dir":     {"mars_like_p": "min", "precip_p": "max", "barren": "min", "temp_p": "max"}},
    },
    show=["moon_like_p", "mars_like_p", "precip_p", "temp_p", "barren", "slope_p90"],
    requires=["moon_like_p", "mars_like_p", "pass_slope", "pass_rough"],
)
