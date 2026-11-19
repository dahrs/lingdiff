"""Pydantic schema for the per-language profile written to data/languages/<glottocode>.json.

`glottocode` (not ISO 639-3) is the universal identifier here: Glottolog assigns a code at
every level of its classification — leaf languages, dialects, *and* family-level groupings —
while ISO 639-3 only covers (macro)languages and some dialects, leaving no code at all for a
node like "Romance" or "Italic". That universality is what lets a `LanguageProfile` represent
either a single speakable variety (Spanish, Levantine Arabic, Standard Arabic) or an aggregate
group (Romance, the Arabic macrolanguage) — see `comparison_kind` below.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ClassificationNode(BaseModel):
    name: str
    glottocode: str | None = None
    """None when this node is sourced from WALS's shallow Family/Subfamily/Genus columns,
    which don't carry Glottolog codes for intermediate levels — see Classification.path_source."""


class Classification(BaseModel):
    """Root-to-leaf genealogical path, e.g. Indo-European -> Romance -> Iberian Romance ->
    West Iberian -> Spanish."""

    path: list[ClassificationNode]
    genetic_vector: list[float] | None = None
    """URIEL genetic feature vector, when lang2vec has an entry for this language — the actual
    basis for genetic DISTANCE SCORING. `path` below is for human-readable display only and
    never feeds the score."""
    path_source: Literal["wikidata", "wals"] = "wals"
    """"wikidata": the real multi-level chain, walked via Wikidata's P279 ("subclass of")
    edges filtered to items tagged "instance of: language family" (Q25295) — see
    wikidata_family_tree.py. "wals": fallback when Wikidata has no usable chain — WALS's own
    3-level Family/Subfamily/Genus columns, shallower but always present for any WALS-covered
    language."""


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
    tense_aspect_categories: list[TenseAspectCategory] = []
    """WALS tense/aspect-related parameters — typological signals (does this language mark
    this category at all, and how), not a literal enumeration of every tense."""
    grammatical_cases: list[str] = []
    """From Wikidata P2989 "has grammatical case" — an actual named enumeration (e.g. German:
    nominative/accusative/dative/genitive), unlike WALS's case-related parameters below which
    only give a typological count/strategy. Cross-checked against WALS's own "Number of Cases"
    (49A) and related parameters, which land in other_typological_features."""
    tenses: list[str] = []
    """From Wikidata P3103 "has tense" — a named list, e.g. present/preterite/future."""
    moods: list[str] = []
    """From Wikidata P3161 "has grammatical mood"."""
    aspects: list[str] = []
    """From Wikidata P7486 "grammatical aspect"."""


class WordlistEntry(BaseModel):
    concept: str
    """ASJP core-concept label, e.g. 'water', 'mother'."""
    word: str


class LexicalData(BaseModel):
    wordlist: list[WordlistEntry]
    """ASJP 40-item core vocabulary."""


class Script(BaseModel):
    name: str
    script_type: str
    """One of: alphabet, abjad, abugida, syllabary, logographic, featural, other."""
    sample_glyphs: list[str] = []
    source: str
    """One of: wikidata, wals, llm."""


class WritingSystem(BaseModel):
    scripts: list[Script]
    """A language can genuinely use more than one script — not a data gap to collapse to
    "pick one": Japanese routinely uses hiragana+katakana+kanji together, and several Arabic
    varieties are tagged with both the Arabic script and an informal Latin-based "chat
    alphabet"/romanization (confirmed live: Levantine Arabic's Wikidata entry lists Arabic,
    Latin, *and* Hebrew scripts). Always non-empty when this field is present at all."""


class Geography(BaseModel):
    primary_region: str
    coordinates: tuple[float, float] | None = None
    """(lat, lon), from Glottolog. Context only, not scored."""


class NotableFeatures(BaseModel):
    text: str
    """Short grounded prose blurb, LLM-generated offline from fetched Wikipedia text + structured facts."""
    source: str = "llm"


class DonorLanguageShare(BaseModel):
    name: str
    glottocode: str | None = None
    """Known only when the source gives a Glottolog code directly (WOLD does) or the donor
    language's name could be cross-referenced against our own WALS-keyed dataset (etymology-db
    gives only a free-text name, no code — see pipeline/etymology_db_loader.py)."""
    count: int
    percentage: float
    """Share of this language's SAMPLED borrowed words attributed to this donor, 0-100."""


