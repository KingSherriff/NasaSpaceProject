"""Application 3: spacewalk / EVA.

Gate: land-cover screening + open ground (barren >= 30 %).
Site: walkable in a suit -> slope_p90 <= 15° (screening slope rule).
Moon: large temperature swings (BIO7 annual range), dry, bare, high (thin air / radiation proxy).
Mars: very dry first (driest 10 % of Earth), then high elevation (low pressure), cool, bare,
some temperature swing.
"""

from ..filters import landcover_ok
from .core import Application

BARREN_MIN = 0.30

SPACEWALK = Application(
    name="spacewalk",
    gate=lambda df: landcover_ok(df) & (df.barren >= BARREN_MIN),
    site=lambda df: df.pass_slope,
    profiles={
        "moon": {"target":  {"temp_range_p": 0.90,  "precip_p": 0.20,  "barren": 1.0,   "elev_p": 0.80},
                 "weights": {"temp_range_p": 2,     "precip_p": 1,     "barren": 1,     "elev_p": 1},
                 "dir":     {"temp_range_p": "min", "precip_p": "max", "barren": "min", "elev_p": "min"}},
        "mars": {"target":  {"temp_p": 0.40,  "elev_p": 0.80,  "precip_p": 0.10,  "barren": 1.0,   "temp_range_p": 0.70},
                 "weights": {"temp_p": 1,     "elev_p": 1.5,   "precip_p": 2,     "barren": 1,     "temp_range_p": 0.5},
                 "dir":     {"temp_p": "max", "elev_p": "min", "precip_p": "max", "barren": "min", "temp_range_p": "min"}},
    },
    show=["temp_range_p", "temp_p", "elev_p", "precip_p", "barren"],
    requires=["temp_range_p", "elev_p", "pass_slope"],
)
