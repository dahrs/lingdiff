"""CLI entrypoint for the pipeline build: fetch sources, build a LanguageProfile per leaf
language WALS covers (WALS/PHOIBLE/Glottolog/URIEL/Wikidata) plus a handful of "group"-level
family/macrolanguage entries, run leaf profiles through the scoped LLM-enrichment step, and
write data/languages/<glottocode>.json + data/index.json.

Safe to interrupt and rerun at any point: every expensive step (Wikidata of all kinds,
Wikipedia, LLM) is cached per-language in its own file under data/sources/raw/, independent
of this script's own top-level loop — a rerun re-touches every language but only pays real
(network/LLM) cost for ones that weren't already cached."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pipeline.build_profile import VocabularySources, build_group_profile, build_profile
from pipeline.checkpoint import Checkpoint
from pipeline.enrich_llm import LlmEnrichmentCache, enrich, fetch_wikipedia_extract, find_wikipedia_title
from pipeline.etymology_db_loader import EtymologyDbData
from pipeline.fetch_sources import fetch_all
from pipeline.fetch_vocabulary_sources import fetch_all as fetch_vocabulary_sources
from pipeline.glottolog_loader import GlottologGeoData
from pipeline.iso_language_codes import build_name_to_iso3
from pipeline.nearest_neighbors import compute_nearest_neighbors
from pipeline.phoible_loader import PhoibleData
from pipeline.schema import (
    LanguageIndexEntry,
    LanguageProfile,
    NearestNeighbor,
    NotableFeatures,
    Script,
    WritingSystem,
)
from pipeline.wals_loader import WalsData
from pipeline.wikidata_family_tree import FamilyTreeCache
from pipeline.wikidata_lookup import WikidataGrammarCache
from pipeline.wold_loader import WoldData

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
# Pipeline *output* lives under docs/ (not top-level data/) because GitHub Pages only serves
# files inside its configured source folder — see README.md's "Data pipeline" section.
_LANGUAGES_DIR = _REPO_ROOT / "docs" / "data" / "languages"
_INDEX_PATH = _REPO_ROOT / "docs" / "data" / "index.json"
_CHECKPOINT_PATH = _REPO_ROOT / "data" / "sources" / "pipeline_checkpoint.json"

# "group"-level entries (family/macrolanguage, no ISO code, no WALS/PHOIBLE coverage of their
# own — see build_profile.build_group_profile). Still hardcoded rather than swept from
# Glottolog's full languoid table (27k rows, not fetched yet) — worth automating, but a
# handful of examples is enough to exercise the "compare across levels" design for now.
# Glottocode/geography verified live against glottolog-cldf's languages.csv; Wikidata QIDs
# verified live against query.wikidata.org.
_DRAFT_GROUP_ENTITIES = [
    # (glottocode, name, wikidata_qid, macroarea, (lat, lon))
    ("roma1334", "Romance", "Q19814", "Eurasia", (41.588280773333345, 12.532342982000023)),
    ("ital1284", "Italic", "Q131848", "Eurasia", (42.99937193700613, 6.166917340757963)),
    ("arab1395", "Arabic", "Q13955", "Eurasia", (28.293689418964068, 35.871537655605096)),
]


def main() -> None:
    fetch_all()
    fetch_vocabulary_sources()
    wals = WalsData(_RAW_DIR)
    phoible = PhoibleData(_RAW_DIR)
    glottolog = GlottologGeoData(_RAW_DIR)
    wikidata = WikidataGrammarCache(_RAW_DIR)
    family_tree_cache = FamilyTreeCache(_RAW_DIR)
    vocabulary_sources = VocabularySources(
        wold=WoldData(_RAW_DIR),
        etymology_db=EtymologyDbData(_RAW_DIR),
        name_to_iso3=build_name_to_iso3(_RAW_DIR),
    )
    llm_cache = LlmEnrichmentCache(_RAW_DIR / "llm_enrichment_cache.json")
    checkpoint = Checkpoint(_CHECKPOINT_PATH)
    _LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)

    iso_codes = wals.all_iso_codes()
    index_entries: list[LanguageIndexEntry] = []
    leaf_profile_dicts: list[tuple[str, dict[str, Any]]] = []
    missing: list[str] = []

    total = len(iso_codes)
    for count, iso in enumerate(iso_codes, start=1):
        profile = build_profile(iso, wals, phoible, glottolog, wikidata, family_tree_cache, vocabulary_sources)
        if profile is None:
            missing.append(iso)
            continue

        _apply_llm_enrichment(profile, llm_cache)
        _write_profile(profile)
        checkpoint.mark_done(profile.glottocode)
        index_entries.append(_to_index_entry(profile))
        leaf_profile_dicts.append((profile.glottocode, profile.model_dump()))

        if count % 25 == 0 or count == total:
            print(f"[{count}/{total}] {iso} -> {profile.name}", flush=True)

    for glottocode, name, qid, macroarea, coordinates in _DRAFT_GROUP_ENTITIES:
        group_profile = build_group_profile(glottocode, name, qid, macroarea, coordinates)
        _write_profile(group_profile)
        checkpoint.mark_done(group_profile.glottocode)
        index_entries.append(_to_index_entry(group_profile))

    print(f"Computing nearest/farthest neighbors across {len(leaf_profile_dicts)} leaf languages...", flush=True)
    neighbors = compute_nearest_neighbors(leaf_profile_dicts)
    for entry in index_entries:
        result = neighbors.get(entry.glottocode)
        if result is None:
            continue
        entry.closest = [NearestNeighbor(**n) for n in result["closest"]]
        entry.farthest = [NearestNeighbor(**n) for n in result["farthest"]]

    _INDEX_PATH.write_text(json.dumps([e.model_dump() for e in index_entries], indent=2))

    print(f"\nBuilt {len(index_entries)}/{total + len(_DRAFT_GROUP_ENTITIES)} profiles.")
    if missing:
        # Should be empty by construction (iso_codes comes from wals.all_iso_codes(), the
        # same index build_profile looks up against) — kept as a defensive check, not
        # expected to ever fire.
        print(f"Unexpectedly no WALS entry found for: {', '.join(missing)}")


def _write_profile(profile: LanguageProfile) -> None:
    (_LANGUAGES_DIR / f"{profile.glottocode}.json").write_text(profile.model_dump_json(indent=2, exclude_none=True))


def _to_index_entry(profile: LanguageProfile) -> LanguageIndexEntry:
    path_names = [node.name for node in profile.classification.path]
    family = path_names[0] if path_names else "Unknown"
    return LanguageIndexEntry(
        glottocode=profile.glottocode,
        comparison_kind=profile.comparison_kind,
        glottolog_level=profile.glottolog_level,
        iso639_3=profile.iso639_3,
        name=profile.name,
        english_name=profile.english_name,
        family=family,
        classification_path=path_names,
        is_sign_language=profile.is_sign_language,
    )


def _apply_llm_enrichment(profile: LanguageProfile, llm_cache: LlmEnrichmentCache) -> None:
    """Mutates `profile` in place with the cached/fetched LLM enrichment, if any grounding
    text was found for it. Silently leaves notable_features/writing_system unset (not an
    error) when there's no Wikipedia article to ground the call in, or the reply didn't
    parse — see enrich_llm.py. Only applies to leaf ("comparison_kind=leaf") profiles, which
    are the only ones with an iso639_3 to look up a grounding article by."""
    if profile.iso639_3 is None:
        return
    result = llm_cache.get(profile.iso639_3)
    if result is None:
        title = find_wikipedia_title(profile.iso639_3)
        extract = fetch_wikipedia_extract(title) if title else None
        if extract is None:
            return
        result = enrich(profile, extract)
        if result is None:
            return
        llm_cache.set(profile.iso639_3, result)

    if result.get("notable_features"):
        profile.notable_features = NotableFeatures(text=result["notable_features"])
    if (
        profile.writing_system is None
        and result.get("writing_system_script_name")
        and result.get("writing_system_script_type")
    ):
        profile.writing_system = WritingSystem(
            scripts=[
                Script(
                    name=result["writing_system_script_name"],
                    script_type=result["writing_system_script_type"],
                    source="llm",
                )
            ]
        )


if __name__ == "__main__":
    main()
