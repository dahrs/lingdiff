"""Standalone backfill: adds vocabulary_origin to every already-built docs/data/languages/
*.json profile, without rebuilding anything else about them (no WALS/PHOIBLE/Wikidata/LLM
calls — those are untouched). Written to run *after* the main pipeline build (which doesn't
yet gather vocabulary-origin data mid-run) rather than as part of it, specifically so it
doesn't need to interrupt or wait for a long-running `run_pipeline.py` invocation — see the
project's own notes on this from 2026-11-17: the full build already takes the better part of
a day given Wikidata's endpoint instability, and vocabulary-origin data (WOLD/etymology-db,
entirely separate sources, no Wikidata involved) has nothing to do with the rest of that
cost.

`build_profile.py`'s own `VocabularySources` plumbing means a FUTURE full `run_pipeline.py`
run will gather this from the start, same as everything else — this script exists only to
backfill profiles that were already built before that was wired in, or that were built
without `VocabularySources` for cheapness of resumability. **Safe to run repeatedly, at any
point, including while `run_pipeline.py` is still running elsewhere** — each ISO code in
`run_pipeline.py`'s sweep is visited exactly once; if a file already exists on disk, that
language's own build already finished and won't be touched again this run, so there's no
race condition in this script also updating it. Run it again later to catch languages the
main build has added since."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.etymology_db_loader import EtymologyDbData
from pipeline.fetch_vocabulary_sources import fetch_all
from pipeline.iso_language_codes import build_name_to_iso3
from pipeline.schema import LanguageProfile
from pipeline.vocabulary_origin import build_vocabulary_origin
from pipeline.wals_loader import WalsData
from pipeline.wold_loader import WoldData

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
_LANGUAGES_DIR = _REPO_ROOT / "docs" / "data" / "languages"


def main() -> None:
    fetch_all()
    wals = WalsData(_RAW_DIR)
    wold = WoldData(_RAW_DIR)
    etymology_db = EtymologyDbData(_RAW_DIR)
    name_to_iso3 = build_name_to_iso3(_RAW_DIR)

    profile_paths = sorted(_LANGUAGES_DIR.glob("*.json"))
    updated, no_data, skipped_group = 0, 0, 0

    for path in profile_paths:
        raw = json.loads(path.read_text())
        if raw.get("comparison_kind") != "leaf" or not raw.get("iso639_3"):
            skipped_group += 1
            continue

        vocabulary_origin = build_vocabulary_origin(raw["iso639_3"], wold, etymology_db, wals, name_to_iso3)
        if vocabulary_origin is None:
            no_data += 1
            continue

        profile = LanguageProfile.model_validate(raw)
        profile.vocabulary_origin = vocabulary_origin
        path.write_text(profile.model_dump_json(indent=2, exclude_none=True))
        updated += 1

    print(f"Backfilled vocabulary_origin for {updated}/{len(profile_paths)} profiles.")
    print(f"  {no_data} leaf languages had no data in either source.")
    print(f"  {skipped_group} were group entities (not applicable).")
    print("Rerun this script again once run_pipeline.py has built more languages, or after a full rerun.")


if __name__ == "__main__":
    main()
