"""Valores permitidos e rótulos, lidos de data/reference.json (fonte única)."""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REF: dict = json.loads((DATA_DIR / "reference.json").read_text(encoding="utf-8"))

CUISINES: dict[str, str] = {k: v["label"] for k, v in REF["cuisines"].items()}
DIETS: dict[str, str] = REF["dietary_options"]
AMBIENCES: dict[str, str] = REF["ambiences"]
OCCASIONS: dict[str, str] = REF["occasions"]
NEIGHBORHOODS: dict[str, dict] = REF["neighborhoods"]


def cuisine_label(key: str) -> str:
    return CUISINES.get(key, key).lower()


def ambience_label(key: str) -> str:
    return AMBIENCES.get(key, key).lower()


def diet_label(key: str) -> str:
    return DIETS.get(key, key).lower()
