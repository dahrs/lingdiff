"""Thin wrapper around lang2vec (the URIEL knowledge base's query tool). Uses the "_knn"
feature sets specifically because they're the only ones guaranteed dense (no missing '--'
entries) — the plain/"_average" sets still have per-language gaps where none of URIEL's
underlying source databases (WALS, Ethnologue, PHOIBLE, ...) had data."""

from __future__ import annotations

import logging

import lang2vec.lang2vec as l2v

log = logging.getLogger(__name__)

_MISSING = "--"


def get_vector(iso639_3: str, feature_set: str) -> list[float] | None:
    """Returns the named lang2vec feature vector for one language, or None if lang2vec has
    no entry for this ISO code at all."""
    try:
        features = l2v.get_features([iso639_3], feature_set)
    except Exception:
        # lang2vec raises a bare Exception (not a specific subclass — confirmed in its own
        # source) for any ISO code it doesn't recognize at all, rather than returning an
        # empty result the way it does for a recognized-but-data-sparse language. Confirmed
        # live: crashed a full pipeline run outright on ISO "bpe" with "Note: Language bpe
        # not found in the URIEL database." A language entirely outside URIEL's ~8000-language
        # coverage is an expected, known condition at broad-coverage scale, not a bug — logged
        # and treated the same as "no vector available" rather than crashing the whole run.
        log.info("%s is not in lang2vec/URIEL's language database — no %s vector", iso639_3, feature_set)
        return None
    raw = features.get(iso639_3)
    if raw is None:
        return None
    missing = sum(1 for value in raw if value == _MISSING)
    if missing:
        log.warning("%s unexpectedly has %d/%d missing values in %s", iso639_3, missing, len(raw), feature_set)
    return [float(value) if value != _MISSING else 0.0 for value in raw]


def get_genetic_vector(iso639_3: str) -> list[float] | None:
    return get_vector(iso639_3, "fam")


def get_syntactic_vector(iso639_3: str) -> list[float] | None:
    return get_vector(iso639_3, "syntax_knn")


def get_phonological_vector(iso639_3: str) -> list[float] | None:
    return get_vector(iso639_3, "phonology_knn")


def get_inventory_vector(iso639_3: str) -> list[float] | None:
    return get_vector(iso639_3, "inventory_knn")
