#!/usr/bin/env python3
"""Build static parquet: watermain geometry joined with ML break-risk predictions."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_predictions import build_enriched_pipes_cache, enriched_pipes_path


def main() -> int:
    print("Joining watermain GeoJSON with ML predictions…")
    out = build_enriched_pipes_cache(max_dist=None, prediction_year=2016)
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"Wrote {out} ({size_mb:.1f} MB)")
    print(f"App will load from {enriched_pipes_path()} on next start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
