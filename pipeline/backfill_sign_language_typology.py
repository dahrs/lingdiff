"""One-off backfill, scoped to the 40 WALS-listed sign languages only: re-fetches their
Wikidata grammar data (to pick up the newly-added P4132 "linguistic typology" / basic word
order property — see wikidata_lookup.py's module docstring) and rebuilds their profiles so
they also pick up build_profile.py's `_root_matches_wals_family` fix (WALS's Family column is
the placeholder "other" for every sign language, which used to block trusting Wikidata's real,
specific sign-language family chains like "BANZSL"/"French Sign Language family").

Scoped deliberately: these two fixes only affect sign languages (the Family="other" exemption
is genus-gated; P4132 data is sparse for spoken languages, which already have WALS Ch.81 for
word order anyway), so there's no reason to re-fetch or rebuild the other ~2400 profiles. Does
re-touch the full profile set when recomputing index.json's podiums below, since any OTHER
sign language's podium could newly rank one of these 40 differently — but that step is pure
local recomputation, no network calls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pipeline.build_profile import VocabularySources, build_profile
from pipeline.cldr_loader import CldrData
from pipeline.etymology_db_loader import EtymologyDbData
from pipeline.glottolog_loader import GlottologGeoData
from pipeline.iso_language_codes import build_name_to_iso3
from pipeline.nearest_neighbors import compute_nearest_neighbors
from pipeline.phoible_loader import PhoibleData
from pipeline.schema import LanguageIndexEntry, LanguageProfile, NearestNeighbor
from pipeline.wals_loader import WalsData
from pipeline.wikidata_family_tree import FamilyTreeCache
from pipeline.wikidata_lookup import WikidataGrammarCache
from pipeline.wold_loader import WoldData

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RAW_DIR = _REPO_ROOT / "data" / "sources" / "raw"
_LANGUAGES_DIR = _REPO_ROOT / "docs" / "data" / "languages"
_INDEX_PATH = _REPO_ROOT / "docs" / "data" / "index.json"


def main() -> None:
    wals = WalsData(_RAW_DIR)
    phoible = PhoibleData(_RAW_DIR)
    glottolog = GlottologGeoData(_RAW_DIR)
    wikidata = WikidataGrammarCache(_RAW_DIR)
    family_tree_cache = FamilyTreeCache(_RAW_DIR)
    vocabulary_sources = VocabularySources(
        wold=WoldData(_RAW_DIR),
        etymology_db=EtymologyDbData(_RAW_DIR),
        name_to_iso3=build_name_to_iso3(_RAW_DIR),
    )
    cldr = CldrData(_RAW_DIR)

    sign_language_isos = [
        iso
        for iso in wals.all_iso_codes()
        if (wals.find_language(iso) or {}).get("Genus") == "Sign Languages"
    ]
    print(f"Rebuilding {len(sign_language_isos)} sign-language profiles: {sign_language_isos}")

    for iso in sign_language_isos:
        wikidata.invalidate(iso)
        profile = build_profile(
            iso, wals, phoible, glottolog, wikidata, family_tree_cache, vocabulary_sources, cldr
        )
        assert profile is not None
        (_LANGUAGES_DIR / f"{profile.glottocode}.json").write_text(
            profile.model_dump_json(indent=2, exclude_none=True)
        )
        path_names = [node.name for node in profile.classification.path]
        print(f"  {iso} -> {profile.name}: path={path_names}, word_order_features={profile.syntax}")
        time.sleep(0.5)

    print("Rebuilding index.json and nearest/farthest neighbors from the complete profile set...")
    leaf_profile_dicts: list[tuple[str, dict[str, Any]]] = []
    index_entries: list[LanguageIndexEntry] = []
    for path in sorted(_LANGUAGES_DIR.glob("*.json")):
        raw = json.loads(path.read_text())
        profile = LanguageProfile.model_validate(raw)
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
