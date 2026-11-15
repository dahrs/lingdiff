"""Resumable pipeline state: tracks which languages are fully built so reruns skip
finished work and don't re-spend LLM calls."""

from __future__ import annotations

import json
from pathlib import Path


class Checkpoint:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._done: set[str] = set()
        if path.exists():
            self._done = set(json.loads(path.read_text()))

    def is_done(self, iso639_3: str) -> bool:
        return iso639_3 in self._done

    def mark_done(self, iso639_3: str) -> None:
        self._done.add(iso639_3)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(sorted(self._done), indent=2))
