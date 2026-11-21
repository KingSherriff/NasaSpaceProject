"""Paths and settings shared by every pipeline step.

Paths are absolute and built from this file's location, so they work from any working folder
(relative ../data paths broke once when a notebook's folder disappeared).
"""

from __future__ import annotations

from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[1]  # AnalogEngine/
RAW: Path = ROOT / "data" / "raw"
PROCESSED: Path = ROOT / "data" / "processed"
FRONT: Path = ROOT / "public" / "data"

CELL_SIZE: float = 0.5
ETOPO_KIND: str = "surface"  # "surface" or "bed"; download, base table and planets all use this
POLAR_LAT: float = 75  # |lat| above this = wedge-shaped cells, lower confidence


def ensure_dirs() -> None:
    for d in (RAW, PROCESSED, FRONT):
        d.mkdir(parents=True, exist_ok=True)
