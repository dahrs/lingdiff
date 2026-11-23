"""Loads LanguageProfile JSON straight from the same docs/data/ directory the published
GitHub Pages site serves — no network calls, no dependency on the `pipeline` package. This
service is deployed separately from `pipeline/` (same reasoning as ye_olde's search_api not
depending on ye_olde's main package: a much lighter dependency set — this needs only
fastapi/uvicorn/pydantic, not pipeline/'s pycldf/lang2vec/panphon stack), so it reads the
pipeline's *output* directly as plain JSON rather than importing pipeline.schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "data"


class ProfileStore:
    """Resolves a language code (ISO 639-3 or glottocode, case-insensitive) to its profile
    JSON, caching every profile it loads for the lifetime of the process — at ~121MB for the
    full 2444-language dataset, caching everything ever requested is cheap, and most repeat
    requests (the same popular language pairs) hit the cache instead of touching disk again."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _DEFAULT_DATA_DIR
        self._languages_dir = self._data_dir / "languages"
        self._iso_to_glottocode: dict[str, str] = {}
        self._valid_glottocodes: set[str] = set()
        self._profile_cache: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        index: list[dict[str, Any]] = json.loads((self._data_dir / "index.json").read_text())
        for entry in index:
            glottocode = entry["glottocode"]
            self._valid_glottocodes.add(glottocode)
            iso639_3 = entry.get("iso639_3")
            if iso639_3:
                self._iso_to_glottocode[iso639_3.lower()] = glottocode

    def resolve(self, code: str) -> str | None:
        """ISO 639-3 is tried first (the more commonly recognized identifier), falling back
        to a direct glottocode match — needed for "group" entities like the hand-picked
        Romance/Italic/Arabic family nodes, which have no ISO 639-3 code at all."""
        lowered = code.strip().lower()
        if lowered in self._iso_to_glottocode:
            return self._iso_to_glottocode[lowered]
        if lowered in self._valid_glottocodes:
            return lowered
        return None

    def get(self, code: str) -> dict[str, Any] | None:
        glottocode = self.resolve(code)
        if glottocode is None:
            return None
        if glottocode not in self._profile_cache:
            path = self._languages_dir / f"{glottocode}.json"
            if not path.exists():
                return None
            self._profile_cache[glottocode] = json.loads(path.read_text())
        return self._profile_cache[glottocode]
