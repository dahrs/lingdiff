"""Loads the raw WALS CLDF CSVs (fetch_sources.py's output) into simple lookup structures.

Word-order / tense-aspect / writing-system parameters are found by keyword search over
parameters.csv's Name column at load time, rather than hardcoded WALS chapter/parameter
codes — WALS's own parameter numbering is the source of truth, not anything memorized here.
"""

from __future__ import annotations

import csv
from pathlib import Path


class WalsData:
    def __init__(self, raw_dir: Path) -> None:
        self.languages = _read_csv(raw_dir / "wals_languages.csv")
        self.parameters = _read_csv(raw_dir / "wals_parameters.csv")
        self.codes = _read_csv(raw_dir / "wals_codes.csv")
        self.values = _read_csv(raw_dir / "wals_values.csv")

        candidates_by_iso: dict[str, list[dict[str, str]]] = {}
        for row in self.languages:
            iso = row["ISO639P3code"].strip().lower()
            if iso:
                candidates_by_iso.setdefault(iso, []).append(row)

        # Some ISO codes map to several WALS entries (regional dialects). Prefer, in order:
        # (1) WALS's curated 100-/200-language representative sample (Samples_100/200), then
        # (2) the shortest Name, since WALS's convention is "plain language name" for the
        # standard/default variety and "Name (Dialect)" for a specific regional one — e.g.
        # "Italian" over "Italian (Fiorentino)", "Romanian" over "Moldavian". Still a
        # heuristic, not authoritative; worth a manual check if a specific pair looks off.
        self._language_by_iso: dict[str, dict[str, str]] = {
            iso: max(
                rows,
                key=lambda r: (r["Samples_200"] == "true", r["Samples_100"] == "true", -len(r["Name"])),
            )
            for iso, rows in candidates_by_iso.items()
        }

        self._param_name_by_id = {row["ID"]: row["Name"] for row in self.parameters}
        self._code_name_by_id = {row["ID"]: row["Name"] for row in self.codes}

        self._values_by_language_id: dict[str, list[dict[str, str]]] = {}
        for row in self.values:
            self._values_by_language_id.setdefault(row["Language_ID"], []).append(row)

    def find_language(self, iso639_3: str) -> dict[str, str] | None:
        return self._language_by_iso.get(iso639_3.lower())

    def param_name(self, parameter_id: str) -> str:
        return self._param_name_by_id.get(parameter_id, parameter_id)

    def code_name(self, code_id: str) -> str:
        return self._code_name_by_id.get(code_id, code_id)

    def values_for(self, wals_language_id: str, name_contains: tuple[str, ...]) -> list[dict[str, str]]:
        """Returns this language's value rows whose parameter name contains any of the given
        (lowercased) substrings, e.g. ("order of",) for word-order features."""
        matches = []
        for row in self._values_by_language_id.get(wals_language_id, []):
            name = self.param_name(row["Parameter_ID"]).lower()
            if any(substring in name for substring in name_contains):
                matches.append(row)
        return matches

    def all_values_for(self, wals_language_id: str) -> list[dict[str, str]]:
        """Every WALS value row for this language, across all 192 parameters — the basis for
        build_profile.py's other_typological_features catch-all."""
        return list(self._values_by_language_id.get(wals_language_id, []))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
