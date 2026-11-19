"""Merges WOLD + etymology-db into one VocabularyOrigin per language — WOLD preferred
whenever it covers the language, etymology-db as the broader-but-noisier fallback. See
schema.VocabularyOrigin for the field meanings.

**Why WOLD is preferred, not just listed first — confirmed live, not a hypothetical**:
etymology-db gives Mandarin Chinese an 86% borrowed ratio (dominated by English/Japanese
donors); WOLD's expert-curated score for the same language is 2%. The gap isn't noise, it's
systematic: Wiktionary's etymology templates are far more consistently applied to loanwords
(which editors find "interesting" to document) than to a language's inherited core
vocabulary, especially for languages written in a non-Latin, non-alphabetic script (Mandarin,
and by the same logic almost certainly Arabic, which WOLD doesn't cover at all — its 84.7%
etymology-db figure should be treated with real skepticism, not as a reliable measurement).
This asymmetry means etymology-db's ratio isn't just "less precise" than WOLD's, it can be
*systematically biased toward "more borrowed"* for exactly the languages least like the
European, alphabetically-written ones Wiktionary's etymology coverage is deepest for. Flagged
here, in `VocabularyOrigin.source`, and in the README — not hidden, and not something this
module tries to algorithmically correct, since there's no principled way to do that without
an independent, reliable second measurement (which is exactly what WOLD is, for the 41
languages it covers).
"""

from __future__ import annotations

from collections import Counter

from pipeline.etymology_db_loader import EtymologyDbData
from pipeline.iso_language_codes import build_name_to_iso3
from pipeline.schema import DonorLanguageShare, VocabularyOrigin
from pipeline.wals_loader import WalsData
from pipeline.wold_loader import WoldData

_MAX_DONOR_LANGUAGES = 8


def build_vocabulary_origin(
    iso639_3: str, wold: WoldData, etymology_db: EtymologyDbData, wals: WalsData, name_to_iso3: dict[str, str]
) -> VocabularyOrigin | None:
    wold_result = wold.get(iso639_3)
    if wold_result is not None:
        donors = _tally_donor_pairs(wold_result.donors)
        return VocabularyOrigin(
            borrowed_ratio=round(wold_result.mean_borrowed_score, 3),
            donor_languages=_to_shares(donors, wals, name_to_iso3, prefer_given_glottocode=True),
            sample_size=wold_result.sample_size,
            source="wold",
        )

    etymology_result = etymology_db.get(iso639_3)
    if etymology_result is None:
        return None
    total = etymology_result.borrowed_count + etymology_result.inherited_count
    if total == 0:
        return None
    donors = [(name, None, count) for name, count in etymology_result.donor_counts.items()]
    return VocabularyOrigin(
        borrowed_ratio=round(etymology_result.borrowed_count / total, 3),
        donor_languages=_to_shares(donors, wals, name_to_iso3, prefer_given_glottocode=False),
        sample_size=total,
        source="etymology_db",
    )


def _tally_donor_pairs(donors: list[tuple[str, str | None]]) -> list[tuple[str, str | None, int]]:
    counts: Counter[tuple[str, str | None]] = Counter(donors)
    return [(name, glottocode, count) for (name, glottocode), count in counts.items()]


def _to_shares(
    donors: list[tuple[str, str | None, int]],
    wals: WalsData,
    name_to_iso3: dict[str, str],
    prefer_given_glottocode: bool,
) -> list[DonorLanguageShare]:
    total = sum(count for _, _, count in donors)
    if total == 0:
        return []
    merged: dict[str, dict[str, object]] = {}
    for name, glottocode, count in donors:
        if not glottocode:
            glottocode = _resolve_glottocode(name, wals, name_to_iso3)
        entry = merged.setdefault(name, {"glottocode": glottocode, "count": 0})
        entry["count"] = int(entry["count"]) + count
        if prefer_given_glottocode and glottocode:
            entry["glottocode"] = glottocode

    shares = [
        DonorLanguageShare(
            name=name,
            glottocode=entry["glottocode"],  # type: ignore[arg-type]
            count=entry["count"],  # type: ignore[arg-type]
            percentage=round(100 * entry["count"] / total, 1),  # type: ignore[operator]
        )
        for name, entry in merged.items()
    ]
    shares.sort(key=lambda s: s.count, reverse=True)
    return shares[:_MAX_DONOR_LANGUAGES]


def _resolve_glottocode(donor_name: str, wals: WalsData, name_to_iso3: dict[str, str]) -> str | None:
    """Cross-references a donor language NAME (etymology-db gives no code at all) against
    our own WALS-keyed dataset, via the same name->ISO 639-3 table used to interpret
    etymology-db's rows in the first place. None when the donor isn't a language WALS covers
    (reconstructed proto-languages, historical stages like "Old Norse" that are real but
    outside WALS's scope, etc.) — not an error, just nothing further to link to."""
    iso3 = name_to_iso3.get(donor_name.lower())
    if not iso3:
        return None
    wals_lang = wals.find_language(iso3)
    return wals_lang["Glottocode"] if wals_lang else None
