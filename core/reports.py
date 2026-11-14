"""Read-side: tables, CM-wise summaries, pivots and Excel export."""
from __future__ import annotations

import io

import pandas as pd
from openpyxl.styles import Font

from .db import query_df
from .exception_types import label

UNASSIGNED = "Unassigned"

CASE_COLUMNS = {
    "app_id": "Application ID",
    "student_name": "Student Name",
    "orig_overdue": "Overdue",
    "orig_charges": "Charges",
    "orig_dpd": "DPD (Days)",
    "orig_dpd_bucket": "DPD Bucket",
    "case_type": "Case Type",
    "assigned_cm": "CM / Team",
    "issue_categories": "Issue Category",
    "concern": "Customer Concern",
    "institute": "Institute",
    "calling_mobiles": "Calling Mobile",
    "parent_name": "Parent Name",
    "mobile": "Registered Mobile",
    "orig_alloc_agent": "Agent",
    "orig_charges_cm": "Charges CM (info)",
    "orig_loan_stage": "Loan Stage",
    "orig_lender": "Lender",
    "outcomes": "Call Outcome",
    "n_calls": "No. of Calls",
    "orig_alloc_cm": "CM in Allocation File",
    "cm_source": "CM Source",
}


def cases(batch_id: str) -> pd.DataFrame:
    return query_df("SELECT * FROM cases WHERE batch_id=? ORDER BY assigned_cm, app_id", (batch_id,))


def cases_display(df: pd.DataFrame) -> pd.DataFrame:
    out = df[list(CASE_COLUMNS)].rename(columns=CASE_COLUMNS).copy()
    out["CM / Team"] = out["CM / Team"].fillna(UNASSIGNED)
    return out


def calls(batch_id: str) -> pd.DataFrame:
    return query_df("SELECT * FROM calls WHERE batch_id=? ORDER BY call_no", (batch_id,))


def app_ids(batch_id: str) -> pd.DataFrame:
    return query_df("SELECT * FROM batch_app_ids WHERE batch_id=? ORDER BY match_status, app_id", (batch_id,))


def exceptions(batch_id: str | None = None, status: str | None = None) -> pd.DataFrame:
    sql, p = "SELECT * FROM exceptions WHERE 1=1", []
    if batch_id:
        sql += " AND batch_id=?"; p.append(batch_id)  # noqa: E702
    if status:
        sql += " AND status=?"; p.append(status)  # noqa: E702
    df = query_df(sql + " ORDER BY id", tuple(p))
    df.insert(df.columns.get_loc("type") + 1, "exception", df["type"].map(label))
    return df


def headline(df: pd.DataFrame) -> dict:
    od = df["orig_overdue"].fillna(0) > 0
    ch = df["orig_charges"].fillna(0) > 0
    return {
        "Total inbound cases": len(df),
        "Cases with overdue": int(od.sum()),
        "Cases with charges": int(ch.sum()),
        "Cases with both": int((od & ch).sum()),
        "Total overdue (₹)": float(df["orig_overdue"].fillna(0).sum()),
        "Total charges (₹)": float(df["orig_charges"].fillna(0).sum()),
        "Unassigned cases": int(df["assigned_cm"].isna().sum()),
    }


def cm_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = df.assign(
        cm=df["assigned_cm"].fillna(UNASSIGNED),
        od=df["orig_overdue"].fillna(0), chg=df["orig_charges"].fillna(0),
    )
    g = d.groupby("cm").agg(
        Cases=("app_id", "count"),
        **{"With Overdue": ("od", lambda s: int((s > 0).sum())),
           "With Charges": ("chg", lambda s: int((s > 0).sum())),
           "Total Overdue": ("od", "sum"),
           "Total Charges": ("chg", "sum")},
    )
    both = d[(d.od > 0) & (d.chg > 0)].groupby("cm")["app_id"].count()
    g.insert(3, "With Both", both.reindex(g.index).fillna(0).astype(int))
    g["Total Outstanding"] = g["Total Overdue"] + g["Total Charges"]
    g = g.sort_values("Cases", ascending=False)
    g.loc["Grand Total"] = g.sum(numeric_only=True)
    g.index.name = "CM / Team"
    return g.reset_index()


def case_type_pivot(df: pd.DataFrame, bucket_order: list[str]) -> pd.DataFrame:
    """Same layout as the manual 'Pivots' sheet: Charges, DPD Bucket (+ DPD sub-rows), Grand Total."""
    if df.empty:
        return pd.DataFrame()
    rows = []
    for ctype, grp in df.groupby("case_type", sort=True):
        rows.append({"Row Labels": ctype, "Cases": len(grp),
                     "Sum of Overdue": grp["orig_overdue"].fillna(0).sum(),
                     "Sum of Charges": grp["orig_charges"].fillna(0).sum()})
        if grp["orig_overdue"].fillna(0).gt(0).any():
            for b in bucket_order + [None]:
                sub = grp[grp["orig_dpd_bucket"].isna()] if b is None else grp[grp["orig_dpd_bucket"] == b]
                if len(sub):
                    rows.append({"Row Labels": f"    {b or 'DPD missing'}", "Cases": len(sub),
                                 "Sum of Overdue": sub["orig_overdue"].fillna(0).sum(),
                                 "Sum of Charges": sub["orig_charges"].fillna(0).sum()})
    rows.append({"Row Labels": "Grand Total", "Cases": len(df),
                 "Sum of Overdue": df["orig_overdue"].fillna(0).sum(),
                 "Sum of Charges": df["orig_charges"].fillna(0).sum()})
    return pd.DataFrame(rows)


def cm_dpd_matrix(df: pd.DataFrame, bucket_order: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = df.assign(cm=df["assigned_cm"].fillna(UNASSIGNED), b=df["orig_dpd_bucket"].fillna("DPD missing"))
    m = pd.crosstab(d["cm"], d["b"], margins=True, margins_name="Total")
    cols = [b for b in bucket_order + ["DPD missing"] if b in m.columns] + ["Total"]
    m = m[cols]
    m.index.name = "CM / Team"
    return m.reset_index()


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            safe = name[:31]
            df.to_excel(xw, sheet_name=safe, index=False)
            ws = xw.sheets[safe]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for col in ws.columns:
                width = max((len(str(c.value)) if c.value is not None else 0) for c in list(col)[:300])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    return buf.getvalue()


def batch_workbook(batch_id: str, bucket_order: list[str]) -> bytes:
    k = cases(batch_id)
    summary = pd.DataFrame(list(headline(k).items()), columns=["Metric", "Value"]) if len(k) else pd.DataFrame()
    return to_excel({
        "Summary": summary,
        "CM Summary": cm_summary(k),
        "Cases": cases_display(k) if len(k) else k,
        "Case Type Pivot": case_type_pivot(k, bucket_order),
        "CM x DPD Bucket": cm_dpd_matrix(k, bucket_order),
        "Calls": calls(batch_id),
        "All App IDs": app_ids(batch_id),
        "Exceptions": exceptions(batch_id),
    })


def cm_workbook(batch_id: str, cm: str) -> bytes:
    k = cases(batch_id)
    k = k[k["assigned_cm"].fillna(UNASSIGNED) == cm]
    return to_excel({cm[:31]: cases_display(k)})
