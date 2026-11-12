"""Small, pure helpers: ID normalisation, number parsing, DPD buckets."""
from __future__ import annotations

import math
import re
from typing import Iterable

import pandas as pd


def norm_header(value) -> str:
    """'Student Name (DB)' -> 'studentnamedb'. Used for tolerant header matching."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"[\s._\-()/\\]+", "", str(value)).lower()


def is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def norm_id(value) -> str | None:
    """Normalise an Application ID to a clean string ('1868471.0' -> '1868471')."""
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = re.sub(r"\s+", "", str(value))
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s or None


def split_ids(value, separators: Iterable[str]) -> list[str]:
    """Split a cell like '2020950, 2018274' into normalised IDs (order kept, no repeats)."""
    if is_blank(value):
        return []
    text = str(value)
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    pattern = "|".join(re.escape(s) for s in separators)
    out: list[str] = []
    for part in re.split(pattern, text):
        nid = norm_id(part)
        if nid and nid not in out:
            out.append(nid)
    return out


def to_number(value, missing_markers: Iterable[str]) -> float | None:
    """Parse amounts/days. Placeholder text (e.g. 'Not Available') -> None, never 0."""
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    s = str(value).strip()
    markers = {m.strip().lower() for m in missing_markers}
    if s.lower() in markers:
        return None
    s = s.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def dpd_bucket(days, buckets: list[dict]) -> str | None:
    if days is None or (isinstance(days, float) and math.isnan(days)):
        return None
    for b in buckets:
        if b["min"] <= days <= b["max"]:
            return b["label"]
    return None


def matches_any(value, patterns: Iterable[str]) -> bool:
    if is_blank(value):
        return False
    v = str(value).lower()
    return any(p.lower() in v for p in patterns)


def clean_text(value) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
