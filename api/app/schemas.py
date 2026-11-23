"""Response models for GET /compare — a typed mirror of docs/compare.js's `compareLanguages`
output shape (see app/diff.py), so this API returns exactly the same categories/fields the
website itself computes and renders, just as JSON instead of a rendered page.
"""

from __future__ import annotations

from pydantic import BaseModel


class DiffResult(BaseModel):
    """A shared/only-in-A/only-in-B split of two string lists, plus the Jaccard distance
    between them (0 = identical sets, 1 = no overlap at all). `score` is `None` whenever
    either side had no data to compare at all — not the same as "confirmed zero overlap",
    and callers should treat a `None` score as "not comparable" rather than rendering the
    (possibly one-sided) lists as if they meant something."""

    shared: list[str]
    only_a: list[str]
    only_b: list[str]
    score: float | None


class FamilyResult(BaseModel):
    available: bool
    score: float | None = None
    path_a: list[str] = []
    path_b: list[str] = []
    common_ancestor: str | None = None
    """The deepest classification-path name shared by both languages, or `None` if they share
    no ancestor at all in the data available (in which case `score` is exactly 1.0)."""
    diverge_at_a: str | None = None
    diverge_at_b: str | None = None


class PhonologyResult(BaseModel):
    available: bool
    shared: list[str] = []
    only_a: list[str] = []
    only_b: list[str] = []
    score: float | None = None


class WordOrderRow(BaseModel):
    name: str
    value_a: str | None
    value_b: str | None
    match: bool | None
    """`None` when only one side has a value for this feature at all (nothing to compare)."""


class WordOrderResult(BaseModel):
    available: bool
    rows: list[WordOrderRow] = []
    score: float | None = None


class MorphologyResult(BaseModel):
    available: bool
    cases: DiffResult | None = None
    tenses: DiffResult | None = None
    moods: DiffResult | None = None
    aspects: DiffResult | None = None
    wals_categories: DiffResult | None = None
    score: float | None = None
    """Simple mean of whichever of the five sub-categories above had a score, not weighted."""


class WritingSystemResult(BaseModel):
    available: bool
    shared: list[str] = []
    only_a: list[str] = []
    only_b: list[str] = []
    shared_types: list[str] = []
    """Script types (alphabet/abjad/abugida/syllabary/logographic/featural/other) present on
    both sides, even when no single named script matches exactly."""
    glyphs: DiffResult | None = None
    """Letter-level comparison (Unicode CLDR exemplar characters), when both sides' primary
    script has it — see build_profile.py's attach_sample_glyphs. Takes over as `score` when
    present; far more informative than the name/type match above (two scripts can be named
    completely differently while sharing almost all their letters)."""
    score: float | None = None


class DonorLanguageShare(BaseModel):
    name: str
    glottocode: str | None = None
    count: int
    percentage: float


class VocabularyOriginSummary(BaseModel):
    borrowed_ratio: float
    donor_languages: list[DonorLanguageShare] = []
    sample_size: int
    source: str


class VocabularyOriginResult(BaseModel):
    available: bool
    vocabulary_origin_a: VocabularyOriginSummary | None = None
    vocabulary_origin_b: VocabularyOriginSummary | None = None
    shared: list[str] = []
    only_a: list[str] = []
    only_b: list[str] = []
    score: float | None = None
    """Donor-language overlap only — informational, NOT folded into the overall score (shared
    or different borrowing history is a fact about contact/history, not structural similarity;
    see docs/compare.js's compareVocabularyOrigin docstring)."""


class CategoryResults(BaseModel):
    family: FamilyResult
    phonology: PhonologyResult
    word_order: WordOrderResult
    morphology: MorphologyResult
    writing_system: WritingSystemResult
    vocabulary_origin: VocabularyOriginResult


class OverallResult(BaseModel):
    score: int | None
    """0-100, weighted average of whichever categories had data (family/phonology/word_order/
    morphology/writing_system — vocabulary_origin is never included, see its docstring above),
    re-normalized over just those. `None` only if NEITHER language had data for even one
    weighted category (practically never, since family distance is almost always computable)."""
    available_count: int
    total_count: int


class LanguageSummary(BaseModel):
    glottocode: str
    iso639_3: str | None
    name: str
    english_name: str


class ComparisonResponse(BaseModel):
    language_a: LanguageSummary
    language_b: LanguageSummary
    categories: CategoryResults
    overall: OverallResult
    label: str
    """Qualitative label for `overall.score` ("very close", "close", "moderately different",
    "distant", "very distant"), or "not enough data" when `overall.score` is `None`."""
