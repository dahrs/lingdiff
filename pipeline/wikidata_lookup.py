"""Wikidata SPARQL lookups for data neither WALS nor PHOIBLE cover directly: writing system
(fallback when WALS's sparse "Writing Systems" chapter has no entry), and real named
enumerations of grammatical case/tense/mood/aspect (Wikidata has dedicated properties for
these — confirmed live: German correctly returns its 4 cases via P2989, Finnish its 15).

All five properties are fetched in ONE combined query per language (see
WikidataGrammarCache) rather than five separate ones — confirmed live, a ~5x reduction in
Wikidata requests per language, which matters once building thousands of profiles rather than
a couple dozen even though it made no visible difference at draft scale.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from pipeline.wikidata_sparql import query_multi_with_macrolanguage_fallback

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

# property_kind -> Wikidata property ID. Order matters only for readability of the generated
# query; dict iteration order is used to build both the pattern and the cache shape.
_PROPERTIES: dict[str, str] = {
    "writing_system": "P282",
    "grammatical_case": "P2989",
    "tense": "P3103",
    "mood": "P3161",
    "aspect": "P7486",
}

# Legacy per-property cache filenames from before the combined query existed — migrated in on
# first load (see WikidataGrammarCache._migrate_legacy_caches) so already-fetched data isn't
# re-queried just because the storage format changed.
_LEGACY_CACHE_FILENAMES: dict[str, str] = {kind: f"wikidata_{kind}.json" for kind in _PROPERTIES}


class WikidataGrammarCache:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_path = cache_dir / "wikidata_grammar.json"
        self._cache: dict[str, dict[str, str]] = {}
        if self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text())
        self._migrate_legacy_caches(cache_dir)

    def _migrate_legacy_caches(self, cache_dir: Path) -> None:
        legacy_data: dict[str, dict[str, list[str]]] = {}
        for kind, filename in _LEGACY_CACHE_FILENAMES.items():
            path = cache_dir / filename
            if path.exists():
                legacy_data[kind] = json.loads(path.read_text())
        if not legacy_data:
            return
        all_isos = {iso for values in legacy_data.values() for iso in values}
        changed = False
        for iso in all_isos:
            if iso in self._cache:
                continue
            self._cache[iso] = {
                kind: "|".join(legacy_data.get(kind, {}).get(iso, [])) for kind in _PROPERTIES
            }
            changed = True
        if changed:
            self._write_cache()

    def _write_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))

    def get(self, iso639_3: str) -> dict[str, list[str]]:
        """Returns {"writing_system": [...], "grammatical_case": [...], "tense": [...],
        "mood": [...], "aspect": [...]} for this language, each deduped, [] where none found
        (confirmed, or the query failed this run — a failed query is NOT written to cache, so
        it's retried on the next pipeline run instead of being permanently baked in as "no
        data" — see wikidata_sparql.py)."""
        if iso639_3 not in self._cache:
            raw = _query_combined(iso639_3)
            time.sleep(_REQUEST_DELAY_SECONDS)
            if raw is None:
                return {kind: [] for kind in _PROPERTIES}
            self._cache[iso639_3] = raw
            self._write_cache()
        stored = self._cache[iso639_3]
        return {kind: _dedupe(stored.get(kind, "").split("|")) if stored.get(kind) else [] for kind in _PROPERTIES}


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
    if "alphabet" in lowered and "braille" not in lowered:
        # Wikidata often names a language's Latin-based alphabet after the LANGUAGE rather
        # than the script family (confirmed live: "French alphabet", "Italian alphabet",
        # "German alphabet" — no family-name substring above matches "french"/"italian"/
        # "german"), which fell all the way to "other" despite the name saying "alphabet"
        # outright. Checked after the family-name match (which is more specific when both
        # apply, e.g. "Latin alphabet" already matched above) and before the final "other".
        return "alphabet"
    return "other"


def _query_combined(iso639_3: str) -> dict[str, str] | None:
    optional_blocks = []
    select_expressions = []
    for kind, property_id in _PROPERTIES.items():
        val_var, label_var = f"{kind}Val", f"{kind}Label"
        optional_blocks.append(
            f"OPTIONAL {{ ?entity wdt:{property_id} ?{val_var} . "
            f'?{val_var} rdfs:label ?{label_var} . FILTER(LANG(?{label_var})="en") }}'
        )
        select_expressions.append(f'(GROUP_CONCAT(DISTINCT ?{label_var}; separator="|") AS ?{kind})')
    pattern = " ".join(optional_blocks)
    return query_multi_with_macrolanguage_fallback(
        iso639_3, pattern, select_expressions, output_vars=list(_PROPERTIES)
    )
