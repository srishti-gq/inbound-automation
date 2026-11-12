"""Loads YAML configuration. Nothing business-specific is hardcoded in code."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
MAPPING_FILE = CONFIG_DIR / "column_mapping.yaml"


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def settings() -> dict:
    return _load(SETTINGS_FILE)


def column_mapping() -> dict:
    return _load(MAPPING_FILE)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_yaml_text(path: Path, text: str) -> None:
    """Validate YAML before saving so a typo can never break the app."""
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise ValueError("Configuration must be a YAML mapping (key: value).")
    path.write_text(text, encoding="utf-8")


def data_dir() -> Path:
    override = os.environ.get("INBOUND_DATA_DIR")   # used by tests
    d = Path(override) if override else ROOT / settings().get("data_dir", "data")
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / settings().get("database_file", "inbound.db")
