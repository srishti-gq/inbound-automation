"""Source files: every upload is stored as an untouched copy, parsed once,
and kept as a numbered version. Old versions are never overwritten."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from . import config
from .db import audit, connect, current_user, now, transaction
from .excel_io import Detection, read_and_detect
from .utils import clean_text, norm_id, to_number

SOURCE_KINDS = {
    "portfolio": "Loan Live Portfolio",
    "allocation": "CM Allocation (Overdue)",
    "charges_allocation": "Charges Allocation (optional)",
    "inbound": "Inbound Calling Report",
}
ROW_TABLE = {
    "portfolio": "portfolio_rows",
    "allocation": "allocation_rows",
    "charges_allocation": "charges_allocation_rows",
}


class SourceFileError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_upload(kind: str, filename: str, data: bytes) -> tuple[Path, str]:
    """Save an untouched copy of the uploaded file. Never overwrites."""
    digest = sha256_bytes(data)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)
    folder = config.data_dir() / "uploads" / kind
    folder.mkdir(parents=True, exist_ok=True)
    stamp = now().replace(":", "").replace("-", "").replace(" ", "_")
    path = folder / f"{stamp}_{digest[:8]}_{safe}"
    path.write_bytes(data)
    return path, digest


def find_by_sha(kind: str, digest: str):
    conn = connect()
    try:
        return conn.execute(
            "SELECT * FROM source_files WHERE kind=? AND sha256=? ORDER BY id DESC LIMIT 1", (kind, digest)
        ).fetchone()
    finally:
        conn.close()


def _build_rows(kind: str, det: Detection, markers) -> pd.DataFrame:
    df = det.data.copy()
    df["app_id"] = df["app_id"].map(norm_id)
    df = df[df["app_id"].notna()].copy()

    def col(name, fn=clean_text):
        return df[name].map(fn) if name in df.columns else None

    num = lambda v: to_number(v, markers)  # noqa: E731
    if kind == "portfolio":
        out = pd.DataFrame({
            "app_id": df["app_id"],
            "loan_stage": col("loan_stage"), "lender": col("lender"),
            "overdue": col("overdue", num), "charges": col("charges", num), "dpd": col("dpd", num),
            "emi_amount": col("emi_amount", num), "emi_outstanding": col("emi_outstanding", num),
            "total_paid": col("total_paid", num),
            "last_payment_date": col("last_payment_date"), "last_unpaid_due": col("last_unpaid_due"),
        })
        out["dup_rank"] = out.groupby("app_id").cumcount() + 1
    elif kind == "allocation":
        out = pd.DataFrame({
            "app_id": df["app_id"],
            "cm_name": col("cm_name"), "agent_name": col("agent_name"),
            "student_name": col("student_name"), "parent_name": col("parent_name"),
            "mobile": col("mobile"), "institute": col("institute"), "remark": col("remark"),
            "alloc_date": col("alloc_date"), "alloc_dpd": col("alloc_dpd"),
        })
        out["dup_rank"] = out.groupby("app_id").cumcount() + 1
    elif kind == "charges_allocation":
        out = pd.DataFrame({
            "app_id": df["app_id"], "charges_cm": col("charges_cm"),
            "lot": col("lot"), "code": col("code"),
        })
        # latest lot = last row in the file -> rank 1
        out["dup_rank"] = out.iloc[::-1].groupby("app_id").cumcount().iloc[::-1] + 1
    else:
        raise ValueError(kind)
    return out


def register_source(kind: str, filename: str, data: bytes, as_of_date: str | None) -> dict:
    """Store + parse a portfolio / allocation / charges file. Returns a summary dict."""
    if kind not in ROW_TABLE:
        raise ValueError(kind)
    path, digest = store_upload(kind, filename, data)
    spec = config.column_mapping()[kind]
    det = read_and_detect(path, spec)
    if not det.ok:
        raise SourceFileError(
            f"Could not find required column(s) {det.missing_required} in '{filename}'. "
            f"Check the file or update the column mapping in Settings."
        )
    markers = config.settings().get("missing_value_markers", [])
    rows = _build_rows(kind, det, markers)
    n_unique = int(rows["app_id"].nunique())
    n_dup = int((rows["dup_rank"] > 1).sum())
    with transaction() as conn:
        cur = conn.execute(
            """INSERT INTO source_files (kind, original_name, stored_path, sha256, uploaded_at, uploaded_by,
               as_of_date, sheet, header_row, column_map, row_count, unique_ids, duplicate_ids)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (kind, filename, str(path), digest, now(), current_user(), as_of_date, det.sheet,
             det.header_row, json.dumps(det.columns), len(rows), n_unique, n_dup),
        )
        sid = cur.lastrowid
        rows.insert(0, "source_file_id", sid)
        rows.to_sql(ROW_TABLE[kind], conn, if_exists="append", index=False, chunksize=5000)
        audit(conn, f"upload_{kind}", None, {"source_file_id": sid, "file": filename, "rows": len(rows)})
    return {
        "id": sid, "rows": len(rows), "unique_ids": n_unique, "duplicate_ids": n_dup,
        "sheet": det.sheet, "columns": det.columns, "missing_optional": det.missing_optional,
    }


