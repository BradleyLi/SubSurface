#!/usr/bin/env python3
"""
Downloads and prepares Toronto watermain ML training data
into the exact structure expected by build_structured_parquet.py.

Output structure:
.data/
 ├── distribution.geojson
 ├── transmission.geojson
 ├── tree.geojson
 └── watermain-break/
      ├── Breaks_1990_2016_wgs84.shp (+ associated files)
"""

import os
from pathlib import Path
import requests
import zipfile
import io

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / ".data"
BREAK_DIR = DATA_DIR / "watermain-break"

DATA_DIR.mkdir(exist_ok=True, parents=True)
BREAK_DIR.mkdir(exist_ok=True, parents=True)


FILES = {
    "distribution.geojson": "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/4e0989b8-57b9-4629-a5bd-cc672f537593/resource/172419f6-88b6-4cf8-bcc5-5a3aa860e1f8/download/Distribution%20Watermain%20-%204326.geojson",
    "transmission.geojson": "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/4e0989b8-57b9-4629-a5bd-cc672f537593/resource/fefc080e-db94-4b0e-8231-818805fc6157/download/Transmission%20Watermain%20-%204326.geojson",
    "tree.geojson": "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/6ac4569e-fd37-4cbc-ac63-db3624c5f6a2/resource/d6089672-bdf7-4857-8ea8-90da826fcfa1/download/Street%20Tree%20Data%20-%204326.geojson",
}

BREAKS_ZIP = "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/c1339013-2f0f-4a5a-8233-625daef69102/resource/bd587c6a-3de6-4a7d-a743-7d6ed955197d/download/watermain-breaks-1990-to-2016-wgs84.zip"


def download_file(url: str, out_path: Path):
    print(f"Downloading {out_path.name} ...")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()

    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)


def download_geojsons():
    for name, url in FILES.items():
        out_path = DATA_DIR / name
        if out_path.exists():
            print(f"Skipping {name} (already exists)")
            continue
        download_file(url, out_path)


def download_and_extract_breaks():
    print("Downloading watermain breaks zip ...")
    r = requests.get(BREAKS_ZIP, stream=True, timeout=120)
    r.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(r.content))

    print("Extracting breaks shapefile ...")
    z.extractall(BREAK_DIR)

    # Find the shapefile and standardize path expectation
    shp_files = list(BREAK_DIR.rglob("*.shp"))
    if not shp_files:
        raise RuntimeError("No .shp file found in extracted breaks archive")

    # Move/canonicalize into expected name
    shp = shp_files[0]
    target_base = BREAK_DIR / "Breaks_1990_2016_wgs84"

    for ext in [".shp", ".dbf", ".shx", ".prj", ".cpg", ".qix", ".fix"]:
        for f in BREAK_DIR.rglob(f"*{ext}"):
            f.rename(target_base.with_suffix(ext))

    print("Breaks extracted to:", target_base.with_suffix(".shp"))


def main():
    print("\n=== Downloading GeoJSON layers ===")
    download_geojsons()

    print("\n=== Downloading and extracting breaks ===")
    download_and_extract_breaks()

    print("\nDone. Data ready in .data/")


if __name__ == "__main__":
    main()