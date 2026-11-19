"""Precomputes, for every leaf language profile, the top 3 closest (lowest overall distance)
and top 3 farthest (highest) other leaves — a build-time O(n^2/2) pass over all profiles
(see pipeline.scoring), never something the live site computes itself. Results are merged
into each LanguageIndexEntry (see schema.py and run_pipeline.py) so the picker can show a
gold/silver/bronze "podium" for whichever language is selected with no extra fetch needed —
that data is already sitting in index.json, which the picker loads upfront regardless.

Restricted to comparison_kind="leaf" profiles only (see run_pipeline.py's caller) — comparing
against a "group" (family/macrolanguage) entity means fewer categories have any data at all,
which would make group entities spuriously dominate "farthest" for almost everyone; "closest
*language*" should mean closest among actual languages.
"""

from __future__ import annotations

from typing import Any

from pipeline.scoring import overall_distance

_PODIUM_SIZE = 3


def compute_nearest_neighbors(
    leaf_profiles: list[tuple[str, dict[str, Any]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """`leaf_profiles` is [(glottocode, profile_dict), ...] for every comparison_kind="leaf"
    profile. Returns {glottocode: {"closest": [...], "farthest": [...]}}, each a list of up
    to 3 {"glottocode", "name", "score"} dicts, best (lowest score for "closest", highest for
    "farthest") first. A list can be shorter than 3 (even empty) when there weren't enough
    other profiles with any scoreable category in common — practically never for "closest",
    since family distance alone is almost always computable from classification data."""
    podiums: dict[str, dict[str, list[dict[str, Any]]]] = {
        glottocode: {"closest": [], "farthest": []} for glottocode, _ in leaf_profiles
    }

    count = len(leaf_profiles)
    for i in range(count):
        glottocode_a, profile_a = leaf_profiles[i]
        for j in range(i + 1, count):
            glottocode_b, profile_b = leaf_profiles[j]
            score = overall_distance(profile_a, profile_b)
            if score is None:
                continue
            _offer(podiums[glottocode_a]["closest"], glottocode_b, profile_b["name"], score, prefer_lower=True)
            _offer(podiums[glottocode_a]["farthest"], glottocode_b, profile_b["name"], score, prefer_lower=False)
            _offer(podiums[glottocode_b]["closest"], glottocode_a, profile_a["name"], score, prefer_lower=True)
            _offer(podiums[glottocode_b]["farthest"], glottocode_a, profile_a["name"], score, prefer_lower=False)

    return podiums


def _offer(
    podium: list[dict[str, Any]], candidate_glottocode: str, candidate_name: str, score: int, prefer_lower: bool
) -> None:
    """Inserts the candidate into `podium` (mutated in place) if it ranks among the top
    `_PODIUM_SIZE`, keeping it sorted best-first and trimmed to that size. Re-sorting a
    (at most `_PODIUM_SIZE`-long, since it's trimmed every call) list on every offer is
    simpler than a proper insert-and-shift and the list is small enough that it doesn't
    matter for an O(n^2) pass over thousands of languages."""
    podium.append({"glottocode": candidate_glottocode, "name": candidate_name, "score": score})
    podium.sort(key=lambda entry: entry["score"], reverse=not prefer_lower)
    del podium[_PODIUM_SIZE:]
