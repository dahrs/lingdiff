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

# Script-family-name -> script-type, matched as a substring of Wikidata's label rather than
# requiring the full phrase: Wikidata labels a script as "<family> script" OR "<family>
# alphabet" inconsistently even for the same family (confirmed live: Levantine Arabic
# "Arabic alphabet" vs Egyptian Arabic "Arabic script", both really the Arabic abjad) — the
# generic suffix word never indicates type, only the family name does. Not exhaustive —
# anything not listed here falls back to "other".
_SCRIPT_FAMILY_TYPES: dict[str, str] = {
    "latin": "alphabet",
    "cyrillic": "alphabet",
    "greek": "alphabet",
    "armenian": "alphabet",
    "georgian": "alphabet",
    "hangul": "alphabet",
    "arabic": "abjad",
    "hebrew": "abjad",
    "devanagari": "abugida",
    "thai": "abugida",
    "ge'ez": "abugida",
    "ethiopic": "abugida",
    "tamil": "abugida",
    "bengali": "abugida",
    "han": "logographic",
    "chinese": "logographic",
    "kanji": "logographic",
    "hiragana": "syllabary",
    "katakana": "syllabary",
    "kana": "syllabary",
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
        this language, deduped (Wikidata sometimes carries the same label on more than one
        statement — confirmed live: Levantine Arabic's writing systems included "Arabic
        alphabet" twice), [] if none found (confirmed, or the query failed this run — a
        failed query is NOT written to cache, so it's retried on the next pipeline run
        instead of being permanently baked in as "no data" — see wikidata_sparql.py)."""
        if iso639_3 in self._cache:
            return _dedupe(self._cache[iso639_3])

        values = _query_property(iso639_3, self._property_id)
        time.sleep(_REQUEST_DELAY_SECONDS)
        if values is None:
            return []
        self._cache[iso639_3] = values
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))
        return _dedupe(values)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def script_type_for(script_name: str) -> str:
    lowered = script_name.lower()
    if "chat alphabet" in lowered or "chat alphbet" in lowered:
        # An informal Latin-based romanization scheme for digital writing (e.g. "Arabic chat
        # alphabet"/Arabizi) — the family-name substring match below would otherwise classify
        # this as the family's native script type (e.g. "arabic" -> abjad), which is wrong:
        # it's specifically NOT written in that script, that's the whole point of a chat
        # alphabet. Checked before the substring match for exactly this reason.
        return "alphabet"
    for family, script_type in _SCRIPT_FAMILY_TYPES.items():
        if family in lowered:
            return script_type
    return "other"


def _query_property(iso639_3: str, property_id: str) -> list[str] | None:
    pattern = f'?entity wdt:{property_id} ?val . SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}'
    bindings = query_with_macrolanguage_fallback(iso639_3, pattern, select_var="valLabel", limit=30)
    if bindings is None:
        return None
    return [b["valLabel"]["value"] for b in bindings]
