"""Python port of docs/compare.js's overall-score computation, used ONLY for the offline
"closest/farthest language in the list" precomputation (see run_pipeline.py and
pipeline/nearest_neighbors.py) — the live comparison page still does its own scoring in JS at
view time per the project's core design constraint (no server/Python involved in what a
visitor sees). This exists because precomputing "closest to every language" needs all
profiles compared pairwise at build time, in Python, not in a browser.

Kept in sync with compare.js BY HAND — there is no shared implementation between the two
languages. If you change one side's scoring logic, change this one too. This port only
covers what feeds the *overall* score (family, phonology, word order, morphology, writing
system) — compare.js's per-category detail views (diffView rendering, etc.) have no
equivalent here since nothing here is ever displayed, only ranked.
"""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE_OR_HYPHEN = re.compile(r"[-\s]")


def _normalize_family_name(name: str) -> str:
    return _WHITESPACE_OR_HYPHEN.sub("", name.lower())


def _family_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    path_a = [n["name"] for n in a["classification"]["path"]]
    path_b = [n["name"] for n in b["classification"]["path"]]

    best_index_a, best_index_b, best_depth = -1, -1, -1
    for index_a, name_a in enumerate(path_a):
        normalized_a = _normalize_family_name(name_a)
        for index_b, name_b in enumerate(path_b):
            if _normalize_family_name(name_b) != normalized_a:
                continue
            if index_a + index_b > best_depth:
                best_depth = index_a + index_b
                best_index_a, best_index_b = index_a, index_b

    hops_a = len(path_a) if best_index_a == -1 else len(path_a) - 1 - best_index_a
    hops_b = len(path_b) if best_index_b == -1 else len(path_b) - 1 - best_index_b
    max_depth = max(len(path_a), len(path_b), 1)
    return min(1.0, (hops_a + hops_b) / (2 * max_depth))


def _diff_score(list_a: list[str] | None, list_b: list[str] | None) -> float | None:
    """Mirrors compare.js's diffSets: None (not 0 or 1) whenever either side is empty — an
    empty list means "no data gathered", never "confirmed zero", so it must not be scored as
    "maximally different" (see compare.js's docstring for the bug this was)."""
    set_a, set_b = set(list_a or []), set(list_b or [])
    if not set_a or not set_b:
        return None
    shared = set_a & set_b
    union = set_a | set_b
    return 1 - len(shared) / len(union)


def _phonology_distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    # `.get(key, {})` only substitutes the default when `key` is ABSENT, not when it's
    # present with value None — and pydantic's model_dump() (unlike model_dump_json(
    # exclude_none=True), used for the on-disk JSON) always includes every field, set to
    # None when unset. Confirmed live: crashed the real nearest-neighbor pass outright with
    # AttributeError on any profile lacking phonology data, which is most of them at broad
    # coverage. `or {}` is required, not optional, on every one of these.
    phonology_a = a.get("phonology") or {}
    phonology_b = b.get("phonology") or {}
    return _diff_score(phonology_a.get("phonemes", []), phonology_b.get("phonemes", []))


def _word_order_distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    syntax_a = a.get("syntax") or {}
    syntax_b = b.get("syntax") or {}
    features_a = syntax_a.get("features", [])
    features_b = syntax_b.get("features", [])
    if not features_a or not features_b:
        return None
    map_a = {f["wals_code"]: f["value"] for f in features_a}
    map_b = {f["wals_code"]: f["value"] for f in features_b}
    shared_codes = set(map_a) & set(map_b)
    if not shared_codes:
        return None
    matches = sum(1 for code in shared_codes if map_a[code] == map_b[code])
    return 1 - matches / len(shared_codes)


def _morphology_distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    morph_a = a.get("morphology", {}) or {}
    morph_b = b.get("morphology", {}) or {}
    sub_scores = [
        _diff_score(morph_a.get(key), morph_b.get(key)) for key in ("grammatical_cases", "tenses", "moods", "aspects")
    ]
    sub_scores.append(
        _diff_score(
            [c["name"] for c in morph_a.get("tense_aspect_categories", [])],
            [c["name"] for c in morph_b.get("tense_aspect_categories", [])],
        )
    )
    available = [s for s in sub_scores if s is not None]
    if not available:
        return None
    return sum(available) / len(available)


def _writing_system_distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    scripts_a = a.get("writing_system", {}).get("scripts", []) if a.get("writing_system") else []
    scripts_b = b.get("writing_system", {}).get("scripts", []) if b.get("writing_system") else []
    if not scripts_a or not scripts_b:
        return None
    names_score = _diff_score([s["name"] for s in scripts_a], [s["name"] for s in scripts_b])
    if names_score is None:
        return None
    shared_names = {s["name"] for s in scripts_a} & {s["name"] for s in scripts_b}
    if not shared_names:
        shared_types = {s["script_type"] for s in scripts_a} & {s["script_type"] for s in scripts_b}
        if shared_types:
            return 0.4
    return names_score


_WEIGHTS: dict[str, float] = {
    "family": 1.5,
    "phonology": 1.0,
    "word_order": 1.0,
    "morphology": 1.0,
    "writing_system": 0.5,
}


def overall_distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    """0-100 overall distance score, re-normalized over whichever categories had data for
    this pair — same weights and meaning as compare.js's computeOverall. None if NEITHER
    profile has enough data for even one category (practically never happens, since family
    distance is always computable from classification alone)."""
    scores = {
        "family": _family_distance(a, b),
        "phonology": _phonology_distance(a, b),
        "word_order": _word_order_distance(a, b),
        "morphology": _morphology_distance(a, b),
        "writing_system": _writing_system_distance(a, b),
    }
    weighted_sum = 0.0
    total_weight = 0.0
    for key, weight in _WEIGHTS.items():
        score = scores[key]
        if score is not None:
            weighted_sum += score * weight
            total_weight += weight
    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight * 100)