def register_inbound_file(filename: str, data: bytes, det: Detection) -> int:
    path, digest = store_upload("inbound", filename, data)
    with transaction() as conn:
        cur = conn.execute(
            """INSERT INTO source_files (kind, original_name, stored_path, sha256, uploaded_at, uploaded_by,
               sheet, header_row, column_map, row_count) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            ("inbound", filename, str(path), digest, now(), current_user(), det.sheet, det.header_row,
             json.dumps(det.columns), len(det.data)),
        )
        return cur.lastrowid


def list_sources(kind: str | None = None) -> pd.DataFrame:
    from .db import query_df

    sql = """SELECT id, kind, original_name, as_of_date, uploaded_at, uploaded_by, sheet,
                    row_count, unique_ids, duplicate_ids FROM source_files"""
    if kind:
        return query_df(sql + " WHERE kind=? ORDER BY id DESC", (kind,))
    return query_df(sql + " ORDER BY id DESC")


def latest_source(kind: str):
    conn = connect()
    try:
        return conn.execute(
            "SELECT * FROM source_files WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)
        ).fetchone()
    finally:
        conn.close()


def lookup(kind: str, source_file_id: int, app_ids: list[str]) -> pd.DataFrame:
    """Equivalent of a VLOOKUP: fetch rows for the given IDs (all duplicates included)."""
    table = ROW_TABLE[kind]
    conn = connect()
    try:
        frames = []
        for i in range(0, len(app_ids), 800):
            chunk = app_ids[i:i + 800]
            q = f"SELECT * FROM {table} WHERE source_file_id=? AND app_id IN ({','.join('?' * len(chunk))})"
            frames.append(pd.read_sql_query(q, conn, params=[source_file_id, *chunk]))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    finally:
        conn.close()


def distinct_cms(allocation_file_id: int | None = None) -> list[str]:
    """Known CM names (for manual assignment dropdowns)."""
    conn = connect()
    try:
        if allocation_file_id:
            rows = conn.execute(
                "SELECT DISTINCT cm_name FROM allocation_rows WHERE source_file_id=? AND cm_name IS NOT NULL",
                (allocation_file_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT cm_name FROM allocation_rows WHERE cm_name IS NOT NULL").fetchall()
        rows += conn.execute("SELECT DISTINCT assigned_cm FROM cases WHERE assigned_cm IS NOT NULL").fetchall()
    finally:
        conn.close()
    patterns = config.settings().get("non_cm_allocation_patterns", [])
    names = {r[0] for r in rows if r[0] and not any(p.lower() in r[0].lower() for p in patterns)}
    return sorted(names)
