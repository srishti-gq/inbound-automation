# 01 – Source File Analysis (Pre-development)

Status: **DRAFT – awaiting business sign-off.** No application code is written until the open questions below are answered.
Only column names and aggregate counts are recorded here. No customer data is stored in this repository.

## Files received

| # | File | Role (as understood) | Sheets | Rows | Key column |
|---|------|----------------------|--------|------|-----------|
| 1 | `loan_live-Portfolio-Metrics-05-11-2026.xlsx` | Loan Live Portfolio (latest loan-level snapshot) | Sheet1 | 148,657 | `GQ Application ID` (unique, integer) |
| 2 | `October_Data_6.xlsx` | Overdue (EMI) CM allocation + monthly collection tracker | Sheet1 | 13,716 | `GQ Application IDs` (unique, integer) |
| 3 | `Charges_Allocation-October26_2.xlsx` | Charges CM allocation + charges collection tracker | Loan Live, Loan Closed, Sheet9, WC Cases, settlement case, removed cases, MIS | 5,704 (Loan Live) / 1,266 (Loan Closed) | `APP ID` (NOT unique) |
| – | Inbound calling report | **NOT YET RECEIVED** | | | |
| – | Existing MIS sheet | **NOT YET RECEIVED** (the 2-column `MIS` tab in file 3 does not look like the full MIS) | | | |

The key column has a different name in every file, which confirms column mapping must be configurable.

---

## File 1 – Loan Live Portfolio

| Column | Type observed | Notes |
|---|---|---|
| GQ Application ID | int | Unique. Primary key. |
| Lender Loan Number | text | |
| Loan Stage | text | Loan Live (146,617), Settled, Drop Out – Refund Received, Drop out – Partial Refund Received, Drop Out – Refund Pending |
| Current Overdue Amount | int | 108,480 rows > 0 |
| Last Unpaid EMI Due Date | text | Mixed `d-m-yyyy`, plus literal `Upfront Data Not Found` |
| EMI Amount | int / numeric-text | Some values stored as text |
| Total Payment made till date | int | **Cumulative payments.** 1,791 rows = `Not Available` |
| LENDER | text | 27 lender variants |
| Current Overdue days | int | = DPD. 13 rows = `Not Available` |
| Total EMI Outstanding Amount | int | Not the same as overdue (equal in only ~12% of rows); appears to be total remaining EMI principal |
| Total Charges Outstanding Amount | int | = Pending Charges. 22,253 rows > 0 |
| Last Payment Date | text | `dd-mm-yyyy hh:mm:ss`, or `Not Available` |
| Amount Settled to Lender | int | |

Observations:
- **No DPD Bucket column.** It must be calculated from `Current Overdue days`.
- **No customer details** (name, mobile, institute). These must come from the inbound report or an allocation file.
- **100,420 rows have overdue > 0 but DPD = 0.** This looks like the EMI due on the snapshot date. Counting "cases with overdue" by amount alone will include these.
- **`Total Payment made till date` is cumulative.** If it is reliable, then *actual payment = latest cumulative − original cumulative*. That answers the "new EMI accrued + partial payment" problem without a separate ledger (see Q9).
- Placeholder text (`Not Available`, `Upfront Data Not Found`) appears inside number and date columns. It must be treated as missing, not as zero.

## File 2 – October_Data (Overdue allocation)

| Column group | Columns |
|---|---|
| Customer | Name of Student, Parent Name, Institute Name, Mobile Number, Group Name, State, City, Institute location |
| Loan | Loan Stage (Loan Live / Loan Live – partial / Dropout / Refund Denied), Loan Amount, LENDER, EMI Amount, Total Outstanding, FSF/non, Edtech |
| Allocation | Date (4 allocation dates), Remark, **Name**, **CM Name**, Senior CM Name |
| Collection | DPD (bucket text), Current Overdue, Amount Received, Pending Overdue, Status |

