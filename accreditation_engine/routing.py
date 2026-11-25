"""Which official body to target first.

AICTE approves technical and professional programmes (engineering, technology, management, computer applications,
pharmacy, architecture, hotel management, applied arts & crafts, design, town planning) and the institutions that
run them. UGC lists universities. Both lists are always searched; the route decides which body is reported first
when the institution appears in both, and which list's evidence leads the proof PDF.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TECHNICAL_PROGRAMMES = re.compile(
    r"\b(B\.?\s?E\b|B\.?\s?TECH|M\.?\s?E\b|M\.?\s?TECH|BACHELOR OF ENGINEERING|MASTER OF ENGINEERING|"
    r"BACHELOR OF TECHNOLOGY|MASTER OF TECHNOLOGY|ENGINEERING|DIPLOMA IN ENGINEERING|POLYTECHNIC|"
    r"MBA|M\.?\s?B\.?\s?A\b|PGDM|PGDBM|MASTER OF BUSINESS ADMINISTRATION|BUSINESS MANAGEMENT|"
    r"MCA|M\.?\s?C\.?\s?A\b|MASTER OF COMPUTER APPLICATIONS|BCA|B\.?\s?C\.?\s?A\b|BACHELOR OF COMPUTER APPLICATIONS|"
    r"B\.?\s?PHARM|M\.?\s?PHARM|D\.?\s?PHARM|PHARM\.?\s?D|PHARMACY|"
    r"B\.?\s?ARCH|M\.?\s?ARCH|ARCHITECTURE|TOWN PLANNING|B\.?\s?PLAN|M\.?\s?PLAN|"
    r"HOTEL MANAGEMENT|CATERING TECHNOLOGY|BHMCT|B\.?\s?H\.?\s?M\b|APPLIED ARTS|B\.?\s?DES|M\.?\s?DES|DESIGN)", re.I)

TECHNICAL_INSTITUTES = re.compile(
    r"\b(ENGINEERING|ENGG|TECHNOLOGY|TECHNOLOGICAL|POLYTECHNIC|INSTITUTE OF TECHNOLOGY|INSTITUTE OF MANAGEMENT|"
    r"BUSINESS SCHOOL|SCHOOL OF MANAGEMENT|PHARMACY|PHARMACEUTICAL|ARCHITECTURE|HOTEL MANAGEMENT|"
    r"COMPUTER APPLICATIONS)\b", re.I)


@dataclass
class Route:
    order: list[str]          # e.g. ["AICTE", "UGC"]
    technical: bool
    reason: str

    def as_dict(self) -> dict:
        return {"order": self.order, "technical": self.technical, "reason": self.reason}


def decide(university: str, institute: str | None, degree: str | None) -> Route:
    if degree and TECHNICAL_PROGRAMMES.search(degree):
        m = TECHNICAL_PROGRAMMES.search(degree).group(0)
        return Route(["AICTE", "UGC"], True, f"degree '{degree}' is a technical/professional programme ({m}) — "
                                            f"AICTE approves these programmes")
    if institute and TECHNICAL_INSTITUTES.search(institute):
        m = TECHNICAL_INSTITUTES.search(institute).group(0)
        return Route(["AICTE", "UGC"], True, f"institute name indicates a technical institution ({m})")
    if not degree and not institute and TECHNICAL_INSTITUTES.search(university or ""):
        # e.g. "Gujarat Technological University": still a university → UGC first, AICTE also checked
        return Route(["UGC", "AICTE"], False, "university name only — UGC lists universities; AICTE also checked")
    if degree:
        return Route(["UGC", "AICTE"], False, f"degree '{degree}' is not an AICTE-regulated programme — UGC first")
    return Route(["UGC", "AICTE"], False, "university name only — UGC lists universities; AICTE also checked")
