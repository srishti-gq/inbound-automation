# Inbound Calling & Recovery Follow-up Dashboard – GrayQuest

Internal dashboard that replaces the Excel workflow for inbound AI-calling follow-ups:
upload → enrich → CM-wise allocation → (emails, recheck, MIS – coming in later phases).

## Run it from VS Code (Windows / Mac / Linux)

Requires **Python 3.10 or newer** (check with `python --version`).

1. Get the code (first time only), then open the folder in VS Code
   ```bash
   git clone https://github.com/srishti-gq/inbound-automation.git
   cd inbound-automation
   git checkout claude/blissful-wozniak-4vdqmc
   ```
   Later, to get updates: `git pull`

2. Open the VS Code terminal (**Terminal → New Terminal**) and create a virtual environment (first time only)
   ```bash
   python -m venv .venv
   ```
3. Activate it (every time you open a new terminal)
   - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
     – if blocked, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
   - Windows (cmd): `.venv\Scripts\activate.bat`
   - Mac/Linux: `source .venv/bin/activate`
4. Install packages (first time, and whenever `requirements.txt` changes)
   ```bash
   pip install -r requirements.txt
   ```
5. Start the dashboard
   ```bash
   streamlit run app.py
   ```
   It opens at http://localhost:8501. Stop it with **Ctrl + C** in the terminal.

Run the automated tests (synthetic data only): `pytest -q`

## How to use (Phase 1)

1. **Upload Inbound Report → Step 1**: upload the *Loan Live Portfolio* and the *CM Allocation (Overdue)* file
   (and optionally the *Charges Allocation*). Set the data date of each file. You only re-upload when you have a newer file.
2. **Step 2**: upload the inbound calling report. Check the preview (calls, App IDs, detected columns).
3. **Step 3**: confirm the calling date and file versions → **Process & create batch**.
4. **CM-wise Allocation**: assign a CM to unassigned cases (not in allocation file / on Hold), review CM totals,
   download CM-wise case lists.
5. **Batch Management**: full report per batch (Excel download), calls, all App IDs, exceptions, audit trail.
6. **Exception Management**: review and resolve exceptions with a note.

## Processing rules (same as the manual Main_Data sheet)

1. Split each call's `App ID` list into individual IDs (one case = one App ID per batch; repeat calls are linked).
2. Look up every ID in the Loan Live Portfolio.
3. Case if **overdue > 0 or charges > 0**. Case type = `DPD Bucket` if overdue > 0, else `Charges`.
4. DPD bucket from portfolio overdue days (ranges in `config/settings.yaml`).
5. CM / Team from the CM Allocation file. Missing or "Hold…" → exception + manual assignment.
6. Every ID is accounted for: *Case created / No dues / Not in portfolio / Missing amounts*.

## Data safety

- All data lives in the local `data/` folder (SQLite database + an untouched copy of every uploaded file).
  `data/` and all Excel files are git-ignored – customer data is never committed.
- Original snapshot and original CM allocation are **read-only** (enforced by database triggers).
- Every upload, batch, assignment and exception change is written to the audit log.
- **Backup**: copy the `data/` folder.

## Configuration (no code changes needed)

- `config/column_mapping.yaml` – which column headers to look for in each file.
- `config/settings.yaml` – DPD buckets, "Not Available"-style markers, hold patterns, Batch ID prefix.
- Both can also be edited from **Settings** in the dashboard.

## Project layout

```
app.py                 Streamlit entry point + navigation
core/                  processing logic (no UI)
  excel_io.py          sheet / header / column auto-detection
  sources.py           portfolio & allocation file versions + lookups
  inbound.py           inbound report parsing
  batch.py             enrichment, cases, exceptions, manual CM assignment
  reports.py           summaries, pivots, Excel export
  db.py                SQLite schema, audit log, read-only triggers
views/                 one file per dashboard page
config/                YAML configuration
docs/                  analysis & business rules
tests/                 automated tests (synthetic data)
```

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Upload, enrichment, exceptions, CM-wise allocation, reports | ✅ Basic version |
| 2 | Email drafts, approval, sending, logs | Next |
| 3 | Outstanding recheck & payment classification | |
| 4 | Google Sheet MIS updates | |
| 5 | Recovery analytics | |
