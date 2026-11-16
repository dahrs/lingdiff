"""Wikidata SPARQL lookups — used only as a fallback for writing-system data when WALS's
sparse "Writing Systems" chapter has no entry for a language (see build_profile.py). Results
are cached to data/sources/raw/wikidata_cache.json so reruns don't re-query."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_ENDPOINT = "https://query.wikidata.org/sparql"
_USER_AGENT = "lingdiff-pipeline/0.1 (https://github.com/dahrs/lingdiff)"
_REQUEST_DELAY_SECONDS = 1.0

# Best-effort script-name -> script-type mapping for Wikidata's common script labels.
# Not exhaustive — anything not listed here falls back to "other".
_SCRIPT_TYPES: dict[str, str] = {
    "latin script": "alphabet",
    "cyrillic script": "alphabet",
    "greek script": "alphabet",
    "armenian script": "alphabet",
    "georgian script": "alphabet",
    "hangul": "alphabet",
    "arabic script": "abjad",
    "hebrew script": "abjad",
    "devanagari": "abugida",
    "thai script": "abugida",
    "ge'ez script": "abugida",
    "ethiopic script": "abugida",
    "tamil script": "abugida",
    "bengali-assamese script": "abugida",
    "han script": "logographic",
    "chinese characters": "logographic",
    "hiragana": "syllabary",
    "katakana": "syllabary",
}


class WikidataWritingSystemCache:
    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._cache: dict[str, list[str]] = {}
        if cache_path.exists():
            self._cache = json.loads(cache_path.read_text())

    def get_scripts(self, iso639_3: str) -> list[str]:
        """Returns script names (e.g. ["Latin script"]) for this language, [] if none found."""
        if iso639_3 in self._cache:
            return self._cache[iso639_3]

        scripts = _query_scripts(iso639_3)
        self._cache[iso639_3] = scripts
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))
        time.sleep(_REQUEST_DELAY_SECONDS)
        return scripts


def script_type_for(script_name: str) -> str:
    return _SCRIPT_TYPES.get(script_name.lower(), "other")


def _query_scripts(iso639_3: str) -> list[str]:
    query = f"""
    SELECT ?scriptLabel WHERE {{
      ?lang wdt:P220 "{iso639_3}" .
      ?lang wdt:P282 ?script .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    try:
        response = requests.get(
            _ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException:
        log.warning("Wikidata query failed for %s", iso639_3, exc_info=True)
        return []
    bindings = response.json()["results"]["bindings"]
    return [b["scriptLabel"]["value"] for b in bindings]
