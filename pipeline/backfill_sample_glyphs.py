"""One-off backfill: fetches CLDR exemplar-character data (see fetch_cldr_sources.py),
attaches it to every already-built profile's writing_system (see build_profile.py's
attach_sample_glyphs), re-derives each script's script_type with the corrected
wikidata_lookup.script_type_for (see that function's "alphabet" fallback fix), and
recomputes index.json + the nearest/farthest podiums with the new letter-level writing-system
scoring in pipeline/scoring.py. Pure local recomputation except for the one-time CLDR
download — no LLM/Wikidata/WALS re-fetch needed, everything else is already cached.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.build_profile import attach_sample_glyphs, wals_script_type_for
from pipeline.cldr_loader import CldrData
from pipeline.fetch_cldr_sources import fetch_all as fetch_cldr_sources
from pipeline.nearest_neighbors import compute_nearest_neighbors
from pipeline.schema import LanguageIndexEntry, LanguageProfile, NearestNeighbor
from pipeline.wikidata_lookup import script_type_for

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
_LANGUAGES_DIR = _REPO_ROOT / "docs" / "data" / "languages"
_INDEX_PATH = _REPO_ROOT / "docs" / "data" / "index.json"


def main() -> None:
    fetch_cldr_sources()
    cldr = CldrData(_RAW_DIR)

    leaf_profile_dicts: list[tuple[str, dict[str, Any]]] = []
    index_entries: list[LanguageIndexEntry] = []
    glyphs_attached = 0

    for path in sorted(_LANGUAGES_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        profile = LanguageProfile.model_validate(raw)

        if profile.writing_system is not None:
            for script in profile.writing_system.scripts:
                if script.source == "wikidata":
                    script.script_type = script_type_for(script.name)
                else:
                    script.script_type = wals_script_type_for(script.name)
            if profile.iso639_3 is not None:
                attach_sample_glyphs(profile.writing_system.scripts, profile.iso639_3, cldr)
                if any(s.sample_glyphs for s in profile.writing_system.scripts):
                    glyphs_attached += 1

        path.write_text(profile.model_dump_json(indent=2, exclude_none=True))

        path_names = [node.name for node in profile.classification.path]
        index_entries.append(
            LanguageIndexEntry(
                glottocode=profile.glottocode,
                comparison_kind=profile.comparison_kind,
                glottolog_level=profile.glottolog_level,
                iso639_3=profile.iso639_3,
                name=profile.name,
                english_name=profile.english_name,
                family=path_names[0] if path_names else "Unknown",
                classification_path=path_names,
                is_sign_language=profile.is_sign_language,
            )
        )
        if profile.comparison_kind == "leaf":
            leaf_profile_dicts.append((profile.glottocode, profile.model_dump()))

    print(f"Attached CLDR sample_glyphs to {glyphs_attached}/{len(index_entries)} profiles.")

    print("Recomputing nearest/farthest podiums with letter-level writing-system scoring...")
    neighbors = compute_nearest_neighbors(leaf_profile_dicts)
    for entry in index_entries:
        result = neighbors.get(entry.glottocode)
        if result is None:
            continue
        entry.closest = [NearestNeighbor(**n) for n in result["closest"]]
        entry.farthest = [NearestNeighbor(**n) for n in result["farthest"]]

    _INDEX_PATH.write_text(json.dumps([e.model_dump() for e in index_entries], indent=2))
    print(f"Wrote index.json with {len(index_entries)} entries.")


if __name__ == "__main__":
    main()
