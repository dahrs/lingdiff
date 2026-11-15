"""Loads PHOIBLE's phoneme-inventory CSV (fetch_sources.py's output)."""

from __future__ import annotations

import csv
from pathlib import Path


class PhoibleData:
    def __init__(self, raw_dir: Path) -> None:
        self._phonemes_by_inventory: dict[str, list[str]] = {}
        self._inventories_by_iso: dict[str, set[str]] = {}

        with (raw_dir / "phoible.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                iso = row["ISO6393"].strip().lower()
                inventory_id = row["InventoryID"]
                if iso:
                    self._inventories_by_iso.setdefault(iso, set()).add(inventory_id)
                self._phonemes_by_inventory.setdefault(inventory_id, []).append(row["Phoneme"])

    def phonemes_for(self, iso639_3: str) -> tuple[list[str], str] | None:
        """Returns (phoneme list, inventory id) for the largest available inventory for this
        language, or None if PHOIBLE has no entry for it."""
        inventory_ids = self._inventories_by_iso.get(iso639_3.lower())
        if not inventory_ids:
            return None
        best_id = max(inventory_ids, key=lambda i: len(self._phonemes_by_inventory[i]))
        return self._phonemes_by_inventory[best_id], best_id
