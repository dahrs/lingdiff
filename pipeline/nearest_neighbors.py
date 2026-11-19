"""Precomputes, for every leaf language profile, which other leaf is closest (lowest overall
distance) and which is farthest (highest) — a build-time O(n^2/2) pass over all profiles
(see pipeline.scoring), never something the live site computes itself. Results are merged
into each LanguageIndexEntry (see schema.py and run_pipeline.py) so the picker can show
"closest: X" / "farthest: Y" for whichever language is selected with no extra fetch needed —
that data is already sitting in index.json, which the picker loads upfront regardless.

Restricted to comparison_kind="leaf" profiles only (see run_pipeline.py's caller) — comparing
against a "group" (family/macrolanguage) entity means fewer categories have any data at all,
which would make group entities spuriously dominate "farthest" for almost everyone; "closest
*language*" should mean closest among actual languages.
"""

from __future__ import annotations

from typing import Any

from pipeline.scoring import overall_distance


def compute_nearest_neighbors(
    leaf_profiles: list[tuple[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any] | None]]:
    """`leaf_profiles` is [(glottocode, profile_dict), ...] for every comparison_kind="leaf"
    profile. Returns {glottocode: {"closest": {...} | None, "farthest": {...} | None}}, each
    inner dict holding {"glottocode", "name", "score"} for whichever other profile was
    closest/farthest. None when there was nothing to compare against at all (a list of 1) or
    no pair had any scoreable category in common (practically never — family distance alone
    is almost always computable from classification data)."""
    best: dict[str, dict[str, dict[str, Any]]] = {glottocode: {} for glottocode, _ in leaf_profiles}

    count = len(leaf_profiles)
    for i in range(count):
        glottocode_a, profile_a = leaf_profiles[i]
        for j in range(i + 1, count):
            glottocode_b, profile_b = leaf_profiles[j]
            score = overall_distance(profile_a, profile_b)
            if score is None:
                continue
            _update_extreme(best[glottocode_a], "closest", glottocode_b, profile_b["name"], score, prefer_lower=True)
            _update_extreme(best[glottocode_a], "farthest", glottocode_b, profile_b["name"], score, prefer_lower=False)
            _update_extreme(best[glottocode_b], "closest", glottocode_a, profile_a["name"], score, prefer_lower=True)
            _update_extreme(best[glottocode_b], "farthest", glottocode_a, profile_a["name"], score, prefer_lower=False)

    return {
        glottocode: {"closest": entries.get("closest"), "farthest": entries.get("farthest")}
        for glottocode, entries in best.items()
    }


def _update_extreme(
    entries: dict[str, dict[str, Any]],
    key: str,
    candidate_glottocode: str,
    candidate_name: str,
    score: int,
    prefer_lower: bool,
) -> None:
    current = entries.get(key)
    is_better = current is None or (score < current["score"] if prefer_lower else score > current["score"])
    if is_better:
        entries[key] = {"glottocode": candidate_glottocode, "name": candidate_name, "score": score}
