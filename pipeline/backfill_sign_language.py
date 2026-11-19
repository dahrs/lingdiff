"""One-off backfill: adds `is_sign_language` to every already-built profile JSON (built before
this field existed) and recomputes index.json + the nearest/farthest podiums with the new
modality-aware filtering in nearest_neighbors.py (see its module docstring). Pure local
recomputation, no network calls — only WALS (for each leaf's Genus) is needed, already
downloaded under data/sources/raw/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.build_profile import is_sign_language_for
from pipeline.nearest_neighbors import compute_nearest_neighbors
from pipeline.schema import LanguageIndexEntry, LanguageProfile, NearestNeighbor
from pipeline.wals_loader import WalsData

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
_LANGUAGES_DIR = _REPO_ROOT / "docs" / "data" / "languages"
_INDEX_PATH = _REPO_ROOT / "docs" / "data" / "index.json"


def main() -> None:
    wals = WalsData(_RAW_DIR)

    leaf_profile_dicts: list[tuple[str, dict[str, Any]]] = []
    index_entries: list[LanguageIndexEntry] = []
    sign_language_count = 0

    for path in sorted(_LANGUAGES_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        profile = LanguageProfile.model_validate(raw)

        if profile.iso639_3 is not None:
            wals_lang = wals.find_language(profile.iso639_3)
            genus = wals_lang.get("Genus") if wals_lang is not None else None
            profile.is_sign_language = is_sign_language_for(profile.name, genus)
        else:
            profile.is_sign_language = is_sign_language_for(profile.name)

        if profile.is_sign_language:
            sign_language_count += 1

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

    print(
        f"Backfilled is_sign_language onto {len(index_entries)} profiles "
        f"({sign_language_count} sign languages)."
    )

    print("Recomputing nearest/farthest podiums with modality-aware filtering...")
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
