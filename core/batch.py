"""Creates an inbound batch: enrichment (lookups), case creation, exceptions.
Reproduces the manual Main_Data logic:
  1. split each call's App ID list -> unique IDs
  2. look up each ID in the Loan Live Portfolio
  3. keep IDs with overdue > 0 OR charges > 0  -> cases
  4. case type = 'DPD Bucket' if overdue > 0 else 'Charges'
  5. DPD bucket from portfolio overdue days
  6. CM / Team from the overdue CM allocation file
"""
from __future__ import annotations

import math

import pandas as pd

from . import config, sources
from .db import audit, connect, current_user, now, transaction
from .exception_types import CM_EXCEPTION_TYPES
from .inbound import InboundParse
from .utils import dpd_bucket, matches_any


def _val(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def new_batch_id(conn, calling_date: str | None) -> str:
    prefix = config.settings().get("batch_id_prefix", "IB")
    day = (calling_date or now()[:10]).replace("-", "")
    base = f"{prefix}-{day}-"
    n = conn.execute("SELECT COUNT(*) FROM batches WHERE batch_id LIKE ?", (base + "%",)).fetchone()[0]
    return f"{base}{n + 1:02d}"


def _concern(call_rows: pd.DataFrame) -> str:
    parts = []
    for _, c in call_rows.sort_values("call_time", na_position="last").iterrows():
        when = (c["call_time"] or "")[:16]
        cat = c["issue_category"] or "-"
        det = c["issue_details"]
        parts.append(f"[{when}] {cat}" + (f": {det}" if det else ""))
    return "\n".join(parts)


def _join_unique(values) -> str | None:
    out = []
    for v in values:
        if v and v not in out:
            out.append(v)
    return ", ".join(out) or None


def create_batch(parsed: InboundParse, inbound_file_id: int, calling_date: str | None,
                 portfolio_file_id: int, allocation_file_id: int, charges_file_id: int | None,
                 notes: str | None = None) -> str:
    st = config.settings()
    buckets = st["dpd_buckets"]
    thr = float(st.get("min_amount_threshold", 0))
    labels = st.get("case_type_labels", {"overdue": "DPD Bucket", "charges_only": "Charges"})
    hold_patterns = st.get("non_cm_allocation_patterns", [])

    calls, idx = parsed.calls, parsed.id_index
    all_ids = idx["app_id"].tolist()
    pf = sources.lookup("portfolio", portfolio_file_id, all_ids)
    al = sources.lookup("allocation", allocation_file_id, all_ids)
    ch = sources.lookup("charges_allocation", charges_file_id, all_ids) if charges_file_id else pd.DataFrame()
    pf_first = pf[pf["dup_rank"] == 1].set_index("app_id") if len(pf) else pd.DataFrame()
    pf_dups = set(pf.loc[pf["dup_rank"] > 1, "app_id"]) if len(pf) else set()
    al_first = al[al["dup_rank"] == 1].set_index("app_id") if len(al) else pd.DataFrame()
    al_dups = set(al.loc[al["dup_rank"] > 1, "app_id"]) if len(al) else set()
    ch_first = ch[ch["dup_rank"] == 1].set_index("app_id") if len(ch) else pd.DataFrame()

    ts = now()
    exceptions: list[tuple] = []   # (app_id, call_no, type, detail)
    id_rows, case_rows = [], []
    calls_by_no = calls.set_index("call_no")

    for c in parsed.unidentified.itertuples():
        exceptions.append((None, int(c.call_no), "UNIDENTIFIED_CALL",
                           f"Caller {c.calling_mobile or '-'} / {c.student_name or '-'}: {c.issue_category or ''}"))

    for r in idx.itertuples():
        a = r.app_id
        status = None
        if a not in pf_first.index:
            status = "Not in portfolio"
            if r.listed_as in ("live", "unknown"):
                exceptions.append((a, None, "MISSING_IN_PORTFOLIO",
                                   f"Listed as '{r.listed_as}' in inbound report but not in portfolio file"))
        else:
            p = pf_first.loc[a]
            od, chg, dpd = _val(p["overdue"]), _val(p["charges"]), _val(p["dpd"])
            if a in pf_dups:
                exceptions.append((a, None, "DUPLICATE_IN_PORTFOLIO", "First occurrence used"))
            if od is None and chg is None:
                status = "Missing amounts"
                exceptions.append((a, None, "MISSING_AMOUNTS", "Both overdue and charges are blank/'Not Available'"))
                has_dues = True   # cannot decide -> keep as a case for review, never drop silently
            else:
                if od is None or chg is None:
                    exceptions.append((a, None, "MISSING_AMOUNTS",
                                       f"{'Overdue' if od is None else 'Charges'} is blank/'Not Available'"))
                has_dues = (od or 0) > thr or (chg or 0) > thr
                status = "Case created" if has_dues else "No dues"
            if has_dues:
                cr = calls_by_no.loc[r.call_nos].reset_index()
                alloc = al_first.loc[a] if a in al_first.index else None
                chrow = ch_first.loc[a] if a in ch_first.index else None
                orig_cm = _val(alloc["cm_name"]) if alloc is not None else None
                if alloc is None or orig_cm is None:
                    assigned, src = None, None
                    exceptions.append((a, None, "NO_CM_ALLOCATION", "App ID not found in CM allocation file"))
                elif matches_any(orig_cm, hold_patterns):
                    assigned, src = None, None
                    exceptions.append((a, None, "ALLOCATION_ON_HOLD", f"Allocation file says '{orig_cm}'"))
                else:
                    assigned, src = orig_cm, "allocation_file"
                if a in al_dups:
                    exceptions.append((a, None, "DUPLICATE_IN_ALLOCATION", "First occurrence used"))
                if dpd is None:
                    exceptions.append((a, None, "MISSING_DPD", "DPD blank/'Not Available' in portfolio"))
                stage = _val(p["loan_stage"])
                if stage and stage.strip().lower() != "loan live":
                    exceptions.append((a, None, "NON_LIVE_STAGE", f"Loan stage is '{stage}' but dues exist"))
                case_rows.append({
                    "batch_id": None, "app_id": a,
                    "student_name": _join_unique(cr["student_name"]) or (_val(alloc["student_name"]) if alloc is not None else None),
                    "parent_name": _val(alloc["parent_name"]) if alloc is not None else None,
                    "mobile": _val(alloc["mobile"]) if alloc is not None else None,
                    "calling_mobiles": _join_unique(cr["calling_mobile"]),
                    "institute": _join_unique(cr["institute"]) or (_val(alloc["institute"]) if alloc is not None else None),
                    "issue_categories": _join_unique(cr["issue_category"]),
                    "outcomes": _join_unique(cr["outcome"]),
                    "concern": _concern(cr), "n_calls": int(r.n_calls),
                    "snapshot_at": ts,
                    "orig_loan_stage": stage, "orig_lender": _val(p["lender"]),
                    "orig_overdue": od, "orig_charges": chg, "orig_dpd": dpd,
                    "orig_dpd_bucket": dpd_bucket(dpd, buckets),
                    "orig_emi_outstanding": _val(p["emi_outstanding"]), "orig_total_paid": _val(p["total_paid"]),
                    "orig_last_payment_date": _val(p["last_payment_date"]),
                    "case_type": (labels["overdue"] if (od or 0) > thr else
                                  labels["charges_only"] if (chg or 0) > thr else "Needs review"),
                    "orig_alloc_cm": orig_cm,
                    "orig_alloc_agent": _val(alloc["agent_name"]) if alloc is not None else None,
                    "orig_charges_cm": _val(chrow["charges_cm"]) if chrow is not None else None,
                    "assigned_cm": assigned, "cm_source": src,
                    "cm_assigned_by": current_user() if assigned else None,
                    "cm_assigned_at": ts if assigned else None,
                })
        id_rows.append({"app_id": a, "call_nos": ",".join(map(str, r.call_nos)), "n_calls": int(r.n_calls),
                        "listed_as": r.listed_as, "match_status": status})

    with transaction() as conn:
        batch_id = new_batch_id(conn, calling_date)
        n_exc_pending = len(exceptions)
        conn.execute(
            """INSERT INTO batches (batch_id, created_at, created_by, calling_date, inbound_file_id,
               portfolio_file_id, allocation_file_id, charges_file_id, total_calls, unidentified_calls,
               total_app_ids, total_cases, processing_status, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (batch_id, ts, current_user(), calling_date, inbound_file_id, portfolio_file_id,
             allocation_file_id, charges_file_id, len(calls), len(parsed.unidentified), len(idx),
             len(case_rows), "Processed with exceptions" if n_exc_pending else "Processed", notes),
        )
        cdf = calls.drop(columns=["id_list"]).copy()
        cdf.insert(0, "batch_id", batch_id)
        cdf.to_sql("calls", conn, if_exists="append", index=False)
        idf = pd.DataFrame(id_rows)
        idf.insert(0, "batch_id", batch_id)
        idf.to_sql("batch_app_ids", conn, if_exists="append", index=False)
        if case_rows:
            kdf = pd.DataFrame(case_rows)
            kdf["batch_id"] = batch_id
            kdf.to_sql("cases", conn, if_exists="append", index=False)
        conn.executemany(
            "INSERT INTO exceptions (batch_id, app_id, call_no, type, detail, created_at) VALUES (?,?,?,?,?,?)",
            [(batch_id, a, cn, t, d, ts) for a, cn, t, d in exceptions],
        )
        audit(conn, "create_batch", batch_id, {
            "calls": len(calls), "app_ids": len(idx), "cases": len(case_rows), "exceptions": len(exceptions),
            "portfolio_file_id": portfolio_file_id, "allocation_file_id": allocation_file_id,
            "charges_file_id": charges_file_id,
        })
    return batch_id


def assign_cm(batch_id: str, app_id: str, cm: str, note: str | None = None) -> None:
    """Manual CM assignment for unallocated / on-hold cases. The original allocation is untouched."""
    cm = (cm or "").strip()
    if not cm:
        raise ValueError("CM name is required")
    with transaction() as conn:
        old = conn.execute("SELECT assigned_cm FROM cases WHERE batch_id=? AND app_id=?", (batch_id, app_id)).fetchone()
        if old is None:
            raise ValueError("Case not found")
        conn.execute(
            "UPDATE cases SET assigned_cm=?, cm_source='manual', cm_assigned_by=?, cm_assigned_at=? WHERE batch_id=? AND app_id=?",
            (cm, current_user(), now(), batch_id, app_id),
        )
        conn.execute(
            f"""UPDATE exceptions SET status='Resolved', resolved_at=?, resolved_by=?, resolution_note=?
                WHERE batch_id=? AND app_id=? AND status!='Resolved' AND type IN ({','.join('?' * len(CM_EXCEPTION_TYPES))})""",
            (now(), current_user(), f"CM assigned manually: {cm}" + (f" – {note}" if note else ""),
             batch_id, app_id, *CM_EXCEPTION_TYPES),
        )
        audit(conn, "assign_cm", batch_id, {"app_id": app_id, "from": old["assigned_cm"], "to": cm, "note": note})
        _refresh_status(conn, batch_id)


def resolve_exceptions(ids: list[int], status: str, note: str | None) -> None:
    if status not in ("Pending", "Resolved", "Reprocessing"):
        raise ValueError(status)
    with transaction() as conn:
        batches = set()
        for i in ids:
            row = conn.execute("SELECT batch_id FROM exceptions WHERE id=?", (i,)).fetchone()
            if row:
                batches.add(row["batch_id"])
            conn.execute(
                "UPDATE exceptions SET status=?, resolved_at=?, resolved_by=?, resolution_note=? WHERE id=?",
                (status, now() if status == "Resolved" else None, current_user(), note, i),
            )
        audit(conn, "update_exceptions", None, {"ids": ids, "status": status, "note": note})
        for b in batches:
            if b:
                _refresh_status(conn, b)


def _refresh_status(conn, batch_id: str) -> None:
    pending = conn.execute(
        "SELECT COUNT(*) FROM exceptions WHERE batch_id=? AND status!='Resolved'", (batch_id,)
    ).fetchone()[0]
    conn.execute("UPDATE batches SET processing_status=? WHERE batch_id=?",
                 ("Processed with exceptions" if pending else "Processed", batch_id))


def list_batches() -> pd.DataFrame:
    from .db import query_df

    return query_df(
        """SELECT b.batch_id, b.calling_date, b.created_at, b.total_calls, b.total_app_ids, b.total_cases,
                  b.processing_status, b.email_status, b.recheck_status, b.mis_status,
                  (SELECT COUNT(*) FROM exceptions e WHERE e.batch_id=b.batch_id AND e.status!='Resolved') AS open_exceptions
           FROM batches b ORDER BY b.created_at DESC"""
    )


def get_batch(batch_id: str):
    conn = connect()
    try:
        return conn.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
    finally:
        conn.close()
