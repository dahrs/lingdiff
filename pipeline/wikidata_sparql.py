"""Shared Wikidata SPARQL plumbing used by wikidata_lookup.py and enrich_llm.py."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "lingdiff-pipeline/0.1 (https://github.com/dahrs/lingdiff)"


def run_query(query: str, retries: int = 1) -> list[dict[str, dict[str, str]]] | None:
    """Returns the query's result bindings, [] if it ran successfully but matched nothing, or
    None if it failed after `retries` retries (network error/timeout — the public Wikidata
    endpoint does occasionally time out under load, observed live). Callers must NOT treat
    None the same as [] — a transient failure is not a confirmed empty match, and caching it
    as one would permanently bake in "no data" for a language that actually has some.

    `retries` defaults to 1 (2 attempts, not 3) and the per-attempt timeout to 15s (not 30) —
    tuned down from the original values once building thousands of profiles made the
    worst-case cost of every failed query matter a lot more than it did for a couple dozen;
    a query that's going to fail because of broad endpoint trouble (observed live: sustained
    502s/timeouts) is just as likely to fail on a 3rd attempt as a 2nd, so the extra wait
    mostly adds latency, not reliability, at this scale."""
    for attempt in range(retries + 1):
        try:
            response = requests.get(
                _ENDPOINT, params={"query": query, "format": "json"}, headers={"User-Agent": USER_AGENT}, timeout=15
            )
            response.raise_for_status()
            bindings: list[dict[str, dict[str, str]]] = response.json()["results"]["bindings"]
            return bindings
        except requests.RequestException:
            log.warning("Wikidata query failed (attempt %d/%d)", attempt + 1, retries + 1, exc_info=True)
    return None


def query_with_macrolanguage_fallback(
    iso639_3: str, entity_pattern: str, select_var: str, limit: int = 1
) -> list[dict[str, dict[str, str]]] | None:
    """Tries an ISO 639-3 lookup three ways, in order, stopping at the first that returns a
    confirmed (successfully-queried, non-empty) result: (1) the language's own Wikidata item,
    (2) its direct P279 ("subclass of") parent — covers the common case where a source like
    WALS uses a macrolanguage's individual-variety code but Wikidata's main coverage sits on a
    differently-coded macrolanguage item (e.g. ISO 639-3 "arb"/Standard Arabic vs. Wikidata's
    "ara"-coded main "Arabic" item, confirmed live: Q122602987 P220=arb, P279->Q13955 which is
    P220=ara and holds the real Wikipedia coverage) — then (3) any-depth P279 ancestor as a
    last resort.

    `entity_pattern` is SPARQL WHERE-clause triples using `?entity` as the item to look up
    (e.g. writing system, Wikipedia sitelink); `select_var` is the variable to return.

    Returns None (not []) if any tier's query itself failed (see run_query) — this stops at
    that tier rather than falling through to a broader/less-precise tier on bad information
    (observed live: a timeout on tier 1 silently producing "West Iberian languages" instead of
    "Spanish" from tier 3, which would then get permanently cached as if correct). Callers
    must not cache a None result as "no data".
    """
    tiers = [
        f'?lang wdt:P220 "{iso639_3}" . BIND(?lang AS ?entity) . {entity_pattern}',
        f'?lang wdt:P220 "{iso639_3}" . ?lang wdt:P279 ?entity . {entity_pattern}',
        f'?lang wdt:P220 "{iso639_3}" . ?entity wdt:P279* ?lang . {entity_pattern}',
    ]
    for pattern in tiers:
        query = f"SELECT ?{select_var} WHERE {{ {pattern} }} LIMIT {limit}"
        bindings = run_query(query)
        if bindings is None:
            return None
        if bindings:
            return bindings
    return []


def query_multi_with_macrolanguage_fallback(
    iso639_3: str, entity_pattern: str, select_expressions: list[str], output_vars: list[str]
) -> dict[str, str] | None:
    """Same three-tier fallback as query_with_macrolanguage_fallback, but for a query that
    fetches several GROUP_CONCAT-aggregated properties from ?entity in one round trip instead
    of one query per property — a ~5x reduction in requests per language once several
    properties are needed (see wikidata_lookup.WikidataGrammarCache), which matters a lot at
    broad-coverage scale even though it made no difference for a couple dozen languages.

    `entity_pattern` is the WHERE-clause triples (using `?entity`, with an OPTIONAL block per
    property); `select_expressions` are the full SPARQL aggregation expressions (e.g.
    `'(GROUP_CONCAT(DISTINCT ?tenseLabel; separator="|") AS ?tense)'`), and `output_vars` are
    the resulting bound variable names (`"tense"` above) used to read the response. Each
    OPTIONAL block must join its label via a plain `?x rdfs:label ?xLabel .
    FILTER(LANG(?xLabel)="en")` triple, not the `wikibase:label` SERVICE — confirmed live that
    GROUP_CONCAT over a SERVICE-generated label variable silently returns empty strings on
    this endpoint, while the identical query using an explicit label triple works correctly.

    Returns a {var_name: "value1|value2|..."} dict (empty string where a property had no
    values — still a confirmed result, not missing data), or None if every tier's query
    itself failed, same meaning as the single-variable version.
    """
    tiers = [
        f'?lang wdt:P220 "{iso639_3}" . BIND(?lang AS ?entity) . {entity_pattern}',
        f'?lang wdt:P220 "{iso639_3}" . ?lang wdt:P279 ?entity . {entity_pattern}',
        f'?lang wdt:P220 "{iso639_3}" . ?entity wdt:P279* ?lang . {entity_pattern}',
    ]
    select_clause = " ".join(select_expressions)
    for pattern in tiers:
        query = f"SELECT {select_clause} WHERE {{ {pattern} }} GROUP BY ?entity LIMIT 1"
        bindings = run_query(query)
        if bindings is None:
            return None
        if bindings and any(bindings[0].get(v, {}).get("value") for v in output_vars):
            return {v: bindings[0].get(v, {}).get("value", "") for v in output_vars}
    return {v: "" for v in output_vars}
