"""Merges WALS + PHOIBLE + Glottolog geography + URIEL/lang2vec vectors (Wikidata/LLM
enrichment land in a later pipeline step) into one LanguageProfile per requested ISO 639-3 code.

Deliberately does not hardcode any language's Glottocode/family/features — everything is
looked up from the downloaded source tables / queried from lang2vec at build time, by ISO
639-3 code.
"""

from __future__ import annotations

from pipeline import uriel_vectors
from pipeline.glottolog_loader import GlottologGeoData
from pipeline.phoible_loader import PhoibleData
from pipeline.wikidata_lookup import WikidataWritingSystemCache, script_type_for
from pipeline.schema import (
    Classification,
    ClassificationNode,
    Geography,
    LanguageProfile,
    MorphologyData,
    PhonemeInventory,
    SyntaxData,
    TenseAspectCategory,
    WordOrderFeature,
    WritingSystem,
)
from pipeline.wals_loader import WalsData

_SCRIPT_TYPE_KEYWORDS: dict[str, str] = {
    "alphabet": "alphabet",
    "syllabary": "syllabary",
    "syllabic": "syllabary",
    "logographic": "logographic",
    "ideographic": "logographic",
    "abjad": "abjad",
    "consonantal": "abjad",
    "featural": "featural",
}


def build_profile(
    iso639_3: str,
    wals: WalsData,
    phoible: PhoibleData,
    glottolog: GlottologGeoData,
    wikidata: WikidataWritingSystemCache,
) -> LanguageProfile | None:
    wals_lang = wals.find_language(iso639_3)
    if wals_lang is None:
        return None

    classification = _build_classification(wals_lang, iso639_3)
    syntax = _build_syntax(wals_lang, wals, iso639_3)
    morphology = _build_morphology(wals_lang, wals)
    writing_system = _build_writing_system(wals_lang, wals, iso639_3, wikidata)
    phonology = _build_phonology(iso639_3, phoible)
    geography = _build_geography(wals_lang["Glottocode"], glottolog)

    return LanguageProfile(
        iso639_3=iso639_3,
        glottocode=wals_lang["Glottocode"],
        name=wals_lang["Name"],
        english_name=wals_lang["Name"],
        classification=classification,
        phonology=phonology,
        syntax=syntax,
        morphology=morphology,
        writing_system=writing_system,
        geography=geography,
    )


def _build_classification(wals_lang: dict[str, str], iso639_3: str) -> Classification:
    path: list[ClassificationNode] = []
    for key in ("Family", "Subfamily", "Genus"):
        value = wals_lang.get(key, "").strip()
        if value:
            path.append(ClassificationNode(name=value))
    path.append(ClassificationNode(name=wals_lang["Name"], glottocode=wals_lang["Glottocode"]))
    return Classification(path=path, genetic_vector=uriel_vectors.get_genetic_vector(iso639_3))


def _build_syntax(wals_lang: dict[str, str], wals: WalsData, iso639_3: str) -> SyntaxData | None:
    rows = wals.values_for(wals_lang["ID"], name_contains=("order of",))
    features = [
        WordOrderFeature(
            wals_code=row["Parameter_ID"],
            name=wals.param_name(row["Parameter_ID"]),
            value=wals.code_name(row["Code_ID"]) if row["Code_ID"] else row["Value"],
        )
        for row in rows
    ]
    vector = uriel_vectors.get_syntactic_vector(iso639_3)
    if not features and vector is None:
        return None
    return SyntaxData(features=features, syntactic_vector=vector)


def _build_morphology(wals_lang: dict[str, str], wals: WalsData) -> MorphologyData | None:
    # No dedicated URIEL feature set for tense/aspect specifically (its syntactic vector
    # doesn't isolate this axis) — WALS is the only source here, per the plan.
    rows = wals.values_for(wals_lang["ID"], name_contains=("tense", "aspect", "perfect"))
    if not rows:
        return None
    categories = [
        TenseAspectCategory(wals_code=row["Parameter_ID"], name=wals.param_name(row["Parameter_ID"]))
        for row in rows
    ]
    return MorphologyData(tense_aspect_categories=categories)


def _build_writing_system(
    wals_lang: dict[str, str], wals: WalsData, iso639_3: str, wikidata: WikidataWritingSystemCache
) -> WritingSystem | None:
    rows = wals.values_for(wals_lang["ID"], name_contains=("writing system",))
    if rows:
        row = rows[0]
        code_text = wals.code_name(row["Code_ID"]) if row["Code_ID"] else row["Value"]
        script_type = next(
            (t for keyword, t in _SCRIPT_TYPE_KEYWORDS.items() if keyword in code_text.lower()),
            "other",
        )
        return WritingSystem(script_name=code_text, script_type=script_type, sample_glyphs=[], source="wals")

    scripts = wikidata.get_scripts(iso639_3)
    if not scripts:
        return None
    return WritingSystem(
        script_name=scripts[0],
        script_type=script_type_for(scripts[0]),
        sample_glyphs=[],
        source="wikidata",
    )


def _build_phonology(iso639_3: str, phoible: PhoibleData) -> PhonemeInventory | None:
    result = phoible.phonemes_for(iso639_3)
    phonemes = result[0] if result else []
    inventory_id = int(result[1]) if result else None
    phonological_vector = uriel_vectors.get_phonological_vector(iso639_3)
    inventory_vector = uriel_vectors.get_inventory_vector(iso639_3)
    if not phonemes and phonological_vector is None and inventory_vector is None:
        return None
    return PhonemeInventory(
        phonemes=phonemes,
        source_inventory_id=inventory_id,
        phonological_vector=phonological_vector,
        inventory_vector=inventory_vector,
    )


def _build_geography(glottocode: str, glottolog: GlottologGeoData) -> Geography | None:
    row = glottolog.lookup(glottocode)
    if row is None or not row.get("latitude") or not row.get("longitude"):
        return None
    return Geography(
        primary_region=row.get("macroarea", "") or "Unknown",
        coordinates=(float(row["latitude"]), float(row["longitude"])),
    )
