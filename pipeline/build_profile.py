"""Merges WALS + PHOIBLE (URIEL/Wikidata/LLM enrichment land in later pipeline steps) into
one LanguageProfile per requested ISO 639-3 code.

Deliberately does not hardcode any language's Glottocode/family/features — everything is
looked up from the downloaded source tables at build time, by ISO 639-3 code.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.phoible_loader import PhoibleData
from pipeline.schema import (
    Classification,
    ClassificationNode,
    LanguageProfile,
    PhonemeInventory,
    SyntaxData,
    TenseAspectCategory,
    MorphologyData,
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


def build_profile(iso639_3: str, wals: WalsData, phoible: PhoibleData) -> LanguageProfile | None:
    wals_lang = wals.find_language(iso639_3)
    if wals_lang is None:
        return None

    classification = _build_classification(wals_lang)
    syntax = _build_syntax(wals_lang, wals)
    morphology = _build_morphology(wals_lang, wals)
    writing_system = _build_writing_system(wals_lang, wals)
    phonology = _build_phonology(iso639_3, phoible)

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
    )


def _build_classification(wals_lang: dict[str, str]) -> Classification:
    path: list[ClassificationNode] = []
    for key in ("Family", "Subfamily", "Genus"):
        value = wals_lang.get(key, "").strip()
        if value:
            path.append(ClassificationNode(name=value))
    path.append(ClassificationNode(name=wals_lang["Name"], glottocode=wals_lang["Glottocode"]))
    return Classification(path=path)


def _build_syntax(wals_lang: dict[str, str], wals: WalsData) -> SyntaxData | None:
    rows = wals.values_for(wals_lang["ID"], name_contains=("order of",))
    if not rows:
        return None
    features = [
        WordOrderFeature(
            wals_code=row["Parameter_ID"],
            name=wals.param_name(row["Parameter_ID"]),
            value=wals.code_name(row["Code_ID"]) if row["Code_ID"] else row["Value"],
        )
        for row in rows
    ]
    return SyntaxData(features=features)


def _build_morphology(wals_lang: dict[str, str], wals: WalsData) -> MorphologyData | None:
    rows = wals.values_for(wals_lang["ID"], name_contains=("tense", "aspect", "perfect"))
    if not rows:
        return None
    categories = [
        TenseAspectCategory(wals_code=row["Parameter_ID"], name=wals.param_name(row["Parameter_ID"]))
        for row in rows
    ]
    return MorphologyData(tense_aspect_categories=categories)


def _build_writing_system(wals_lang: dict[str, str], wals: WalsData) -> WritingSystem | None:
    rows = wals.values_for(wals_lang["ID"], name_contains=("writing system",))
    if not rows:
        return None
    row = rows[0]
    code_text = wals.code_name(row["Code_ID"]) if row["Code_ID"] else row["Value"]
    script_type = next(
        (t for keyword, t in _SCRIPT_TYPE_KEYWORDS.items() if keyword in code_text.lower()),
        "other",
    )
    return WritingSystem(
        script_name=code_text,
        script_type=script_type,
        sample_glyphs=[],
        source="wals",
    )


def _build_phonology(iso639_3: str, phoible: PhoibleData) -> PhonemeInventory | None:
    result = phoible.phonemes_for(iso639_3)
    if result is None:
        return None
    phonemes, inventory_id = result
    return PhonemeInventory(phonemes=phonemes, source_inventory_id=int(inventory_id))
