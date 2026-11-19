"""Maps a Wiktionary-style language NAME (e.g. "Latin", "Ancient Greek") to an ISO 639-3
code — needed because etymology-db's `lang`/`related_lang` columns are free-text names, not
codes (confirmed live: rows read like `lang=Latin, related_lang=Ancient Greek`), while our
own dataset is keyed by ISO 639-3 throughout.

Built from three real, downloaded sources rather than any hardcoded name/code table:
- `wiktionary_codes.csv` (from etymology-db's own repo): Wiktionary's own short code -> the
  exact language name used in its etymology templates (and therefore in etymology-db's `lang`
  column). Most codes here are already ISO 639-3 directly (confirmed live: ~7400 of ~8600 are
  3 letters and match real ISO 639-3 codes, e.g. "aaa"->Ghotuo, the same language WALS covers)
  — those need no further mapping.
- `iso639-3.tab` (SIL's own official code table): for Wiktionary's ~180 2-letter codes (the
  major world languages — English, French, German, Spanish, Arabic, Chinese, ... — all use
  ISO 639-1-style 2-letter codes in Wiktionary) gives the ISO 639-1 <-> ISO 639-3 equivalence.
- `iso639-3-macrolanguages.tab` (also SIL): a 2-letter code can resolve to a MACROLANGUAGE
  (confirmed live: "ar" -> "ara", "zh" -> "zho" — not an individual, speakable language, the
  same ambiguity build_profile.py already handles for Wikidata lookups). Rather than pick a
  "most representative member" algorithmically, this hardcodes the two cases that actually
  matter for any major, etymology-db-rich language (Arabic -> "arb" Standard Arabic, Chinese
  -> "cmn" Mandarin) — the same individual varieties WALS/this pipeline already treats as
  each macrolanguage's default representative elsewhere. Any other macrolanguage-ambiguous
  code simply won't resolve (treated as "no mapping", not guessed).
"""

from __future__ import annotations

import csv
from pathlib import Path

_MACROLANGUAGE_DEFAULT_MEMBER: dict[str, str] = {
    "ara": "arb",
    "zho": "cmn",
}


def _load_iso639_3_tables(raw_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Returns (part1_to_iso3, scope_by_iso3), parsed once from SIL's iso639-3.tab — shared by
    build_name_to_iso3 and build_part1_to_iso3 below."""
    part1_to_iso3: dict[str, str] = {}
    scope_by_iso3: dict[str, str] = {}
    with (raw_dir / "iso639-3.tab").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            scope_by_iso3[row["Id"]] = row["Scope"]
            if row["Part1"]:
                part1_to_iso3[row["Part1"]] = row["Id"]
    return part1_to_iso3, scope_by_iso3


def _resolve_macrolanguage(iso3: str, scope_by_iso3: dict[str, str]) -> str:
    """Collapses a macrolanguage code (Scope="M") to its hardcoded default member (see
    _MACROLANGUAGE_DEFAULT_MEMBER); returns "" for an unmapped macrolanguage (treated as "no
    mapping", never guessed) or `iso3` unchanged when it isn't a macrolanguage at all."""
    if scope_by_iso3.get(iso3) != "M":
        return iso3
    return _MACROLANGUAGE_DEFAULT_MEMBER.get(iso3, "")


def build_name_to_iso3(raw_dir: Path) -> dict[str, str]:
    """Returns {lowercased language name: iso639_3}, e.g. {"latin": "lat", "french": "fra"}."""
    code_to_name: dict[str, str] = {}
    with (raw_dir / "wiktionary_codes.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                code_to_name[row[0].strip()] = row[1].strip()

    part1_to_iso3, scope_by_iso3 = _load_iso639_3_tables(raw_dir)

    name_to_iso3: dict[str, str] = {}
    for code, name in code_to_name.items():
        if len(code) == 3:
            iso3 = code
        elif len(code) == 2:
            iso3 = part1_to_iso3.get(code, "")
        else:
            continue
        if not iso3:
            continue
        iso3 = _resolve_macrolanguage(iso3, scope_by_iso3)
        if not iso3:
            continue
        name_to_iso3[name.lower()] = iso3
    return name_to_iso3


def build_part1_to_iso3(raw_dir: Path) -> dict[str, str]:
    """Returns {ISO 639-1 2-letter code: ISO 639-3 code}, with macrolanguage codes already
    resolved to their default member — used by pipeline/cldr_loader.py to map CLDR's 2-letter
    locale subtags onto our ISO-639-3-keyed profiles."""
    part1_to_iso3, scope_by_iso3 = _load_iso639_3_tables(raw_dir)
    resolved: dict[str, str] = {}
    for part1, iso3 in part1_to_iso3.items():
        resolved_iso3 = _resolve_macrolanguage(iso3, scope_by_iso3)
        if resolved_iso3:
            resolved[part1] = resolved_iso3
    return resolved


def valid_iso639_3_codes(raw_dir: Path) -> set[str]:
    """Returns the full set of ISO 639-3 Ids (SIL's iso639-3.tab) — used by
    pipeline/cldr_loader.py to check whether a CLDR locale whose primary subtag is already 3
    letters (e.g. "ady", "ast") is itself a real ISO 639-3 code rather than something else."""
    with (raw_dir / "iso639-3.tab").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["Id"] for row in reader}
