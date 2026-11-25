"""Input guard and outbound audit log.

The engine needs PUBLIC institution information only (university / institute name, degree, state). Inputs are
rejected if they look like personal data (e-mail, phone, ID numbers, dates of birth), because the university name
may be sent to OpenAI for name resolution. Every OpenAI request is appended to data/audit/outbound.jsonl with its
full prompt so an auditor can see exactly what left the machine.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

PATTERNS = [
    ("e-mail address", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("phone number", re.compile(r"\+\d{1,3}[\s-]?\d{6,}|(?<![\d-])\d{10}(?![\d-])")),
    ("ID-like number (7+ digits)", re.compile(r"(?<![\d.])\d{7,}(?![\d.])")),
    ("date of birth-like date", re.compile(r"\b\d{1,2}[-/.](?:\d{1,2}|[A-Za-z]{3})[-/.](?:19|20)\d{2}\b")),
]

_lock = threading.Lock()


class InputRejected(ValueError):
    pass


def problems(text: str) -> list[str]:
    return [label for label, pat in PATTERNS if pat.search(text or "")]


def check_public(fields: dict[str, str | None]) -> None:
    for name, value in fields.items():
        found = problems(value or "")
        if found:
            raise InputRejected(f"'{name}' looks like personal data ({', '.join(found)}). This engine accepts public "
                                f"institution information only.")


def audit(audit_dir: Path, service: str, payload: dict) -> None:
    rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "service": service, **payload}
    audit_dir.mkdir(parents=True, exist_ok=True)
    with _lock, open(audit_dir / "outbound.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
