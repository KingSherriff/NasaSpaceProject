"""Every raw-data download. Each function skips files already on disk and returns the local path(s).

NASA Earthdata (MODIS, GEDI) needs a login: earthaccess.login(persist=True) stores it in ~/.netrc.
"""

from __future__ import annotations

import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .config import ETOPO_KIND

WORLDCLIM_ZIP_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
GEDI_CONCEPT_ID = "C3043630107-ORNL_CLOUD"
ETOPO_DIR_URL = "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_{kind}_elev_gtif/"
MOON_DEM_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_PA/LDEM64_PA_gridline_202405.grd"
MARS_DEM_URL = "https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"
GVP_WFS_URL = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Impact structures on Earth from Wikidata (CC0): instances of "impact crater" (Q55818) whose
# coordinates are on Earth. Stand-in for the Earth Impact Database / Kenkmann 2021, which have no API.
CRATER_QUERY = """
SELECT ?item ?itemLabel ?lat ?lon ?diam WHERE {
  ?item wdt:P31/wdt:P279* wd:Q55818 ; p:P625/psv:P625 ?c .
  ?c wikibase:geoGlobe wd:Q2 ; wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
  OPTIONAL { ?item wdt:P2386 ?diam }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}"""


# ----------------------------------------------------------------------------- generic
def download(url: str, dest: Path) -> Path:
    """Stream url to dest; skipped if dest exists. Written to .part first, so a cut run is retried."""
    dest = Path(dest)
    if dest.exists():
        print(f"✓ already have {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"↓ downloading {dest.name} ...")
    tmp = dest.with_suffix(".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.replace(dest)
    return dest


# ----------------------------------------------------------------------------- Earth base table
def worldclim(raw: Path) -> Path:
    """WorldClim 2.1 bioclim 10' (zip, unpacked). Returns the folder."""
    out = raw / "worldclim"
    wc_zip = download(WORLDCLIM_ZIP_URL, out / "wc2.1_10m_bio.zip")
    if not (out / "wc2.1_10m_bio_1.tif").exists():
        with zipfile.ZipFile(wc_zip) as z:
            z.extractall(out)
        print("✓ unzipped WorldClim")
    return out


def modis_lc(raw: Path, year: int = 2022) -> Path:
    """MODIS MCD12C1 v061 land cover for one year (NASA Earthdata login)."""
    out = raw / "modis_lc"
    existing = sorted(out.glob("MCD12C1*.hdf"))
    if existing:
        print(f"✓ already have {existing[-1].name}")
        return existing[-1]
    import earthaccess

    out.mkdir(parents=True, exist_ok=True)
    earthaccess.login(persist=True)
    res = earthaccess.search_data(
        short_name="MCD12C1", version="061", temporal=(f"{year}-01-01", f"{year}-12-31")
    )
    path = Path(earthaccess.download(res[:1], str(out))[0])
    print(f"✓ downloaded {path.name}")
    return path


def gedi(raw: Path) -> Path:
    """GEDI gridded AGBD, full mission (2019-04-17 to 2023-03-16), 12 km (NASA Earthdata login)."""
    out = raw / "gedi"
    existing = sorted(out.glob("*agbd*20230316*12000m.tif"))
    if existing:
        print(f"✓ already have {existing[0].name}")
        return existing[0]
    import earthaccess

    out.mkdir(parents=True, exist_ok=True)
    earthaccess.login(persist=True)
    res = earthaccess.search_data(concept_id=GEDI_CONCEPT_ID)
    names = [g["umm"]["GranuleUR"] for g in res]
    want = [
        (g, n)
        for g, n in zip(res, names)
        if "_agbd-" in n and "20190417_20230316" in n and n.endswith("12000m.tif")
    ]
    want.sort(key=lambda gn: "_vf_" not in gn[1])  # prefer _vf_
    if not want:
        avail = "\n".join(n for n in names if "agbd" in n)
        raise RuntimeError(f"No matching GEDI AGBD file. Available biomass files:\n{avail}")
    print("picked:", want[0][1])
    return Path(earthaccess.download([want[0][0]], str(out))[0])


def etopo(raw: Path, kind: str = ETOPO_KIND, workers: int = 4) -> list[Path]:
    """All ETOPO 2022 15" tiles of one kind (288 tiles of 15°). Falls back to the tiles on disk offline."""
    out = raw / "etopo"
    out.mkdir(parents=True, exist_ok=True)
    url = ETOPO_DIR_URL.format(kind=kind)
    existing = sorted(out.glob(f"ETOPO_2022_v1_15s_*_{kind}.tif"))
    try:
        listing = requests.get(url, timeout=120)
        listing.raise_for_status()
        tiles = sorted(set(re.findall(r'ETOPO_2022[^"<>]*\.tif', listing.text)))
    except requests.RequestException as e:
        if not existing:
            raise
        tiles = [p.name for p in existing]
        print(f"! could not list ETOPO tiles ({type(e).__name__}), using the {len(tiles)} on disk")
    new = [n for n in tiles if not (out / n).exists()]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda n: download(url + n, out / n), new))
    print(f"✓ ETOPO: had {len(tiles) - len(new)} of {len(tiles)} tiles, downloaded {len(new)}")
    return [out / n for n in tiles]


