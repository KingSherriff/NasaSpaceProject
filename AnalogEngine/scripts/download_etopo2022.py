"""Download all ETOPO 2022 15 arc-second bedrock elevation GeoTIFF tiles from NOAA NGDC.

Usage: python scripts/download_etopo2022.py [output_dir] [--workers N]
Existing files with the expected size are skipped, so it is safe to re-run.
"""
import argparse
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_URL = "https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/15s/15s_bed_elev_gtif/"


def list_tiles():
    with urllib.request.urlopen(BASE_URL) as resp:
        html = resp.read().decode()
    return sorted(set(re.findall(r'ETOPO_2022[^"<>]*\.tif', html)))


def download(name, out_dir):
    dest = out_dir / name
    url = BASE_URL + name
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as resp:
        size = int(resp.headers["Content-Length"])
    if dest.exists() and dest.stat().st_size == size:
        return f"skip  {name}"
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    return f"done  {name}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", nargs="?", default="data", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tiles = list_tiles()
    print(f"{len(tiles)} tiles -> {args.output_dir}")
    with ThreadPoolExecutor(args.workers) as pool:
        for msg in pool.map(lambda n: download(n, args.output_dir), tiles):
            print(msg)


if __name__ == "__main__":
    main()
