"""Loads Glottolog's lightweight geography CSV (fetch_sources.py's output)."""

from __future__ import annotations

import csv
from pathlib import Path


class GlottologGeoData:
    def __init__(self, raw_dir: Path) -> None:
        self._by_glottocode: dict[str, dict[str, str]] = {}
        with (raw_dir / "glottolog_geo.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self._by_glottocode[row["glottocode"]] = row

    def lookup(self, glottocode: str) -> dict[str, str] | None:
        return self._by_glottocode.get(glottocode)
