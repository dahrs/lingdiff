"""CLI entrypoint for the draft build: fetch sources, build a LanguageProfile per leaf ISO
code below (WALS/PHOIBLE/Glottolog/URIEL/Wikidata) plus a handful of "group"-level
family/macrolanguage entries, run leaf profiles through the scoped LLM-enrichment step, and
write data/languages/<glottocode>.json + data/index.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline.build_profile import WikidataCaches, build_group_profile, build_profile
from pipeline.checkpoint import Checkpoint
from pipeline.enrich_llm import LlmEnrichmentCache, enrich, fetch_wikipedia_extract, find_wikipedia_title
from pipeline.fetch_sources import fetch_all
from pipeline.glottolog_loader import GlottologGeoData
from pipeline.phoible_loader import PhoibleData
from pipeline.schema import LanguageIndexEntry, LanguageProfile, NotableFeatures, WritingSystem
from pipeline.wals_loader import WalsData
from pipeline.wikidata_family_tree import FamilyTreeCache
from pipeline.wikidata_lookup import WikidataPropertyCache

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
# Pipeline *output* lives under docs/ (not top-level data/) because GitHub Pages only serves
# files inside its configured source folder — see README.md's "Data pipeline" section.
_LANGUAGES_DIR = _REPO_ROOT / "docs" / "data" / "languages"
_INDEX_PATH = _REPO_ROOT / "docs" / "data" / "index.json"
_CHECKPOINT_PATH = _REPO_ROOT / "data" / "sources" / "pipeline_checkpoint.json"

# A deliberately small draft set — broad coverage is a later pipeline increment (see the
# plan's build order) once this smaller set has been reviewed. Includes two Arabic
# macrolanguage siblings (apc, arz) alongside Standard Arabic (arb) specifically to exercise
# the "compare across all levels" design: they're siblings, not dialects of arb, per
# Glottolog (confirmed live: both Glottolog-level "language", Family_ID=afro1255, no
# Language_ID pointing at Standard Arabic's glottocode) — see schema.py's comparison_kind docs.
_SMOKE_TEST_ISO_CODES = [
    "spa", "ita", "fra", "por", "ron",
    "eng", "deu", "nld", "swe", "isl",
    "rus", "pol", "ces",
    "cmn", "jpn", "kor",
    "arb", "apc", "arz", "heb", "hin", "tur", "fin", "ell", "eus", "swa", "zul",
]

# "group"-level entries (family/macrolanguage, no ISO code, no WALS/PHOIBLE coverage of their
# own — see build_profile.build_group_profile). Hardcoded for this draft rather than swept
# from Glottolog's full languoid table — that table (27k rows) isn't fetched yet; worth adding
# once we're scaling past the draft set. Glottocode/geography verified live against
# glottolog-cldf's languages.csv; Wikidata QIDs verified live against query.wikidata.org.
_DRAFT_GROUP_ENTITIES = [
    # (glottocode, name, wikidata_qid, macroarea, (lat, lon))
    ("roma1334", "Romance", "Q19814", "Eurasia", (41.588280773333345, 12.532342982000023)),
    ("ital1284", "Italic", "Q131848", "Eurasia", (42.99937193700613, 6.166917340757963)),
    ("arab1395", "Arabic", "Q13955", "Eurasia", (28.293689418964068, 35.871537655605096)),
]


def main() -> None:
    fetch_all()
    wals = WalsData(_RAW_DIR)
    phoible = PhoibleData(_RAW_DIR)
    glottolog = GlottologGeoData(_RAW_DIR)
    wikidata = WikidataCaches(
        writing_system=WikidataPropertyCache(_RAW_DIR, "writing_system"),
        grammatical_case=WikidataPropertyCache(_RAW_DIR, "grammatical_case"),
        tense=WikidataPropertyCache(_RAW_DIR, "tense"),
        mood=WikidataPropertyCache(_RAW_DIR, "mood"),
        aspect=WikidataPropertyCache(_RAW_DIR, "aspect"),
    )
    family_tree_cache = FamilyTreeCache(_RAW_DIR)
    llm_cache = LlmEnrichmentCache(_RAW_DIR / "llm_enrichment_cache.json")
    checkpoint = Checkpoint(_CHECKPOINT_PATH)
    _LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)

    index_entries: list[LanguageIndexEntry] = []
    missing: list[str] = []

    for iso in _SMOKE_TEST_ISO_CODES:
        profile = build_profile(iso, wals, phoible, glottolog, wikidata, family_tree_cache)
        if profile is None:
            missing.append(iso)
            continue

        _apply_llm_enrichment(profile, llm_cache)
        _write_profile(profile)
        checkpoint.mark_done(profile.glottocode)
        index_entries.append(_to_index_entry(profile))

    for glottocode, name, qid, macroarea, coordinates in _DRAFT_GROUP_ENTITIES:
        group_profile = build_group_profile(glottocode, name, qid, macroarea, coordinates)
        _write_profile(group_profile)
        checkpoint.mark_done(group_profile.glottocode)
        index_entries.append(_to_index_entry(group_profile))

    _INDEX_PATH.write_text(json.dumps([e.model_dump() for e in index_entries], indent=2))

    print(f"Built {len(index_entries)}/{len(_SMOKE_TEST_ISO_CODES) + len(_DRAFT_GROUP_ENTITIES)} profiles.")
    if missing:
        print(f"No WALS entry found for: {', '.join(missing)}")
    for entry in index_entries:
        label = entry.iso639_3 or entry.glottocode
        print(f"  {label} [{entry.comparison_kind}/{entry.glottolog_level}]: {entry.name} ({entry.family})")


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
            script_name=result["writing_system_script_name"],
            script_type=result["writing_system_script_type"],
            sample_glyphs=[],
            source="llm",
        )


if __name__ == "__main__":
    main()
