"""Parses Unicode CLDR's per-locale exemplar-character data (see fetch_cldr_sources.py) into
per-ISO-639-3 letter lists, for attaching to LanguageProfile.writing_system.scripts[].
sample_glyphs (see build_profile.py's _attach_sample_glyphs).

Matching strategy: a CLDR locale code with NO script subtag (e.g. "fr", "it", "ast") maps to
an ISO 639-3 code via its 2-letter ISO 639-1 equivalent (iso_language_codes.
build_part1_to_iso3) when the locale code is 2 letters, or directly when the locale code is
already a 3-letter ISO 639-3 Id itself (e.g. "ast" Asturian, "ady" Adyghe — CLDR uses the
language's real ISO 639-3 tag as the locale's primary subtag whenever there's no 639-1 code).

Locale codes WITH a script subtag (e.g. "zh-Hans"/"zh-Hant", "sr-Cyrl"/"sr-Latn") are
deliberately NOT matched to anything here — a profile can list more than one script (see
schema.WritingSystem), and disambiguating which CLDR script-variant corresponds to which of a
profile's several Script entries isn't attempted; left unmatched rather than guessed. In
practice this only costs us letter data for languages that are written in more than one
script — most languages have exactly one, and get matched via the plain base locale.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.iso_language_codes import build_part1_to_iso3, valid_iso639_3_codes

_EXEMPLAR_TOKEN = re.compile(r"\{[^}]*\}|\\.|\S")


def parse_exemplar_set(raw: str) -> list[str]:
    """Parses a UTS#35 UnicodeSet string's exemplar set (e.g. "[a à â æ b c ç ...]") into
    individual letters. Handles the two constructs CLDR's exemplarCharacters data actually
    uses: `{multi-char}` compound letters, kept as one unit (e.g. Welsh "{ch}", Hungarian
    "{sz}" — digraphs/trigraphs treated as a single letter in that language's own
    orthography), and bare adjacent single codepoints with no separator, CLDR's space-saving
    convention for grouping a base letter with its accented forms (e.g. French "aàâ" parses
    to the three separate letters a/à/â). Does not handle UnicodeSet ranges ("a-z") or set
    operators — neither appears in any base locale's exemplarCharacters (verified by
    inspection), only in its punctuation/numbers sets, which this is never called on."""
    inner = raw.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    letters: list[str] = []
    for token in _EXEMPLAR_TOKEN.findall(inner):
        if token.startswith("{") and token.endswith("}"):
            letters.append(token[1:-1])
        elif token.startswith("\\"):
            letters.append(token[1:])
        else:
            letters.append(token)
    return letters


class CldrData:
    def __init__(self, raw_dir: Path) -> None:
        part1_to_iso3 = build_part1_to_iso3(raw_dir)
        valid_iso3 = valid_iso639_3_codes(raw_dir)
        self._letters_by_iso3: dict[str, list[str]] = {}

        cldr_dir = raw_dir / "cldr"
        for path in cldr_dir.glob("*.json"):
            locale = path.stem
            if "-" in locale:
                continue  # script-subtag locale — not matched, see module docstring
            if len(locale) == 2:
                iso3 = part1_to_iso3.get(locale)
            else:
                iso3 = locale if locale in valid_iso3 else None
            if iso3 is None:
                continue
            raw = json.loads(path.read_text())
            characters = raw.get("main", {}).get(locale, {}).get("characters", {})
            exemplar = characters.get("exemplarCharacters")
            if exemplar:
                self._letters_by_iso3[iso3] = parse_exemplar_set(exemplar)

    def get(self, iso639_3: str) -> list[str] | None:
        return self._letters_by_iso3.get(iso639_3)
