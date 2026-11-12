"""Catalogue of exception types shown in Exception Management."""

EXCEPTION_TYPES = {
    "UNIDENTIFIED_CALL":      "Call has no Application ID",
    "MISSING_IN_PORTFOLIO":   "Live App ID not found in Loan Live Portfolio",
    "NO_CM_ALLOCATION":       "No CM allocation found",
    "ALLOCATION_ON_HOLD":     "Allocation on hold / not a real CM",
    "MISSING_AMOUNTS":        "Overdue or charges value missing in portfolio",
    "MISSING_DPD":            "DPD missing in portfolio",
    "DUPLICATE_IN_PORTFOLIO": "App ID appears more than once in portfolio",
    "DUPLICATE_IN_ALLOCATION": "App ID appears more than once in CM allocation",
    "NON_LIVE_STAGE":         "Case has dues but loan stage is not 'Loan Live'",
}

# exception types that are cleared when a CM is assigned manually
CM_EXCEPTION_TYPES = ("NO_CM_ALLOCATION", "ALLOCATION_ON_HOLD")


def label(code: str) -> str:
    return EXCEPTION_TYPES.get(code, code)
