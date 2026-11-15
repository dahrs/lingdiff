"""Downloads raw source dumps into data/sources/raw/, skipping files already present so
reruns are cheap. Nothing in here is parsed/interpreted — that's build_profile.py's job."""

from __future__ import annotations

from pathlib import Path

import requests

_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "sources" / "raw"

_SOURCES: dict[str, str] = {
    "wals_languages.csv": "https://raw.githubusercontent.com/cldf-datasets/wals/master/cldf/languages.csv",
    "wals_values.csv": "https://raw.githubusercontent.com/cldf-datasets/wals/master/cldf/values.csv",
    "wals_parameters.csv": "https://raw.githubusercontent.com/cldf-datasets/wals/master/cldf/parameters.csv",
    "wals_codes.csv": "https://raw.githubusercontent.com/cldf-datasets/wals/master/cldf/codes.csv",
    "phoible.csv": "https://raw.githubusercontent.com/phoible/dev/master/data/phoible.csv",
    "glottolog_geo.csv": "https://cdstar.eva.mpg.de/bitstreams/EAEA0-E62D-ED67-FD05-0/languages_and_dialects_geo.csv",
}


def fetch_all(force: bool = False) -> dict[str, Path]:
    """Downloads every source listed in _SOURCES, returns {name: local_path}."""
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, url in _SOURCES.items():
        dest = _RAW_DIR / name
        if dest.exists() and not force:
            paths[name] = dest
            continue
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        dest.write_bytes(response.content)
        paths[name] = dest
    return paths


if __name__ == "__main__":
    fetched = fetch_all()
    for fetched_name, fetched_path in fetched.items():
        size_kb = fetched_path.stat().st_size // 1024
        print(f"{fetched_name}: {size_kb} KB -> {fetched_path}")
