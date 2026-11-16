"""Deep genealogical classification path via Wikidata's P279 ("subclass of") edges, as an
upgrade over WALS's shallow 3-level Family/Subfamily/Genus columns (see build_profile.py and
the plan: "Spanish -> Ibero-Romance -> Romance -> Italic -> Indo-European" vs. WALS's flat
"Indo-European -> Romance -> Spanish").

Unfiltered P279* also pulls in generic ontology classes Wikidata models "language" as a
subclass of (confirmed live: "conceptual system", "abstract entity", "soft symbol sequence",
"entity (BFO)", ...) — this filters ancestors to ones tagged "instance of: language family"
(Q25295), which empirically isolates the real linguistic taxonomy (confirmed live for Spanish:
Castilian, West Iberian, Iberian Romance, Gallo-Iberian, Western Romance, Italo-Western,
Romance, Latino-Faliscan, Italic, Italo-Celtic, Indo-European).

The result isn't a strict tree — a handful of nodes carry more than one P279 parent in
Wikidata (e.g. "Italic" lists both Indo-European and Italo-Celtic). Reconstruction picks one
parent per node, preferring a Q25295-tagged one, then falls back to whichever was returned
first — the same "good enough, not authoritative" heuristic already used for WALS's
dialect-selection ambiguity (wals_loader.py). This path is for human-readable display only;
it never feeds the actual genetic DISTANCE SCORE, which stays URIEL's genetic vector.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.wikidata_sparql import run_query

_LANGUAGE_FAMILY_QID = "Q25295"
_MAX_HOPS = 15


class FamilyTreeCache:
    """Caches get_family_path results to data/sources/raw/wikidata_family_tree.json — this
    lookup is deterministic, so there's no reason to re-query a flaky endpoint on every
    rerun. Same discipline as wikidata_lookup.py's WikidataPropertyCache: a failed query (see
    run_query) is NOT written to cache, so it's retried next run instead of being permanently
    baked in as "no family tree"."""

    def __init__(self, raw_dir: Path) -> None:
        self._cache_path = raw_dir / "wikidata_family_tree.json"
        self._cache: dict[str, list[str]] = {}
        if self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text())

    def get(self, iso639_3: str) -> list[str] | None:
        if iso639_3 in self._cache:
            return self._cache[iso639_3]
        path = get_family_path(iso639_3)
        if path is None:
            return None
        self._cache[iso639_3] = path
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))
        return path


def get_family_path(iso639_3: str) -> list[str] | None:
    """Ancestor names for the language with this ISO 639-3 code — see get_family_path_from_qid,
    which this resolves the Wikidata entity for and delegates to. None if no Wikidata entity
    was found for this ISO code. Prefer FamilyTreeCache.get over calling this directly so
    results survive across pipeline reruns."""
    qid = _find_entity_qid(iso639_3)
    if qid is None:
        return None
    return get_family_path_from_qid(qid)


def get_family_path_from_qid(qid: str) -> list[str] | None:
    """Ancestor names, immediate parent first, root family last (the starting entity itself
    not included — caller already has its own name). Used both for an ordinary language (via
    get_family_path, resolved from its ISO code) and directly for a "group"-level entity
    (a family or macrolanguage, which has no ISO code but does have its own Wikidata QID —
    see build_profile.build_group_profile). None if the entity has no usable P279 edges, or
    the query failed (see run_query — a failure is distinct from a confirmed-empty chain;
    callers must not cache None as "no family tree exists" the same way
    wikidata_lookup.py's writing-system cache doesn't)."""
    query = f"""
    SELECT ?node ?nodeLabel ?isDirectParent ?parent ?parentIsFamily WHERE {{
      {{
        wd:{qid} wdt:P279+ ?node .
        ?node wdt:P31 wd:{_LANGUAGE_FAMILY_QID} .
      }}
      UNION
      {{ wd:{qid} wdt:P279 ?node . }}
      BIND(EXISTS {{ wd:{qid} wdt:P279 ?node }} AS ?isDirectParent)
      OPTIONAL {{
        ?node wdt:P279 ?parent .
        BIND(EXISTS {{ ?parent wdt:P31 wd:{_LANGUAGE_FAMILY_QID} }} AS ?parentIsFamily)
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    bindings = run_query(query)
    if bindings is None:
        return None
    if not bindings:
        return []
    return _reconstruct_path(bindings)


def _reconstruct_path(bindings: list[dict[str, dict[str, str]]]) -> list[str]:
    labels: dict[str, str] = {}
    direct_parents: list[str] = []
    parents_of: dict[str, list[tuple[str, bool]]] = {}

    for row in bindings:
        node_id = row["node"]["value"].rsplit("/", 1)[-1]
        labels[node_id] = row["nodeLabel"]["value"]
        if row.get("isDirectParent", {}).get("value") == "true" and node_id not in direct_parents:
            direct_parents.append(node_id)
        if "parent" in row:
            parent_id = row["parent"]["value"].rsplit("/", 1)[-1]
            is_family = row.get("parentIsFamily", {}).get("value") == "true"
            parents_of.setdefault(node_id, []).append((parent_id, is_family))

    if not direct_parents:
        return []

    path: list[str] = []
    seen: set[str] = set()
    current = direct_parents[0]
    for _ in range(_MAX_HOPS):
        if current not in labels or current in seen:
            break
        path.append(labels[current])
        seen.add(current)
        next_edges = parents_of.get(current, [])
        if not next_edges:
            break
        current = _prefer_family_tagged(next_edges)
    return path


def _prefer_family_tagged(edges: list[tuple[str, bool]]) -> str:
    """Picks one parent when a node has more than one P279 edge — prefers a Q25295-tagged
    ("instance of: language family") one, falling back to whichever Wikidata returned first."""
    family_tagged = [node_id for node_id, is_family in edges if is_family]
    return family_tagged[0] if family_tagged else edges[0][0]


def _find_entity_qid(iso639_3: str) -> str | None:
    bindings = run_query(f'SELECT ?lang WHERE {{ ?lang wdt:P220 "{iso639_3}" . }} LIMIT 1')
    if not bindings:
        return None
    return bindings[0]["lang"]["value"].rsplit("/", 1)[-1]
