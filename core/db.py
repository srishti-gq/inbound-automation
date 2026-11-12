"""SQLite storage. Original snapshots are protected by database triggers so
they can never be overwritten, even by mistake."""
from __future__ import annotations

import getpass
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,            -- inbound | portfolio | allocation | charges_allocation
    original_name   TEXT NOT NULL,
    stored_path     TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    uploaded_at     TEXT NOT NULL,
    uploaded_by     TEXT,
    as_of_date      TEXT,                     -- data date of the file (user supplied)
    sheet           TEXT,
    header_row      INTEGER,
    column_map      TEXT,                     -- JSON {field: header}
    row_count       INTEGER,
    unique_ids      INTEGER,
    duplicate_ids   INTEGER,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_rows (
    source_file_id    INTEGER NOT NULL,
    app_id            TEXT NOT NULL,
    loan_stage        TEXT, lender TEXT,
    overdue           REAL, charges REAL, dpd REAL,
    emi_amount        REAL, emi_outstanding REAL, total_paid REAL,
    last_payment_date TEXT, last_unpaid_due TEXT,
    dup_rank          INTEGER DEFAULT 1        -- 1 = first occurrence of the ID in the file
);
CREATE INDEX IF NOT EXISTS ix_portfolio ON portfolio_rows(source_file_id, app_id);

CREATE TABLE IF NOT EXISTS allocation_rows (
    source_file_id INTEGER NOT NULL,
    app_id TEXT NOT NULL,
    cm_name TEXT, agent_name TEXT, student_name TEXT, parent_name TEXT,
    mobile TEXT, institute TEXT, remark TEXT, alloc_date TEXT, alloc_dpd TEXT,
    dup_rank INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_alloc ON allocation_rows(source_file_id, app_id);

CREATE TABLE IF NOT EXISTS charges_allocation_rows (
    source_file_id INTEGER NOT NULL,
    app_id TEXT NOT NULL,
    charges_cm TEXT, lot TEXT, code TEXT,
    dup_rank INTEGER DEFAULT 1                 -- 1 = LAST occurrence (latest lot) in the file
);
CREATE INDEX IF NOT EXISTS ix_challoc ON charges_allocation_rows(source_file_id, app_id);

CREATE TABLE IF NOT EXISTS batches (
    batch_id            TEXT PRIMARY KEY,
    created_at          TEXT NOT NULL,
    created_by          TEXT,
    calling_date        TEXT,
    inbound_file_id     INTEGER NOT NULL,
    portfolio_file_id   INTEGER NOT NULL,
    allocation_file_id  INTEGER NOT NULL,
    charges_file_id     INTEGER,
    total_calls         INTEGER,
    unidentified_calls  INTEGER,
    total_app_ids       INTEGER,
    total_cases         INTEGER,
    processing_status   TEXT,
    email_status        TEXT DEFAULT 'Not started',
    recheck_status      TEXT DEFAULT 'Not due',
    mis_status          TEXT DEFAULT 'Not updated',
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS calls (
    batch_id TEXT NOT NULL,
    call_no INTEGER NOT NULL,
    call_time TEXT, calling_mobile TEXT, student_name TEXT, institute TEXT,
    issue_category TEXT, issue_details TEXT, outcome TEXT,
    app_ids TEXT, live_app_ids TEXT, closed_app_ids TEXT, panel_stage TEXT, recording_url TEXT,
    PRIMARY KEY (batch_id, call_no)
);

-- every Application ID mentioned in the inbound report, with what happened to it
CREATE TABLE IF NOT EXISTS batch_app_ids (
    batch_id TEXT NOT NULL,
    app_id TEXT NOT NULL,
    call_nos TEXT,              -- comma separated
    n_calls INTEGER,
    listed_as TEXT,             -- live | closed | other | unknown (from inbound report columns)
    match_status TEXT,          -- Case created | No dues | Not in portfolio | Missing amounts
    PRIMARY KEY (batch_id, app_id)
);

CREATE TABLE IF NOT EXISTS cases (
    batch_id TEXT NOT NULL,
    app_id TEXT NOT NULL,
    -- customer / call details
    student_name TEXT, parent_name TEXT, mobile TEXT, calling_mobiles TEXT, institute TEXT,
    issue_categories TEXT, outcomes TEXT, concern TEXT, n_calls INTEGER,
    -- ORIGINAL SNAPSHOT (read-only, protected by trigger)
    snapshot_at TEXT NOT NULL,
    orig_loan_stage TEXT, orig_lender TEXT,
    orig_overdue REAL, orig_charges REAL, orig_dpd REAL, orig_dpd_bucket TEXT,
    orig_emi_outstanding REAL, orig_total_paid REAL, orig_last_payment_date TEXT,
    case_type TEXT,
    -- ORIGINAL ALLOCATION (read-only, protected by trigger)
    orig_alloc_cm TEXT, orig_alloc_agent TEXT, orig_charges_cm TEXT,
    -- allocation used for this batch (may be set manually for unallocated cases)
    assigned_cm TEXT, cm_source TEXT, cm_assigned_by TEXT, cm_assigned_at TEXT,
    PRIMARY KEY (batch_id, app_id)
);

CREATE TRIGGER IF NOT EXISTS protect_case_snapshot
BEFORE UPDATE OF snapshot_at, orig_loan_stage, orig_lender, orig_overdue, orig_charges, orig_dpd,
                 orig_dpd_bucket, orig_emi_outstanding, orig_total_paid, orig_last_payment_date,
                 case_type, orig_alloc_cm, orig_alloc_agent, orig_charges_cm, batch_id, app_id
ON cases
BEGIN
    SELECT RAISE(ABORT, 'Original snapshot / allocation is read-only and cannot be changed');
END;

CREATE TRIGGER IF NOT EXISTS protect_case_delete
BEFORE DELETE ON cases
BEGIN
    SELECT RAISE(ABORT, 'Historical case records cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS protect_batch_sources
BEFORE UPDATE OF batch_id, created_at, inbound_file_id, portfolio_file_id, allocation_file_id, charges_file_id
ON batches
BEGIN
    SELECT RAISE(ABORT, 'Batch source files are read-only');
END;

CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT,
    app_id TEXT,
    call_no INTEGER,
    type TEXT NOT NULL,
    detail TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',   -- Pending | Resolved | Reprocessing
    created_at TEXT NOT NULL,
    resolved_at TEXT, resolved_by TEXT, resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS ix_exc ON exceptions(batch_id, status);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user TEXT,
    action TEXT NOT NULL,
    batch_id TEXT,
    detail TEXT
);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "unknown"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction():
    """All-or-nothing: if anything fails, nothing is written."""
    conn = connect()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def audit(conn: sqlite3.Connection, action: str, batch_id: str | None = None, detail=None) -> None:
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, default=str)
    conn.execute(
        "INSERT INTO audit_log (ts, user, action, batch_id, detail) VALUES (?,?,?,?,?)",
        (now(), current_user(), action, batch_id, detail),
    )


def query_df(sql: str, params=()):
    import pandas as pd

    conn = connect()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()
