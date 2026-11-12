"""End-to-end tests on small synthetic files (no real customer data).
Run:  pytest -q
"""
import sqlite3

import pandas as pd
import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("INBOUND_DATA_DIR", str(tmp_path / "data"))
    from core import db
    db.init_db()
    return tmp_path


def _xlsx(path, sheets: dict):
    with pd.ExcelWriter(path) as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    return path


def _sources(tmp):
    from core import sources
    portfolio = pd.DataFrame({
        "GQ Application ID": [101, 102, 103, 104, 105, 106],
        "Loan Stage": ["Loan Live", "Loan Live", "Loan Live", "Settled", "Loan Live", "Loan Live"],
        "Current Overdue Amount": [10000, 0, 0, 500, 2000, "Not Available"],
        "Total Charges Outstanding Amount": [590, 1180, 0, 0, 0, 300],
        "Current Overdue days": [45, 0, 0, 200, "Not Available", 10],
        "LENDER": ["L1"] * 6,
        "Total Payment made till date": [100, 200, 300, 400, "Not Available", 0],
    })
    alloc = pd.DataFrame({
        "GQ Application IDs": [101, 102, 104, 105],
        "CM Name": ["CM A", "CM B", "Hold till 15th", "CM A"],
        "Name": ["Agent 1", "Agent 2", "Hold till 15th", "Agent 1"],
        "Parent Name": ["P1", "P2", "P4", "P5"],
        "Mobile Number": [9000000001, 9000000002, 9000000004, 9000000005],
    })
    p = sources.register_source("portfolio", "pf.xlsx", _xlsx(tmp / "pf.xlsx", {"Sheet1": portfolio}).read_bytes(), "2026-11-05")
    a = sources.register_source("allocation", "al.xlsx", _xlsx(tmp / "al.xlsx", {"Sheet1": alloc}).read_bytes(), "2026-10-31")
    return p["id"], a["id"]


def _inbound(tmp, name="in.xlsx"):
    rec = pd.DataFrame({
        "Date": ["2026-11-05 10:00:00.1", "2026-11-05 11:00:00.2", "2026-11-04 09:00:00.3", "2026-11-05 12:00:00"],
        "Calling Mobile": ["9000000001", "9000000001", "9000000009", "9000000008"],
        "Student Name (DB)": ["S1", "S1", "S3", None],
        "Issue Category": ["PTP", "Payment Link Required", "Dropout", "No Response / Incomplete Call"],
        "Issue Details": ["Will pay Friday", None, "Left course", None],
        "Outcome": ["Converted", "Follow-Up", "Lost", "Follow-Up"],
        "App ID": ["101, 102", "101", "103, 104, 105, 106, 999", None],
        "Loan Live App ID": ["101, 102", "101", "103, 105, 106, 999", None],
        "Loan Closed App ID": [None, None, None, None],
    })
    summary = pd.DataFrame({"App ID": [1], "Team": ["x"]})   # decoy sheet like 'Main_Data'
    return _xlsx(tmp / name, {"Main_Data": summary, "Recordings": rec})


def _make_batch(tmp, p, a, name="in.xlsx"):
    from core import batch, inbound, sources
    f = _inbound(tmp, name)
    parsed = inbound.parse_inbound(f)
    fid = sources.register_inbound_file(name, f.read_bytes(), parsed.detection)
    return parsed, batch.create_batch(parsed, fid, parsed.calling_date, p, a, None)


def test_inbound_parsing_picks_right_sheet_and_splits_ids(env):
    from core import inbound
    parsed = inbound.parse_inbound(_inbound(env))
    assert parsed.detection.sheet == "Recordings"
    assert set(parsed.id_index["app_id"]) == {"101", "102", "103", "104", "105", "106", "999"}
    assert int(parsed.id_index.set_index("app_id").at["101", "n_calls"]) == 2
    assert len(parsed.unidentified) == 1
    assert parsed.calling_date == "2026-11-05"


def test_enrichment_rules(env):
    from core import reports
    p, a = _sources(env)
    _, bid = _make_batch(env, p, a)
    k = reports.cases(bid).set_index("app_id")
    # 101 overdue, 102 charges only, 104 settled with overdue, 105 overdue (DPD missing), 106 charges (overdue N/A)
    assert set(k.index) == {"101", "102", "104", "105", "106"}
    assert k.at["101", "case_type"] == "DPD Bucket" and k.at["101", "orig_dpd_bucket"] == "31-60"
    assert k.at["102", "case_type"] == "Charges"
    assert k.at["101", "assigned_cm"] == "CM A"
    assert k.at["101", "n_calls"] == 2 and "Will pay Friday" in k.at["101", "concern"]
    assert pd.isna(k.at["106", "orig_overdue"])          # 'Not Available' is NOT turned into 0
    assert pd.isna(k.at["104", "assigned_cm"]) and k.at["104", "orig_alloc_cm"] == "Hold till 15th"

    ids = reports.app_ids(bid).set_index("app_id")["match_status"]
    assert ids["103"] == "No dues" and ids["999"] == "Not in portfolio"

    ex = reports.exceptions(bid)
    types = set(zip(ex["app_id"].fillna("-"), ex["type"]))
    assert ("999", "MISSING_IN_PORTFOLIO") in types
    assert ("104", "ALLOCATION_ON_HOLD") in types
    assert ("106", "NO_CM_ALLOCATION") in types
    assert ("105", "MISSING_DPD") in types
    assert ("106", "MISSING_AMOUNTS") in types
    assert ("104", "NON_LIVE_STAGE") in types
    assert ("-", "UNIDENTIFIED_CALL") in types


def test_snapshot_is_read_only_and_manual_assignment_keeps_history(env):
    from core import batch, db, reports
    p, a = _sources(env)
    _, bid = _make_batch(env, p, a)
    with pytest.raises(sqlite3.DatabaseError):
        with db.transaction() as conn:
            conn.execute("UPDATE cases SET orig_overdue=0 WHERE batch_id=?", (bid,))
    with pytest.raises(sqlite3.DatabaseError):
        with db.transaction() as conn:
            conn.execute("DELETE FROM cases WHERE batch_id=?", (bid,))
    batch.assign_cm(bid, "104", "CM B", "test")
    k = reports.cases(bid).set_index("app_id")
    assert k.at["104", "assigned_cm"] == "CM B" and k.at["104", "cm_source"] == "manual"
    assert k.at["104", "orig_alloc_cm"] == "Hold till 15th"
    ex = reports.exceptions(bid)
    assert (ex[(ex.app_id == "104") & (ex.type == "ALLOCATION_ON_HOLD")]["status"] == "Resolved").all()


def test_same_app_id_in_two_batches_stays_separate(env):
    from core import reports
    p, a = _sources(env)
    _, b1 = _make_batch(env, p, a, "in1.xlsx")
    _, b2 = _make_batch(env, p, a, "in2.xlsx")
    assert b1 == "IB-20261105-01" and b2 == "IB-20261105-02"
    assert len(reports.cases(b1)) == len(reports.cases(b2)) == 5


def test_excel_export(env):
    from core import reports
    p, a = _sources(env)
    _, bid = _make_batch(env, p, a)
    data = reports.batch_workbook(bid, ["0-30", "31-60", "61-90", "91-180", "181-360", "360+"])
    import io
    xl = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
    assert {"Summary", "CM Summary", "Cases", "Exceptions", "All App IDs"} <= set(xl.sheet_names)
