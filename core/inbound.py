"""Parses the inbound calling report into calls and Application IDs."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config
from .excel_io import Detection, read_and_detect
from .utils import clean_text, split_ids


@dataclass
class InboundParse:
    detection: Detection
    calls: pd.DataFrame          # one row per call, with id lists
    id_index: pd.DataFrame       # one row per unique App ID
    calling_date: str | None     # latest call date in the file

    @property
    def unidentified(self) -> pd.DataFrame:
        return self.calls[self.calls["id_list"].map(len) == 0]


def parse_inbound(path) -> InboundParse:
    spec = config.column_mapping()["inbound"]
    det = read_and_detect(path, spec)
    if not det.ok:
        raise ValueError(
            f"Could not find the Application ID column in the inbound report "
            f"(looked for: {spec['fields']['app_ids']}). Update the column mapping in Settings."
        )
    seps = spec.get("id_separators", [","])
    df = det.data.copy()
    calls = pd.DataFrame({"call_no": range(1, len(df) + 1)})
    for fld in ["call_time", "calling_mobile", "student_name", "institute", "issue_category",
                "issue_details", "outcome", "app_ids", "live_app_ids", "closed_app_ids",
                "panel_stage", "recording_url"]:
        calls[fld] = df[fld].map(clean_text).values if fld in df.columns else None
    ts = pd.to_datetime(calls["call_time"], errors="coerce")
    calls["call_time"] = ts.dt.strftime("%Y-%m-%d %H:%M:%S").where(ts.notna(), calls["call_time"])
    calls["id_list"] = df["app_ids"].map(lambda v: split_ids(v, seps)).values
    live = df["live_app_ids"].map(lambda v: split_ids(v, seps)).values if "live_app_ids" in df else None
    closed = df["closed_app_ids"].map(lambda v: split_ids(v, seps)).values if "closed_app_ids" in df else None
    has_split = live is not None or closed is not None

    rows: dict[str, dict] = {}
    for i, ids in enumerate(calls["id_list"]):
        lv = set(live[i]) if live is not None else set()
        cl = set(closed[i]) if closed is not None else set()
        for a in ids:
            r = rows.setdefault(a, {"app_id": a, "call_nos": [], "live": False, "closed": False})
            r["call_nos"].append(int(calls.at[i, "call_no"]))
            r["live"] |= a in lv
            r["closed"] |= a in cl
        # IDs listed only in live/closed columns but not in the main column
        for a in lv | cl:
            if a not in ids:
                r = rows.setdefault(a, {"app_id": a, "call_nos": [], "live": False, "closed": False})
                r["call_nos"].append(int(calls.at[i, "call_no"]))
                r["live"] |= a in lv
                r["closed"] |= a in cl

    def listed(r):
        if not has_split:
            return "unknown"
        return "live" if r["live"] else ("closed" if r["closed"] else "other")

    id_index = pd.DataFrame(
        [{"app_id": r["app_id"], "call_nos": sorted(set(r["call_nos"])), "listed_as": listed(r)} for r in rows.values()],
        columns=["app_id", "call_nos", "listed_as"],
    )
    id_index["n_calls"] = id_index["call_nos"].map(len)
    calling_date = ts.max().strftime("%Y-%m-%d") if ts.notna().any() else None
    return InboundParse(det, calls, id_index, calling_date)
