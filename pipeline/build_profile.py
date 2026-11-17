"""Merges WALS + PHOIBLE + Glottolog geography + URIEL/lang2vec vectors + Wikidata (writing
system, deep family tree, grammatical case/tense/mood/aspect) into one LanguageProfile per
requested ISO 639-3 code.

Deliberately does not hardcode any language's Glottocode/family/features — everything is
looked up from the downloaded source tables / queried from lang2vec/Wikidata at build time,
by ISO 639-3 code.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline import uriel_vectors
from pipeline.glottolog_loader import GlottologGeoData
from pipeline.phoible_loader import PhoibleData
from pipeline.schema import (
    Classification,
    ClassificationNode,
    Geography,
    LanguageProfile,
    MorphologyData,
    PhonemeInventory,
    Script,
    SyntaxData,
    TenseAspectCategory,
    WordOrderFeature,
    WritingSystem,
)
from pipeline.wals_loader import WalsData
from pipeline.wikidata_family_tree import FamilyTreeCache, get_family_path_from_qid
from pipeline.wikidata_lookup import WikidataPropertyCache, script_type_for

# For WALS's own code text (e.g. "Logographic", "Syllabic", "Alphabetic") — the descriptive
# word IS the type here, unlike Wikidata's "<script family> script/alphabet" labels, where the
# suffix word is generic and wikidata_lookup.script_type_for's family-name matching is used
# instead (see _build_writing_system).
_WALS_SCRIPT_TYPE_KEYWORDS: dict[str, str] = {
    "alphabet": "alphabet",
    "syllabary": "syllabary",
    "syllabic": "syllabary",
    "logographic": "logographic",
    "ideographic": "logographic",
    "abjad": "abjad",
    "consonantal": "abjad",
    "featural": "featural",
}


@dataclass
class WikidataCaches:
    """Bundles the per-property-kind Wikidata caches so build_profile doesn't need five
    separate parameters — see wikidata_lookup.WikidataPropertyCache."""

    writing_system: WikidataPropertyCache
    grammatical_case: WikidataPropertyCache
    tense: WikidataPropertyCache
    mood: WikidataPropertyCache
    aspect: WikidataPropertyCache


def build_profile(
    iso639_3: str,
    wals: WalsData,
    phoible: PhoibleData,
    glottolog: GlottologGeoData,
    wikidata: WikidataCaches,
    family_tree_cache: FamilyTreeCache,
) -> LanguageProfile | None:
    wals_lang = wals.find_language(iso639_3)
    if wals_lang is None:
        return None

    claimed_parameter_ids: set[str] = set()
    classification = _build_classification(wals_lang, iso639_3, family_tree_cache)
    syntax = _build_syntax(wals_lang, wals, iso639_3, claimed_parameter_ids)
    morphology = _build_morphology(wals_lang, wals, iso639_3, wikidata, claimed_parameter_ids)
    writing_system = _build_writing_system(wals_lang, wals, iso639_3, wikidata, claimed_parameter_ids)
    other_features = _build_other_typological_features(wals_lang, wals, claimed_parameter_ids)
    phonology = _build_phonology(iso639_3, phoible)
    geography = _build_geography(wals_lang["Glottocode"], glottolog)
    glottolog_row = glottolog.lookup(wals_lang["Glottocode"])
    glottolog_level = (glottolog_row or {}).get("level") or "language"

    return LanguageProfile(
        glottocode=wals_lang["Glottocode"],
        comparison_kind="leaf",
        glottolog_level=glottolog_level,
        iso639_3=iso639_3,
        name=wals_lang["Name"],
        english_name=wals_lang["Name"],
        classification=classification,
        phonology=phonology,
        syntax=syntax,
        morphology=morphology,
        other_typological_features=other_features,
        writing_system=writing_system,
        geography=geography,
    )


def build_group_profile(
    glottocode: str, name: str, wikidata_qid: str, macroarea: str | None, coordinates: tuple[float, float] | None
) -> LanguageProfile:
    """Builds a "group"-level entry — a family or macrolanguage grouping rather than a single
    speakable variety (see schema.LanguageProfile.comparison_kind). Only `classification` is
    populated: there's no single phoneme inventory, word order, or tense system for an entire
    family, so phonology/syntax/morphology/writing_system/lexicon all stay None/empty, same as
    any other leaf profile with no data for a given category — the UI's existing "N of M
    metrics available" disclosure covers this without needing special-case logic.

    For this draft, callers pass the glottocode/name/Wikidata QID/geography directly (see
    run_pipeline.py's _DRAFT_GROUP_ENTITIES) rather than this being driven by a downloaded
    source table the way leaf-language profiles are — scaling to every Glottolog family/every
    ISO 639-3 macrolanguage is future work, not yet needed for a small draft set.
    """
    deep_path = get_family_path_from_qid(wikidata_qid) or []
    nodes = [ClassificationNode(name=n) for n in reversed(deep_path)]
    nodes.append(ClassificationNode(name=name, glottocode=glottocode))
    nodes = _dedupe_consecutive(nodes)
    classification = Classification(path=nodes, genetic_vector=None, path_source="wikidata" if deep_path else "wals")
    geography = Geography(primary_region=macroarea or "Unknown", coordinates=coordinates) if coordinates else None

    return LanguageProfile(
        glottocode=glottocode,
        comparison_kind="group",
        glottolog_level="family",
        iso639_3=None,
        name=name,
        english_name=name,
        classification=classification,
        geography=geography,
    )


def _build_classification(
    wals_lang: dict[str, str], iso639_3: str, family_tree_cache: FamilyTreeCache
) -> Classification:
    genetic_vector = uriel_vectors.get_genetic_vector(iso639_3)
    wals_family = wals_lang.get("Family", "").strip()

    deep_path = family_tree_cache.get(iso639_3) or []
    if deep_path and _root_matches_wals_family(deep_path[-1], wals_family):
        nodes = [ClassificationNode(name=name) for name in reversed(deep_path)]
        nodes.append(ClassificationNode(name=wals_lang["Name"], glottocode=wals_lang["Glottocode"]))
        return Classification(path=_dedupe_consecutive(nodes), genetic_vector=genetic_vector, path_source="wikidata")
    # Wikidata's P279 chain sometimes encodes a disputed/alternative classification scheme
    # alongside the mainstream one (confirmed live: Mandarin's chain ending at "Dené–Caucasian"
    # instead of Sino-Tibetan, Korean's at the disputed "Altaic" hypothesis, French's at an
    # areal "Southern European language" tag rather than Indo-European) — if the climbed
    # root doesn't match WALS's own (typologist-curated) top-level Family, the whole chain is
    # not trusted, not just its root: falls back to WALS's shallower-but-reliable 3 levels.
    # (This can also reject a Wikidata chain that was actually fine, just differently named —
    # confirmed live: Japanese's Wikidata root "Japonic" vs. WALS's "Japanese" — in which case
    # this fallback below, after dedup, isn't wrong, just less detailed.)

    path: list[ClassificationNode] = []
    for key in ("Family", "Subfamily", "Genus"):
        value = wals_lang.get(key, "").strip()
        if value:
            path.append(ClassificationNode(name=value))
    path.append(ClassificationNode(name=wals_lang["Name"], glottocode=wals_lang["Glottocode"]))
    return Classification(path=_dedupe_consecutive(path), genetic_vector=genetic_vector, path_source="wals")


def _dedupe_consecutive(nodes: list[ClassificationNode]) -> list[ClassificationNode]:
    """Collapses consecutive same-name entries — confirmed live two different ways: (1)
    Japanese's Wikidata chain produced ["Japanese", "Japanese", "Japanese"] (three different
    entities sharing one English label, which the tree-walk's cycle guard — keyed on entity
    ID, not display label — doesn't catch), and (2) WALS's own data for Japanese has
    Family="Japanese", Genus="Japanese", Name="Japanese" all identical. A path like
    [X, X, X, leaf] is never a meaningful display regardless of why the duplication
    happened, so collapsing it is always safe. Keeps a glottocode from whichever node in a
    collapsed run has one (only ever the leaf), rather than dropping it."""
    result: list[ClassificationNode] = []
    for node in nodes:
        if result and result[-1].name == node.name:
            if node.glottocode and not result[-1].glottocode:
                result[-1] = node
            continue
        result.append(node)
    return result


def _root_matches_wals_family(wikidata_root: str, wals_family: str) -> bool:
    """Loose match (case-insensitive, either containing the other) — Wikidata and WALS don't
    always format a family name identically (e.g. "Afro-Asiatic" vs "Afroasiatic")."""
    if not wals_family:
        return True  # nothing to validate against (WALS had no Family value) — trust Wikidata
    a, b = wikidata_root.lower().replace("-", ""), wals_family.lower().replace("-", "")
    return a in b or b in a


def _build_syntax(
    wals_lang: dict[str, str], wals: WalsData, iso639_3: str, claimed: set[str]
) -> SyntaxData | None:
    rows = wals.values_for(wals_lang["ID"], name_contains=("order of",))
    claimed.update(row["Parameter_ID"] for row in rows)
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


def _build_morphology(
    wals_lang: dict[str, str], wals: WalsData, iso639_3: str, wikidata: WikidataCaches, claimed: set[str]
) -> MorphologyData | None:
    # WALS tense/aspect/case parameters: typological signals (does this language mark this
    # category, and how), not a literal enumeration — that's what the Wikidata lookups below
    # add (e.g. German's actual 4 named cases, not just "has case marking: yes").
    rows = wals.values_for(wals_lang["ID"], name_contains=("tense", "aspect", "perfect", "case"))
    claimed.update(row["Parameter_ID"] for row in rows)
    categories = [
        TenseAspectCategory(wals_code=row["Parameter_ID"], name=wals.param_name(row["Parameter_ID"]))
        for row in rows
    ]
    grammatical_cases = wikidata.grammatical_case.get(iso639_3)
    tenses = wikidata.tense.get(iso639_3)
    moods = wikidata.mood.get(iso639_3)
    aspects = wikidata.aspect.get(iso639_3)
    if not categories and not grammatical_cases and not tenses and not moods and not aspects:
        return None
    return MorphologyData(
        tense_aspect_categories=categories,
        grammatical_cases=grammatical_cases,
        tenses=tenses,
        moods=moods,
        aspects=aspects,
    )


def _build_writing_system(
    wals_lang: dict[str, str], wals: WalsData, iso639_3: str, wikidata: WikidataCaches, claimed: set[str]
) -> WritingSystem | None:
    """A language can genuinely use more than one script (see schema.WritingSystem) — merges
    WALS's single coded value (if any) with Wikidata's full list (confirmed live: Japanese has
    4 distinct Wikidata-tagged scripts, Levantine Arabic has Arabic/Latin/Hebrew), deduped by
    name, WALS first when both have data."""
    rows = wals.values_for(wals_lang["ID"], name_contains=("writing system",))
    claimed.update(row["Parameter_ID"] for row in rows)

    scripts: list[Script] = []
    seen_names: set[str] = set()
    if rows:
        code_text = wals.code_name(rows[0]["Code_ID"]) if rows[0]["Code_ID"] else rows[0]["Value"]
        scripts.append(Script(name=code_text, script_type=_wals_script_type(code_text), source="wals"))
        seen_names.add(code_text)

    for name in wikidata.writing_system.get(iso639_3):
        if name in seen_names:
            continue
        seen_names.add(name)
        scripts.append(Script(name=name, script_type=script_type_for(name), source="wikidata"))

    if not scripts:
        return None
    return WritingSystem(scripts=scripts)


def _wals_script_type(code_text: str) -> str:
    lowered = code_text.lower()
    return next((t for keyword, t in _WALS_SCRIPT_TYPE_KEYWORDS.items() if keyword in lowered), "other")


def _build_other_typological_features(
    wals_lang: dict[str, str], wals: WalsData, claimed: set[str]
) -> list[WordOrderFeature]:
    """Every WALS value for this language whose Parameter_ID wasn't already claimed by
    syntax/morphology/writing_system above — WALS has 192 parameters total; this is the
    remainder (case-marking details beyond the headline count, numeral classifiers,
    reduplication, politeness distinctions, etc.)."""
    all_rows = wals.all_values_for(wals_lang["ID"])
    return [
        WordOrderFeature(
            wals_code=row["Parameter_ID"],
            name=wals.param_name(row["Parameter_ID"]),
            value=wals.code_name(row["Code_ID"]) if row["Code_ID"] else row["Value"],
        )
        for row in all_rows
        if row["Parameter_ID"] not in claimed
    ]


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
