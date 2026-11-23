"""Python port of docs/compare.js — the SAME comparison logic the website runs in the
browser, reimplemented here so this API can compute it server-side over raw LanguageProfile
JSON (see data_loader.py) without a browser.

Kept in sync with compare.js BY HAND — there is no shared implementation between the two (no
Node/JS runtime in this project's pipeline either; see pipeline/scoring.py's own docstring for
the same situation on the offline nearest-neighbor side). If you change the comparison logic
in compare.js, change it here too. Every function below mirrors its compare.js namesake
function-for-function and should stay readable side by side with it.
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas import (
    CategoryResults,
    ComparisonResponse,
    DiffResult,
    FamilyResult,
    LanguageSummary,
    MorphologyResult,
    OverallResult,
    PhonologyResult,
    VocabularyOriginResult,
    VocabularyOriginSummary,
    WordOrderResult,
    WordOrderRow,
    WritingSystemResult,
)

_WHITESPACE_OR_HYPHEN = re.compile(r"[-\s]")


def _normalize_family_name(name: str) -> str:
    return _WHITESPACE_OR_HYPHEN.sub("", name.lower())


def _diff_sets(list_a: list[str] | None, list_b: list[str] | None) -> DiffResult:
    set_a, set_b = set(list_a or []), set(list_b or [])
    shared = sorted(set_a & set_b)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    union = len(shared) + len(only_a) + len(only_b)
    score = None if (not set_a or not set_b) else 1 - len(shared) / union
    return DiffResult(shared=shared, only_a=only_a, only_b=only_b, score=score)


def _compare_family(a: dict[str, Any], b: dict[str, Any]) -> FamilyResult:
    path_a = [node["name"] for node in a["classification"]["path"]]
    path_b = [node["name"] for node in b["classification"]["path"]]

    best_index_a, best_index_b, best_depth = -1, -1, -1
    for index_a, name_a in enumerate(path_a):
        normalized_a = _normalize_family_name(name_a)
        for index_b, name_b in enumerate(path_b):
            if _normalize_family_name(name_b) != normalized_a:
                continue
            if index_a + index_b > best_depth:
                best_depth = index_a + index_b
                best_index_a, best_index_b = index_a, index_b

    if best_index_a == -1:
        return FamilyResult(
            available=True,
            score=1.0,
            path_a=path_a,
            path_b=path_b,
            common_ancestor=None,
            diverge_at_a=path_a[0] if path_a else None,
            diverge_at_b=path_b[0] if path_b else None,
        )

    hops_a = len(path_a) - 1 - best_index_a
    hops_b = len(path_b) - 1 - best_index_b
    max_depth = max(len(path_a), len(path_b), 1)
    score = min(1.0, (hops_a + hops_b) / (2 * max_depth))
    return FamilyResult(
        available=True,
        score=score,
        path_a=path_a,
        path_b=path_b,
        common_ancestor=path_a[best_index_a],
        diverge_at_a=path_a[best_index_a + 1] if best_index_a + 1 < len(path_a) else None,
        diverge_at_b=path_b[best_index_b + 1] if best_index_b + 1 < len(path_b) else None,
    )


def _compare_phonology(a: dict[str, Any], b: dict[str, Any]) -> PhonologyResult:
    phonemes_a = (a.get("phonology") or {}).get("phonemes", [])
    phonemes_b = (b.get("phonology") or {}).get("phonemes", [])
    if not phonemes_a or not phonemes_b:
        return PhonologyResult(available=False)
    diff = _diff_sets(phonemes_a, phonemes_b)
    return PhonologyResult(
        available=True, shared=diff.shared, only_a=diff.only_a, only_b=diff.only_b, score=diff.score
    )


def _compare_word_order(a: dict[str, Any], b: dict[str, Any]) -> WordOrderResult:
    features_a = (a.get("syntax") or {}).get("features", [])
    features_b = (b.get("syntax") or {}).get("features", [])
    if not features_a and not features_b:
        return WordOrderResult(available=False)

    map_a = {f["wals_code"]: f for f in features_a}
    map_b = {f["wals_code"]: f for f in features_b}
    codes = sorted(set(map_a) | set(map_b))
    rows: list[WordOrderRow] = []
    for code in codes:
        fa = map_a.get(code)
        fb = map_b.get(code)
        source = fa or fb
        assert source is not None
        value_a = fa["value"] if fa else None
        value_b = fb["value"] if fb else None
        match = (value_a == value_b) if (fa and fb) else None
        rows.append(
            WordOrderRow(name=source["name"], value_a=value_a, value_b=value_b, match=match)
        )

    comparable = [row for row in rows if row.match is not None]
    score = (
        None if not comparable else 1 - sum(1 for row in comparable if row.match) / len(comparable)
    )
    return WordOrderResult(available=True, rows=rows, score=score)


def _compare_morphology(a: dict[str, Any], b: dict[str, Any]) -> MorphologyResult:
    morph_a = a.get("morphology") or {}
    morph_b = b.get("morphology") or {}
    cases = _diff_sets(morph_a.get("grammatical_cases"), morph_b.get("grammatical_cases"))
    tenses = _diff_sets(morph_a.get("tenses"), morph_b.get("tenses"))
    moods = _diff_sets(morph_a.get("moods"), morph_b.get("moods"))
    aspects = _diff_sets(morph_a.get("aspects"), morph_b.get("aspects"))
    wals_categories = _diff_sets(
        [c["name"] for c in morph_a.get("tense_aspect_categories", [])],
        [c["name"] for c in morph_b.get("tense_aspect_categories", [])],
    )

    all_diffs = [cases, tenses, moods, aspects, wals_categories]
    available_scores = [d.score for d in all_diffs if d.score is not None]
    if not available_scores:
        return MorphologyResult(available=False)
    score = sum(available_scores) / len(available_scores)
    return MorphologyResult(
        available=True,
        cases=cases,
        tenses=tenses,
        moods=moods,
        aspects=aspects,
        wals_categories=wals_categories,
        score=score,
    )


def _compare_writing_system(a: dict[str, Any], b: dict[str, Any]) -> WritingSystemResult:
    scripts_a = (a.get("writing_system") or {}).get("scripts", [])
    scripts_b = (b.get("writing_system") or {}).get("scripts", [])
    if not scripts_a or not scripts_b:
        return WritingSystemResult(available=False)

    names_diff = _diff_sets([s["name"] for s in scripts_a], [s["name"] for s in scripts_b])
    types_a = {s["script_type"] for s in scripts_a}
    types_b = {s["script_type"] for s in scripts_b}
    shared_types = sorted(types_a & types_b)

    glyphs_a = next((s.get("sample_glyphs") for s in scripts_a if s.get("sample_glyphs")), None)
    glyphs_b = next((s.get("sample_glyphs") for s in scripts_b if s.get("sample_glyphs")), None)
    glyphs = _diff_sets(glyphs_a, glyphs_b) if (glyphs_a and glyphs_b) else None

    score = names_diff.score
    if not names_diff.shared and shared_types:
        score = 0.4
    if glyphs is not None and glyphs.score is not None:
        score = glyphs.score

    return WritingSystemResult(
        available=True,
        shared=names_diff.shared,
        only_a=names_diff.only_a,
        only_b=names_diff.only_b,
        shared_types=shared_types,
        glyphs=glyphs,
        score=score,
    )


def _compare_vocabulary_origin(a: dict[str, Any], b: dict[str, Any]) -> VocabularyOriginResult:
    vo_a = a.get("vocabulary_origin")
    vo_b = b.get("vocabulary_origin")
    if not vo_a or not vo_b:
        return VocabularyOriginResult(available=False)

    def matches_profile(donor: dict[str, Any], profile: dict[str, Any]) -> bool:
        if donor.get("glottocode") and donor["glottocode"] == profile.get("glottocode"):
            return True
        if _normalize_family_name(donor["name"]) == _normalize_family_name(profile["name"]):
            return True
        return _normalize_family_name(donor["name"]) == _normalize_family_name(
            profile.get("english_name", "")
        )

    donors_a = vo_a.get("donor_languages", [])
    donors_b = vo_b.get("donor_languages", [])
    names_a = [d["name"] for d in donors_a]
    names_b = [d["name"] for d in donors_b]

    # A language never lists itself as its own donor, but if it directly influenced the OTHER
    # language in this comparison, that's still a genuine point of overlap — see
    # compareVocabularyOrigin's docstring in compare.js.
    b_borrowed_from_a = next((d for d in donors_b if matches_profile(d, a)), None)
    a_borrowed_from_b = next((d for d in donors_a if matches_profile(d, b)), None)
    if b_borrowed_from_a and b_borrowed_from_a["name"] not in names_a:
        names_a = [*names_a, b_borrowed_from_a["name"]]
    if a_borrowed_from_b and a_borrowed_from_b["name"] not in names_b:
        names_b = [*names_b, a_borrowed_from_b["name"]]

    diff = _diff_sets(names_a, names_b)
    return VocabularyOriginResult(
        available=True,
        vocabulary_origin_a=VocabularyOriginSummary(**vo_a),
        vocabulary_origin_b=VocabularyOriginSummary(**vo_b),
        shared=diff.shared,
        only_a=diff.only_a,
        only_b=diff.only_b,
        score=diff.score,
    )


# key -> weight, mirroring compare.js's computeOverall. vocabulary_origin is deliberately
# absent — see VocabularyOriginResult's docstring.
_WEIGHTED: list[tuple[str, float]] = [
    ("family", 1.5),
    ("phonology", 1.0),
    ("word_order", 1.0),
    ("morphology", 1.0),
    ("writing_system", 0.5),
]


def _compute_overall(
    categories: dict[
        str,
        FamilyResult | PhonologyResult | WordOrderResult | MorphologyResult | WritingSystemResult,
    ],
) -> OverallResult:
    weighted_sum = 0.0
    total_weight = 0.0
    available_count = 0
    for key, weight in _WEIGHTED:
        cat = categories[key]
        if cat.available and cat.score is not None:
            weighted_sum += cat.score * weight
            total_weight += weight
            available_count += 1
    if total_weight == 0:
        return OverallResult(
            score=None, available_count=available_count, total_count=len(_WEIGHTED)
        )
    return OverallResult(
        score=round(weighted_sum / total_weight * 100),
        available_count=available_count,
        total_count=len(_WEIGHTED),
    )


def _qualitative_label(score: int | None) -> str:
    if score is None:
        return "not enough data"
    if score < 15:
        return "very close"
    if score < 35:
        return "close"
    if score < 60:
        return "moderately different"
    if score < 80:
        return "distant"
    return "very distant"


def compare_languages(a: dict[str, Any], b: dict[str, Any]) -> ComparisonResponse:
    family = _compare_family(a, b)
    phonology = _compare_phonology(a, b)
    word_order = _compare_word_order(a, b)
    morphology = _compare_morphology(a, b)
    writing_system = _compare_writing_system(a, b)
    vocabulary_origin = _compare_vocabulary_origin(a, b)

    overall = _compute_overall(
        {
            "family": family,
            "phonology": phonology,
            "word_order": word_order,
            "morphology": morphology,
            "writing_system": writing_system,
        }
    )

    return ComparisonResponse(
        language_a=LanguageSummary(
            glottocode=a["glottocode"],
            iso639_3=a.get("iso639_3"),
            name=a["name"],
            english_name=a["english_name"],
        ),
        language_b=LanguageSummary(
            glottocode=b["glottocode"],
            iso639_3=b.get("iso639_3"),
            name=b["name"],
            english_name=b["english_name"],
        ),
        categories=CategoryResults(
            family=family,
            phonology=phonology,
            word_order=word_order,
            morphology=morphology,
            writing_system=writing_system,
            vocabulary_origin=vocabulary_origin,
        ),
        overall=overall,
        label=_qualitative_label(overall.score),
    )
