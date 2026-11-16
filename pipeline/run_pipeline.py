"""CLI entrypoint for the smoke-test build: fetch sources, build a LanguageProfile per ISO
code below, write data/languages/<code>.json + data/index.json. No LLM calls at this stage
(URIEL vectors, Wikidata lookups, and LLM enrichment are later pipeline increments)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.build_profile import build_profile
from pipeline.checkpoint import Checkpoint
from pipeline.fetch_sources import fetch_all
from pipeline.glottolog_loader import GlottologGeoData
from pipeline.phoible_loader import PhoibleData
from pipeline.schema import LanguageIndexEntry
from pipeline.wals_loader import WalsData
from pipeline.wikidata_lookup import WikidataWritingSystemCache

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
_LANGUAGES_DIR = _REPO_ROOT / "data" / "languages"
_INDEX_PATH = _REPO_ROOT / "data" / "index.json"
_CHECKPOINT_PATH = _REPO_ROOT / "data" / "sources" / "pipeline_checkpoint.json"

_SMOKE_TEST_ISO_CODES = [
    "spa", "ita", "fra", "por", "ron",
    "eng", "deu", "nld", "swe", "isl",
    "rus", "pol", "ces",
    "cmn", "jpn", "kor",
    "arb", "heb", "hin", "tur", "fin", "ell", "eus", "swa", "zul",
]


def main() -> None:
    fetch_all()
    wals = WalsData(_RAW_DIR)
    phoible = PhoibleData(_RAW_DIR)
    glottolog = GlottologGeoData(_RAW_DIR)
    wikidata = WikidataWritingSystemCache(_RAW_DIR / "wikidata_cache.json")
    checkpoint = Checkpoint(_CHECKPOINT_PATH)
    _LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)

    index_entries: list[LanguageIndexEntry] = []
    missing: list[str] = []

    for iso in _SMOKE_TEST_ISO_CODES:
        profile = build_profile(iso, wals, phoible, glottolog, wikidata)
        if profile is None:
            missing.append(iso)
            continue

        (_LANGUAGES_DIR / f"{iso}.json").write_text(profile.model_dump_json(indent=2, exclude_none=True))
        checkpoint.mark_done(iso)
        family = profile.classification.path[0].name if profile.classification.path else "Unknown"
        index_entries.append(
            LanguageIndexEntry(
                iso639_3=profile.iso639_3,
                name=profile.name,
                english_name=profile.english_name,
                family=family,
            )
        )

    _INDEX_PATH.write_text(json.dumps([e.model_dump() for e in index_entries], indent=2))

    print(f"Built {len(index_entries)}/{len(_SMOKE_TEST_ISO_CODES)} profiles.")
    if missing:
        print(f"No WALS entry found for: {', '.join(missing)}")
    for entry in index_entries:
        print(f"  {entry.iso639_3}: {entry.name} ({entry.family})")


if __name__ == "__main__":
    main()
