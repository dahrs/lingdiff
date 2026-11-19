"""Loads WOLD (World Loanword Database) — see pipeline/vocabulary_origin.py for how this
feeds into VocabularyOrigin. Expert-curated, 41 languages, each already keyed by ISO 639-3 +
Glottolog code directly in WOLD's own data — no language-code mapping needed, unlike
etymology-db (see etymology_db_loader.py, which needs one because its source, Wiktionary,
has no such canonical per-language ID system of its own)."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


class WoldData:
    def __init__(self, raw_dir: Path) -> None:
        wold_id_to_iso: dict[str, str] = {}
        for row in _read_csv(raw_dir / "wold_languages.csv"):
            if row["ISO639P3code"]:
                wold_id_to_iso[row["ID"]] = row["ISO639P3code"].strip().lower()

        self._scores_by_iso: dict[str, list[float]] = defaultdict(list)
        form_id_to_iso: dict[str, str] = {}
        for row in _read_csv(raw_dir / "wold_forms.csv"):
            iso = wold_id_to_iso.get(row["Language_ID"])
            if not iso:
                continue
            form_id_to_iso[row["ID"]] = iso
            score = row.get("Borrowed_score", "").strip()
            if score:
                self._scores_by_iso[iso].append(float(score))

        self._donors_by_iso: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for row in _read_csv(raw_dir / "wold_borrowings.csv"):
            iso = form_id_to_iso.get(row["Target_Form_ID"])
            donor_name = row.get("Source_languoid", "").strip()
            if not iso or not donor_name:
                continue
            self._donors_by_iso[iso].append((donor_name, row.get("Source_languoid_glottocode") or None))

    def get(self, iso639_3: str) -> WoldResult | None:
        """None if WOLD doesn't cover this language at all (it's not one of its 41)."""
        scores = self._scores_by_iso.get(iso639_3.lower())
        if not scores:
            return None
        return WoldResult(
            mean_borrowed_score=sum(scores) / len(scores),
            donors=self._donors_by_iso.get(iso639_3.lower(), []),
            sample_size=len(scores),
        )


class WoldResult:
    def __init__(self, mean_borrowed_score: float, donors: list[tuple[str, str | None]], sample_size: int) -> None:
        self.mean_borrowed_score = mean_borrowed_score
        self.donors = donors
        """[(donor_name, donor_glottocode_or_None), ...] — one entry per borrowed WORD, not
        deduped by donor language; pipeline.vocabulary_origin tallies these into shares."""
        self.sample_size = sample_size


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
