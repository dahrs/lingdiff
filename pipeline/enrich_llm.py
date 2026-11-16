"""Scoped LLM enrichment: (a) a short grounded "notable features" blurb per language, and
(b) writing-system classification as a last-resort fallback when WALS and Wikidata both have
no writing-system record. Grounded in a fetched Wikipedia extract + the structured facts
already gathered — never left to the model's unaided memory. Offline-only, cached, resumable
(see checkpoint.py / the per-language cache below), called via claude_cli_client so it draws
on a Claude subscription rather than needing a separate ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import requests

from pipeline.claude_cli_client import complete_via_claude_cli
from pipeline.schema import LanguageProfile
from pipeline.wikidata_sparql import USER_AGENT, query_with_macrolanguage_fallback

log = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_VALID_SCRIPT_TYPES = {"alphabet", "abjad", "abugida", "syllabary", "logographic", "featural", "other"}

_SYSTEM_PROMPT = (
    "You are a linguistics research assistant. You answer using ONLY the facts and text "
    "given to you in the user's message — never general knowledge you weren't given here. "
    "Reply with ONLY a single JSON object, no prose, no code fences, matching exactly this "
    'shape: {"notable_features": "2-3 plain-language sentences about this language\'s most '
    'distinctive features", "writing_system_script_name": string or null, '
    '"writing_system_script_type": one of "alphabet"/"abjad"/"abugida"/"syllabary"/'
    '"logographic"/"featural"/"other", or null}. Set both writing_system fields to null if '
    "the writing system isn't determinable from the given text."
)


class LlmEnrichmentCache:
    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._cache: dict[str, dict[str, str | None]] = {}
        if cache_path.exists():
            self._cache = json.loads(cache_path.read_text())

    def get(self, iso639_3: str) -> dict[str, str | None] | None:
        return self._cache.get(iso639_3)

    def set(self, iso639_3: str, result: dict[str, str | None]) -> None:
        self._cache[iso639_3] = result
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache, indent=2))


def find_wikipedia_title(iso639_3: str) -> str | None:
    """The English Wikipedia article title for this language, via its Wikidata sitelink —
    precise (no search-ranking ambiguity). Falls back through the language's P279 ("subclass
    of") ancestors when its own Wikidata item has no sitelink (see
    wikidata_sparql.query_with_macrolanguage_fallback's docstring — e.g. ISO 639-3 "arb"
    (Standard Arabic) has no enwiki article of its own; Wikipedia's actual "Arabic" coverage
    sits on the macrolanguage-coded parent item one P279 hop up)."""
    pattern = "?article schema:about ?entity . ?article schema:isPartOf <https://en.wikipedia.org/> ."
    bindings = query_with_macrolanguage_fallback(iso639_3, pattern, select_var="article")
    # None (query failed) and [] (confirmed no article) are both "can't enrich this language
    # right now" here — safe to collapse, unlike wikidata_lookup.py's cache: run_pipeline.py
    # only caches a *successful* enrich() result, never a None title, so a transient failure
    # here naturally gets retried on the next full pipeline run rather than being baked in.
    if not bindings:
        return None
    return bindings[0]["article"]["value"].rsplit("/", 1)[-1]


def fetch_wikipedia_extract(title: str) -> str | None:
    try:
        response = requests.get(
            _WIKIPEDIA_SUMMARY_API.format(title=title),
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException:
        log.warning("Wikipedia summary fetch failed for %s", title, exc_info=True)
        return None
    extract: str | None = response.json().get("extract")
    return extract


def enrich(profile: LanguageProfile, wikipedia_extract: str) -> dict[str, str | None] | None:
    """One `claude -p` call grounded in `wikipedia_extract` + the already-gathered structured
    facts. Returns None (logged) if the reply can't be parsed as the expected JSON shape —
    this is a best-effort enrichment layer, not something worth crashing a broad batch run
    over for one language's malformed reply."""
    needs_writing_system = profile.writing_system is None
    prompt = (
        f"Language: {profile.name} (ISO 639-3: {profile.iso639_3})\n\n"
        f"Known structured facts:\n{_summarize_known_facts(profile)}\n\n"
        f"Wikipedia extract:\n{wikipedia_extract}\n\n"
        "Report a notable-features summary"
        + (" and classify its writing system" if needs_writing_system else " (writing system is already known, so set both writing_system fields to null)")
        + "."
    )
    completion = complete_via_claude_cli(prompt, system=_SYSTEM_PROMPT, model=_MODEL)
    result = _parse_reply(completion.content)
    if result is None:
        log.warning("could not parse LLM enrichment reply for %s: %r", profile.iso639_3, completion.content[:300])
    return result


def _summarize_known_facts(profile: LanguageProfile) -> str:
    lines = [f"- Family classification: {' > '.join(n.name for n in profile.classification.path)}"]
    if profile.phonology and profile.phonology.phonemes:
        lines.append(f"- Phoneme inventory size: {len(profile.phonology.phonemes)}")
    if profile.syntax and profile.syntax.features:
        order = next((f.value for f in profile.syntax.features if "Subject, Object and Verb" in f.name), None)
        if order:
            lines.append(f"- Basic word order: {order}")
    if profile.morphology and profile.morphology.tense_aspect_categories:
        lines.append(f"- Marks {len(profile.morphology.tense_aspect_categories)} WALS tense/aspect categories")
    return "\n".join(lines)


def _parse_reply(content: str) -> dict[str, str | None] | None:
    cleaned = _JSON_FENCE_RE.sub("", content.strip()).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "notable_features" not in parsed:
        return None
    script_type = parsed.get("writing_system_script_type")
    if script_type is not None and script_type not in _VALID_SCRIPT_TYPES:
        script_type = None
    return {
        "notable_features": parsed.get("notable_features"),
        "writing_system_script_name": parsed.get("writing_system_script_name"),
        "writing_system_script_type": script_type,
    }
