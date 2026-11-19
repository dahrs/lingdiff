"""Loads etymology-db — a dataset automatically parsed from Wiktionary's own etymology
templates (confirmed live: 4,222,810 rows, CC BY-SA 3.0) — as the broad-but-uneven fallback
to WOLD for vocabulary-origin data (see pipeline/vocabulary_origin.py). Streams the ~436MB
CSV once at construction time rather than loading it into a DataFrame; only a handful of its
31 relation types matter here, and the overwhelming majority of rows get discarded, so this
keeps peak memory to the aggregated per-language counts, not the raw file.

Caveat from the dataset's own README, worth repeating here: "all information is pulled
directly from Wiktionary via semi-structured text parsing, and [the author's] made no effort
yet to validate any particular result." Treat ratios from this source as noisier and less
reliable than WOLD's expert-curated ones — see VocabularyOrigin.source."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.iso_language_codes import build_name_to_iso3

# Relation types that indicate the word was borrowed from another language, in some form —
# see the dataset's README for the exact distinction between these subtypes. Calques/semantic
# loans are deliberately excluded: the word's own morphemes are native, only the underlying
# concept/structure was borrowed, which is a different (and arguably weaker) kind of "foreign
# influence" than a literal loanword.
_BORROWING_RELTYPES = frozenset(
    {
        "borrowed_from",
        "learned_borrowing_from",
        "semi_learned_borrowing_from",
        "orthographic_borrowing_from",
        "unadapted_borrowing_from",
    }
)
_INHERITED_RELTYPE = "inherited_from"


class EtymologyDbResult:
    def __init__(self, borrowed_count: int, inherited_count: int, donor_counts: Counter[str]) -> None:
        self.borrowed_count = borrowed_count
        self.inherited_count = inherited_count
        self.donor_counts = donor_counts
        """Donor language NAME (as Wiktionary spells it, e.g. "Ancient Greek") -> count. Not
        resolved to an ISO 639-3/glottocode here — pipeline.vocabulary_origin does that, by
        re-running these same names through iso_language_codes.build_name_to_iso3."""


class EtymologyDbData:
    def __init__(self, raw_dir: Path) -> None:
        self._name_to_iso3 = build_name_to_iso3(raw_dir)
        self._borrowed_counts: dict[str, int] = defaultdict(int)
        self._inherited_counts: dict[str, int] = defaultdict(int)
        self._donor_counts: dict[str, Counter[str]] = defaultdict(Counter)

        with (raw_dir / "etymology_db.csv").open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # header: term_id,lang,term,reltype,related_term_id,related_lang,related_term,...
            for row in reader:
                if len(row) < 6:
                    continue
                lang_name, reltype, related_lang_name = row[1], row[3], row[5]
                if reltype == _INHERITED_RELTYPE:
                    iso3 = self._name_to_iso3.get(lang_name.lower())
                    if iso3:
                        self._inherited_counts[iso3] += 1
                elif reltype in _BORROWING_RELTYPES:
                    iso3 = self._name_to_iso3.get(lang_name.lower())
                    if iso3:
                        self._borrowed_counts[iso3] += 1
                        if related_lang_name:
                            self._donor_counts[iso3][related_lang_name] += 1

    def get(self, iso639_3: str) -> EtymologyDbResult | None:
        """None if neither a borrowed- nor inherited-type relation was found for this
        language at all — i.e. no direct origin classification exists for it in this data."""
        iso3 = iso639_3.lower()
        borrowed = self._borrowed_counts.get(iso3, 0)
        inherited = self._inherited_counts.get(iso3, 0)
        if borrowed == 0 and inherited == 0:
            return None
        return EtymologyDbResult(borrowed, inherited, self._donor_counts.get(iso3, Counter()))
