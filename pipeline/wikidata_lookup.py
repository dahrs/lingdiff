"""Wikidata SPARQL lookups for data neither WALS nor PHOIBLE cover directly: writing system
(fallback when WALS's sparse "Writing Systems" chapter has no entry), and real named
enumerations of grammatical case/tense/mood/aspect (Wikidata has dedicated properties for
these — confirmed live: German correctly returns its 4 cases via P2989, Finnish its 15).
Each property kind gets its own cache file under data/sources/raw/, independently resumable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from pipeline.wikidata_sparql import query_with_macrolanguage_fallback

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

# property_kind -> Wikidata property ID
_PROPERTIES: dict[str, str] = {
    "writing_system": "P282",
    "grammatical_case": "P2989",
    "tense": "P3103",
    "mood": "P3161",
    "aspect": "P7486",
}


class WikidataPropertyCache:
    """One cache file per property kind (e.g. data/sources/raw/wikidata_tense.json)."""

    def __init__(self, cache_dir: Path, property_kind: str) -> None:
        if property_kind not in _PROPERTIES:
            raise ValueError(f"unknown Wikidata property kind: {property_kind}")
        self._property_id = _PROPERTIES[property_kind]
        self._cache_path = cache_dir / f"wikidata_{property_kind}.json"
        self._cache: dict[str, list[str]] = {}
        if self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text())

    def get(self, iso639_3: str) -> list[str]:
        """Returns the named values (e.g. ["nominative case", "accusative case", ...]) for
        this language, [] if none found (confirmed, or the query failed this run — a failed
        query is NOT written to cache, so it's retried on the next pipeline run instead of
        being permanently baked in as "no data" — see wikidata_sparql.py)."""
        if iso639_3 in self._cache:
            return self._cache[iso639_3]

        values = _query_property(iso639_3, self._property_id)
        time.sleep(_REQUEST_DELAY_SECONDS)
        if values is None:
            return []
        self._cache[iso639_3] = values
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))
        return values


def script_type_for(script_name: str) -> str:
    return _SCRIPT_TYPES.get(script_name.lower(), "other")


def _query_property(iso639_3: str, property_id: str) -> list[str] | None:
    pattern = f'?entity wdt:{property_id} ?val . SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}'
    bindings = query_with_macrolanguage_fallback(iso639_3, pattern, select_var="valLabel", limit=30)
    if bindings is None:
        return None
    return [b["valLabel"]["value"] for b in bindings]
