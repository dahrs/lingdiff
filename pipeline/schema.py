"""Pydantic schema for the per-language profile written to data/languages/<code>.json."""

from __future__ import annotations

from pydantic import BaseModel


class ClassificationNode(BaseModel):
    name: str
    glottocode: str | None = None
    """None for intermediate tree nodes (family/genus) — WALS's classification columns don't
    carry Glottolog codes for those, only for the leaf language itself."""


class Classification(BaseModel):
    """Root-to-leaf genealogical path, e.g. Indo-European -> Romance -> Ibero-Romance -> Spanish."""

    path: list[ClassificationNode]
    genetic_vector: list[float] | None = None
    """URIEL genetic feature vector, when lang2vec has an entry for this language."""


class PhonemeInventory(BaseModel):
    phonemes: list[str]
    """IPA symbols, from PHOIBLE."""
    source_inventory_id: int | None = None
    phonological_vector: list[float] | None = None
    """URIEL "phonology_knn" vector — overall sound-system typology (tone, stress, etc.)."""
    inventory_vector: list[float] | None = None
    """URIEL "inventory_knn" vector — presence/absence of specific common phonemes."""


class WordOrderFeature(BaseModel):
    wals_code: str
    name: str
    value: str


class SyntaxData(BaseModel):
    features: list[WordOrderFeature]
    syntactic_vector: list[float] | None = None
    """URIEL syntactic feature vector."""


class TenseAspectCategory(BaseModel):
    wals_code: str
    name: str


class MorphologyData(BaseModel):
    tense_aspect_categories: list[TenseAspectCategory]


class WordlistEntry(BaseModel):
    concept: str
    """ASJP core-concept label, e.g. 'water', 'mother'."""
    word: str


class LexicalData(BaseModel):
    wordlist: list[WordlistEntry]
    """ASJP 40-item core vocabulary."""


class WritingSystem(BaseModel):
    script_name: str
    script_type: str
    """One of: alphabet, abjad, abugida, syllabary, logographic, featural, other."""
    sample_glyphs: list[str]
    source: str
    """One of: wikidata, wals, llm."""


class Geography(BaseModel):
    primary_region: str
    coordinates: tuple[float, float] | None = None
    """(lat, lon), from URIEL's geographic vector source data. Context only, not scored."""


class NotableFeatures(BaseModel):
    text: str
    """Short grounded prose blurb, LLM-generated offline from fetched Wikipedia text + structured facts."""
    source: str = "llm"


class LanguageProfile(BaseModel):
    iso639_3: str
    glottocode: str
    name: str
    english_name: str
    classification: Classification
    phonology: PhonemeInventory | None = None
    syntax: SyntaxData | None = None
    morphology: MorphologyData | None = None
    lexicon: LexicalData | None = None
    writing_system: WritingSystem | None = None
    geography: Geography | None = None
    notable_features: NotableFeatures | None = None


class LanguageIndexEntry(BaseModel):
    """One row of the lightweight data/index.json used by the UI's language picker."""

    iso639_3: str
    name: str
    english_name: str
    family: str
