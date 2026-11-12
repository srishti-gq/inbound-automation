"""Reads Excel files and auto-detects the right sheet, header row and columns
using the configurable column mapping (config/column_mapping.yaml)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .utils import norm_header

HEADER_SCAN_ROWS = 15


def read_sheets(path: str | Path) -> dict[str, pd.DataFrame]:
    """Read every sheet with no header (header row is detected later)."""
    path = Path(path)
    try:
        return pd.read_excel(path, sheet_name=None, header=None, engine="calamine")
    except ImportError:
        engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
        return pd.read_excel(path, sheet_name=None, header=None, engine=engine)


@dataclass
class Detection:
    sheet: str | None = None
    header_row: int | None = None
    columns: dict[str, str] = field(default_factory=dict)   # field -> actual header text
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    data: pd.DataFrame | None = None                         # columns renamed to field names

    @property
    def ok(self) -> bool:
        return self.sheet is not None and not self.missing_required


def _match_row(cells: list, spec: dict) -> dict[str, int]:
    """Return {field: column_index} for one candidate header row."""
    normed = [norm_header(c) for c in cells]
    used: set[int] = set()
    found: dict[str, int] = {}
    for fld, candidates in spec["fields"].items():
        for cand in candidates:
            nc = norm_header(cand)
            idx = next((i for i, h in enumerate(normed) if h == nc and i not in used), None)
            if idx is not None:
                found[fld] = idx
                used.add(idx)
                break
    return found


def detect(sheets: dict[str, pd.DataFrame], spec: dict) -> Detection:
    required = spec.get("required", [])
    best = None  # (score tuple, sheet, row, found)
    for name, raw in sheets.items():
        if raw.empty:
            continue
        for r in range(min(HEADER_SCAN_ROWS, len(raw))):
            found = _match_row(raw.iloc[r].tolist(), spec)
            score = (sum(f in found for f in required), len(found))
            if score[1] and (best is None or score > best[0]):
                best = (score, name, r, found)
    det = Detection()
    if best is None:
        det.missing_required = list(required)
        return det
    _, name, r, found = best
    raw = sheets[name]
    det.sheet, det.header_row = name, r
    det.columns = {f: str(raw.iat[r, i]) for f, i in found.items()}
    det.missing_required = [f for f in required if f not in found]
    det.missing_optional = [f for f in spec["fields"] if f not in found and f not in required]
    body = raw.iloc[r + 1:, list(found.values())].copy()
    body.columns = list(found.keys())
    body = body.dropna(how="all").reset_index(drop=True)
    det.data = body
    return det


def read_and_detect(path: str | Path, spec: dict) -> Detection:
    return detect(read_sheets(path), spec)