Observations:
- `DPD` is a **bucket label**: `0 to 30`, `31 to 60`, `61 to 90`, `91 to 180`, `180 to 360`, `360+`.
- `Pending Overdue = Current Overdue − Amount Received` for 100% of rows. `Status` is derived from it: Unpaid (7,673) / Part Collected (627) / Fully Paid (5,416). This is the same partial-payment logic you described.
- **Two-level allocation:** `CM Name` has 11 values. `Name` has about 50 values and looks like the agent/caller under a CM. Some agents work under more than one CM. `Senior CM Name` is always `-`.
- **Hold rows:** `Hold till 15th`, `Hold till 15h` (typo), and `Hold till 18th` appear as both CM Name and Name (2,665 rows). These are not real CMs.
- **Spelling and casing variants** exist in `Name` (the same person written in upper and lower case).
- No team column and no email column.
- 520 IDs are not in the 05-11 portfolio.

## File 3 – Charges Allocation

- Main sheet `Loan Live` has 5,704 rows but only 4,853 unique APP IDs. The same ID repeats across **Lots** (Lot 1–6, allocated on different dates). There are also `Manual Payment` rows that record a payment (Paid Amt + payment date stored in the `Paid Status` column).
- 241 duplicated IDs are assigned to **2 different CMs** across lots.
- The CM column `Name` has about 6 real people, but spelled 14 different ways (full name, first name only, misspellings, lowercase).
- `Allocation Date` mixes real dates with text such as `23.10.2026`.
- `DPD`, `Payment Date`, `Payment-Source`, `NOC Status`, `Exc`, and `Alt No` are completely empty.
- `Actual OS` vs `total_charges_out`: these agree in only 68% of rows. Neither matches the portfolio charges consistently, because the snapshot dates differ.
- `Loan Closed` sheet: 1,266 IDs, **none** of them in the live portfolio.
- `Mail ID` is the **customer** email, not the CM email.
- **3,663 IDs are in both the overdue allocation and the charges allocation.** One customer can therefore have two CMs.

## Proposed default rules (subject to sign-off)

1. **Key normalisation:** read Application IDs as text, trim spaces, and drop a trailing `.0`. All matching is exact on the normalised ID.
2. **Placeholder text** in number or date columns is stored as missing and raises a "missing data" exception. It is never converted to 0.
3. **DPD Bucket** is calculated from portfolio `Current Overdue days` using the same labels as File 2. Boundaries are to be confirmed (Q8).
4. **Name aliases** live in a Settings table (variant → canonical CM name → email). Any name not found raises an exception.
5. Hold rows go to the exception "Allocation on hold" and are never emailed.

## Open questions (blocking Phase 1)

1. **Inbound calling report:** please share a sample with real headers and masked rows. It is the main input and I haven't seen it yet.
2. **Which allocation source?** Should the system use both File 2 (overdue CM) and File 3 (charges CM)? Are these replaced with a new file every month?
3. **Case in both files** (3,663 IDs): should one case go to both the overdue CM and the charges CM, or should one take priority?
4. **Who receives the email:** `CM Name` (11 people) or `Name` (agent, about 50 people)? And what is "Team": is it `CM Name`?
5. **Hold rows** (`Hold till 15th/18th`): should these be excluded and shown as exceptions, or allocated to someone?
6. **Charges duplicates:** should the latest lot's CM win? Should `Manual Payment` rows be ignored, or used as payment records? Which sheets count: `Loan Live` only?
7. **CM email IDs:** please share the list (CM name, email, CC/team lead).
8. **DPD buckets:** please confirm the boundaries. Proposed: 0–30, 31–60, 61–90, 91–180, 181–360, 360+. Note that "180 to 360" overlaps "91 to 180" at 180. Should DPD 0 with overdue > 0 count as "0 to 30"?
9. **Actual payment:** may I use the change in `Total Payment made till date` as the actual payment received? Does that figure include payments against **charges**, or only EMIs? Is there any other transaction or ledger export?
10. **Fully Paid definition:** latest overdue = 0 **and** latest charges = 0? Or judged separately for overdue and for charges? Is there a rounding tolerance (for example, ₹0–₹10)?
11. **Loan Stage change at recheck** (for example, Live → Settled or Drop Out): which status should these get?
12. **Customer details:** take them from the inbound report or from File 2? (The portfolio has none.)
13. **Existing MIS sheet:** please share the real MIS template. Is it Excel or a Google Sheet?
14. **Email sending method** (SMTP / Gmail API / other) and the sending mailbox.