# ----------------------------------------------------------------------------- Moon / Mars
def moon_dem(raw: Path) -> Path:
    """LOLA LDEM64 (NASA GSFC PGDA), 64 px/deg, km relative to 1737.4 km sphere."""
    return download(MOON_DEM_URL, raw / "moon" / "LDEM64_PA_gridline_202405.grd")


def mars_dem(raw: Path) -> Path:
    """MOLA MGS 463 m global mosaic (NASA / USGS), m relative to 3396.19 km sphere."""
    return download(MARS_DEM_URL, raw / "mars" / "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif")


# ----------------------------------------------------------------------------- point sources
def gvp_volcanoes(raw: Path) -> Path:
    """Smithsonian GVP Holocene volcanoes via WFS, as CSV."""
    path = raw / "gvp" / "holocene_volcanoes.csv"
    if path.exists():
        print(f"✓ already have {path.name}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        caps = requests.get(
            GVP_WFS_URL, params={"service": "WFS", "request": "GetCapabilities"}, timeout=60
        ).text
        layer_names = re.findall(r"<(?:wfs:)?Name>([^<]+)</(?:wfs:)?Name>", caps)
        holo = [n for n in layer_names if "holocene" in n.lower() and "volcan" in n.lower()]
        if not holo:
            raise RuntimeError(f"No Holocene volcano layer in the WFS; layers: {layer_names}")
        print("Using layer:", holo[0])
        r = requests.get(
            GVP_WFS_URL,
            params={"service": "WFS", "version": "1.0.0", "request": "GetFeature",
                    "typeName": holo[0], "outputFormat": "csv"},
            timeout=120,
        )
        r.raise_for_status()
        path.write_bytes(r.content)
        print(f"✓ downloaded {path.name}")

    head = path.read_text(errors="ignore")[:500]
    if head.lstrip().startswith("<"):  # the server returned an XML error, not CSV
        path.unlink()  # so the next run re-downloads
        raise RuntimeError("WFS returned XML (an error), not CSV:\n" + head)
    return path


def wikidata_craters(raw: Path) -> Path:
    path = raw / "craters" / "wikidata_impact_craters.csv"
    if path.exists():
        print(f"✓ already have {path.name}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(
        WIKIDATA_SPARQL_URL,
        params={"query": CRATER_QUERY},
        timeout=120,
        headers={"Accept": "text/csv", "User-Agent": "analog-finder-hackathon/0.1"},
    )
    r.raise_for_status()
    path.write_bytes(r.content)
    print(f"✓ downloaded {path.name}")
    return path


# ----------------------------------------------------------------------------- groups
def base_sources(raw: Path) -> None:
    """Everything the Earth base table needs."""
    worldclim(raw)
    modis_lc(raw)
    gedi(raw)
    etopo(raw)


def planet_sources(raw: Path) -> None:
    moon_dem(raw)
    mars_dem(raw)


def scoring_sources(raw: Path) -> None:
    gvp_volcanoes(raw)
    wikidata_craters(raw)


def everything(raw: Path) -> None:
    base_sources(raw)
    planet_sources(raw)
    scoring_sources(raw)
