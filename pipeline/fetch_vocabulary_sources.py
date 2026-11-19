"""Downloads the raw sources behind vocabulary-origin data (see pipeline/vocabulary_origin.py)
into data/sources/raw/, skipping files already present. Kept separate from fetch_sources.py's
fetch_all() — those run on every pipeline invocation, including quick ones that have nothing
to do with vocabulary origin, and etymology-db's CSV alone is ~650MB; no reason to make every
run check for it.

**etymology-db's real distribution channel (a OneDrive share link off its GitHub README)
doesn't support plain HTTP download** — confirmed live: redirects to onedrive.live.com and
then 403s a non-browser request. Using the community-maintained Hugging Face mirror
(huggingface.co/datasets/Nickmancol/etymology) instead, which serves the same CC BY-SA 3.0
data over a normal, ungated HTTPS download.
"""

from __future__ import annotations

from pathlib import Path

import requests

_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "sources" / "raw"

_SOURCES: dict[str, str] = {
    "wold_languages.csv": "https://raw.githubusercontent.com/lexibank/wold/master/cldf/languages.csv",
    "wold_forms.csv": "https://raw.githubusercontent.com/lexibank/wold/master/cldf/forms.csv",
    "wold_borrowings.csv": "https://raw.githubusercontent.com/lexibank/wold/master/cldf/borrowings.csv",
    # SIL's official ISO 639-3 code tables — used only to map etymology-db's "lang"/
    # "related_lang" free-text language NAMES to ISO 639-3 (via each name's Wiktionary code,
    # then that code's ISO 639-1<->639-3 equivalence here) — see etymology_db_loader.py.
    "iso639-3.tab": "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab",
    "iso639-3-macrolanguages.tab": "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3-macrolanguages.tab",
    "wiktionary_codes.csv": "https://raw.githubusercontent.com/droher/etymology-db/master/wiktionary_codes.csv",
    "etymology_db.csv": "https://huggingface.co/datasets/Nickmancol/etymology/resolve/main/etymology.csv",
}


def fetch_all(force: bool = False) -> dict[str, Path]:
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, url in _SOURCES.items():
        dest = _RAW_DIR / name
        if dest.exists() and not force:
            paths[name] = dest
            continue
        response = requests.get(url, timeout=600)
        response.raise_for_status()
        dest.write_bytes(response.content)
        paths[name] = dest
    return paths


if __name__ == "__main__":
    fetched = fetch_all()
    for fetched_name, fetched_path in fetched.items():
        size_mb = fetched_path.stat().st_size / (1024 * 1024)
        print(f"{fetched_name}: {size_mb:.1f} MB -> {fetched_path}")