class VocabularyOrigin(BaseModel):
    borrowed_ratio: float
    """0-1: estimated share of vocabulary that is borrowed rather than inherited/native-formed.
    From WOLD: mean of its graded Borrowed_score (already a continuous 0-1 scale per word,
    not binary) across every sampled word. From etymology-db: count of borrowing-type
    relations / (borrowing-type + inherited_from relation count) — see
    pipeline/vocabulary_origin.py for exactly which of etymology-db's 31 relation types count
    as which."""
    donor_languages: list[DonorLanguageShare]
    """Breakdown of borrowed vocabulary by source language, sorted by descending share."""
    sample_size: int
    """How many words this estimate is based on — WOLD's fixed ~1,000-2,000-word list for
    that language, or however many etymology-db rows had a direct origin classification for
    it. A ratio based on a handful of words is far less reliable than one based on hundreds;
    exposed so the UI can disclose that rather than presenting every ratio with equal
    confidence."""
    source: Literal["wold", "etymology_db"]
    """WOLD preferred when it covers this language (expert-curated, graded score, Glottolog-
    coded donor languages, only 41 languages total) — see pipeline/vocabulary_origin.py.
    etymology_db is the broader-coverage (thousands of languages, extremely uneven depth),
    automatically-Wiktionary-parsed fallback used when WOLD has nothing for this language."""


class LanguageProfile(BaseModel):
    glottocode: str
    comparison_kind: Literal["leaf", "group"]
    """"leaf": a single speakable variety with its own phonology/syntax/morphology/lexicon —
    built from WALS/PHOIBLE/Wikidata the same way regardless of whether Glottolog calls it a
    "language" or a "dialect" (e.g. Spanish, Levantine Arabic, and Standard Arabic are all
    "leaf", and are siblings, not parent/child, under the Arabic macrolanguage umbrella).
    "group": an aggregate node (a Glottolog family-level grouping, or an ISO 639-3
    macrolanguage like "ara") with ONLY `classification` populated — there's no single
    phoneme inventory or word order for an entire family/macrolanguage, so every other field
    stays None/empty here, and comparisons involving a "group" entity can only use family
    distance, not phonology/syntax/lexicon/morphology scores. This is what makes "Levantine
    Arabic vs. Italic languages" a valid (if score-limited) comparison alongside "Levantine
    Arabic vs. French"."""
    glottolog_level: str
    """Glottolog's own level label for this node (e.g. "language", "dialect", "family") —
    descriptive metadata only; doesn't by itself determine comparison_kind (the Arabic
    macrolanguage and "Romance" are both Glottolog-level "family", both comparison_kind="group")."""
    iso639_3: str | None = None
    """None for "group" entities and the rare Glottolog leaf with no ISO 639-3 code."""
    name: str
    english_name: str
    classification: Classification
    phonology: PhonemeInventory | None = None
    syntax: SyntaxData | None = None
    morphology: MorphologyData | None = None
    other_typological_features: list[WordOrderFeature] = []
    """Every other WALS parameter not already captured in syntax/morphology/writing_system
    above — WALS has 192 parameters total; this is the remainder (case marking details,
    numeral classifiers, reduplication, politeness distinctions, etc.)."""
    lexicon: LexicalData | None = None
    writing_system: WritingSystem | None = None
    geography: Geography | None = None
    notable_features: NotableFeatures | None = None
    vocabulary_origin: VocabularyOrigin | None = None


class NearestNeighbor(BaseModel):
    glottocode: str
    name: str
    score: int
    """0-100 overall distance, same scale/meaning as the live comparison tool's score."""


class LanguageIndexEntry(BaseModel):
    """One row of the lightweight data/index.json used by the UI's language picker.

    `classification_path` (the same names as LanguageProfile.classification.path, root-first)
    is what lets the picker nest entries under one another — e.g. Levantine/Egyptian Arabic
    indented under the Arabic macrolanguage group, Romanian under the Romance group — by
    finding, for each entry, the other entry whose own path is its longest matching prefix.
    Kept small (names only, no vectors) since every entry's row ships in the one index file
    the picker loads upfront, unlike full profiles which stay lazily fetched.

    `closest`/`farthest` (leaf entries only — see pipeline/nearest_neighbors.py) are
    precomputed at build time specifically so the UI can show them for whichever language is
    selected without an extra fetch: the data's already sitting in this same index file."""

    glottocode: str
    comparison_kind: Literal["leaf", "group"]
    glottolog_level: str
    iso639_3: str | None = None
    name: str
    english_name: str
    family: str
    classification_path: list[str]
    closest: NearestNeighbor | None = None
    farthest: NearestNeighbor | None = None
