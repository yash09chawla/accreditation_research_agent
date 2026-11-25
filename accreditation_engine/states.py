"""Indian states and union territories — canonical names (as written in the UGC lists) plus common aliases."""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # union territories
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]

ALIASES = {
    "AP": "Andhra Pradesh", "ARUNACHAL": "Arunachal Pradesh", "CG": "Chhattisgarh", "CHATTISGARH": "Chhattisgarh",
    "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir", "J AND K": "Jammu and Kashmir", "KA": "Karnataka",
    "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra", "ORISSA": "Odisha", "OR": "Odisha",
    "PONDICHERRY": "Puducherry", "PONDY": "Puducherry", "TN": "Tamil Nadu", "TAMILNADU": "Tamil Nadu",
    "TS": "Telangana", "TG": "Telangana", "UP": "Uttar Pradesh", "UK": "Uttarakhand", "UTTARANCHAL": "Uttarakhand",
    "WB": "West Bengal", "BENGAL": "West Bengal", "NEW DELHI": "Delhi", "NCT OF DELHI": "Delhi", "DL": "Delhi",
    "GJ": "Gujarat", "RJ": "Rajasthan", "PB": "Punjab", "HR": "Haryana", "BR": "Bihar", "JH": "Jharkhand",
    "AS": "Assam", "GA": "Goa", "ANDAMAN": "Andaman and Nicobar Islands", "DAMAN AND DIU":
    "Dadra and Nagar Haveli and Daman and Diu", "DADRA AND NAGAR HAVELI": "Dadra and Nagar Haveli and Daman and Diu",
}

_KEY = {re.sub(r"[^A-Z ]", "", s.upper().replace("&", " AND ")).strip(): s for s in STATES}


def _k(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", (s or "").upper().replace("&", " AND "))).strip()


def canonical_state(value: str | None) -> str | None:
    """'tamilnadu' / 'TN' / 'Tamil Nadu ' → 'Tamil Nadu'. None when empty or not recognisable."""
    k = _k(value or "")
    if not k:
        return None
    if k in _KEY:
        return _KEY[k]
    if k in ALIASES:
        return ALIASES[k]
    if k.replace(" ", "") in ALIASES:
        return ALIASES[k.replace(" ", "")]
    for key, name in _KEY.items():             # "Tamil Nadu Chennai" → starts with a state
        if k.startswith(key + " ") or k.endswith(" " + key):
            return name
    hit = process.extractOne(k, list(_KEY), scorer=fuzz.ratio, score_cutoff=85)
    return _KEY[hit[0]] if hit else None


def same_state(a: str | None, b: str | None) -> bool | None:
    """True / False when both are known, None when either is unknown."""
    ca, cb = canonical_state(a), canonical_state(b)
    if not ca or not cb:
        return None
    return ca == cb
