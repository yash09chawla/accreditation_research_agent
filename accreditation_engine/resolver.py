"""OpenAI name resolution — used only when a name does not match the official lists directly.

It asks OpenAI (Responses API + web_search) for the institution's OFFICIAL name, former names, abbreviations and
official website, using public information only (the inputs pass guard.check_public first). The answer is never
trusted for accreditation: the returned names are matched against the official UGC / AICTE lists again, and only
a hit in a list counts. Answers are cached on disk (30 days) so a repeated name costs nothing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field

from . import guard
from .settings import Settings
from .text import norm

log = logging.getLogger("accreditation_engine.resolver")

# USD per 1M tokens (input, output) — approximate list prices, for the cost figure only.
PRICES = {"gpt-5.4-mini": (0.75, 4.50), "gpt-4.1-mini": (0.40, 1.60), "gpt-4o-mini": (0.15, 0.60)}
WEB_SEARCH_CALL_USD = 0.01
CACHE_DAYS = 30


@dataclass
class Resolution:
    university_names: list[str] = field(default_factory=list)
    institute_names: list[str] = field(default_factory=list)
    website: str = ""
    state: str = ""
    country: str = ""
    category: str = ""
    notes: str = ""
    model: str = ""
    cost_usd: float = 0.0
    seconds: float = 0.0
    cached: bool = False


PROMPT = """You help verify the accreditation of an educational institution in India. Using official and other
reliable public web sources, identify the institution described below. Do NOT decide whether it is accredited.

University (as written by the requester): "{university}"
{institute_line}{degree_line}{state_line}
Return ONLY a JSON object with these keys:
  "university_official_name": the university's current official name exactly as the University Grants Commission
      (UGC) lists it, or "" if unknown,
  "university_other_names": list of former names, abbreviations and common spelling variants of the university,
  "university_website": official website URL or "",
  "university_state": Indian state / union territory of the university's main campus or "",
  "country": country of the university,
  "category": one of "Central University", "State University", "State Private University",
      "Deemed to be University", "Institute of National Importance", "Autonomous/Affiliated College",
      "Not an Indian institution", "Unknown",
{institute_keys}  "notes": one short sentence on how you identified it (or why you could not).
"""

INSTITUTE_KEYS = """  "institute_official_name": the institute's official name exactly as the AICTE approved-institutions list
      would write it, or "",
  "institute_other_names": list of former names and variants of the institute,
"""


class Resolver:
    def __init__(self, settings: Settings):
        self.s = settings
        self._client = None
        self._lock = threading.Lock()
        self._cache_path = settings.cache_dir / "resolver_cache.json"

    @property
    def available(self) -> bool:
        return self.s.llm_available

    def _client_(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.s.openai_api_key, timeout=self.s.openai_timeout_s, max_retries=2)
        return self._client

    def _key(self, university, institute, degree, state) -> str:
        raw = "|".join(norm(x or "") for x in (university, institute, degree, state))
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def _cache_get(self, key: str) -> Resolution | None:
        with self._lock:
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        rec = data.get(key)
        if not rec or time.time() - rec.get("_t", 0) > CACHE_DAYS * 86400:
            return None
        rec = {k: v for k, v in rec.items() if not k.startswith("_")}
        r = Resolution(**rec)
        r.cached, r.cost_usd, r.seconds = True, 0.0, 0.0
        return r

    def _cache_put(self, key: str, r: Resolution) -> None:
        with self._lock:
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            data[key] = {**asdict(r), "_t": time.time()}
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._cache_path)

    def resolve(self, university: str, institute: str | None = None, degree: str | None = None,
                state: str | None = None) -> Resolution:
        if not self.available:
            raise RuntimeError("OpenAI is not configured (OPENAI_API_KEY missing or ARA_DISABLE_LLM=1)")
        key = self._key(university, institute, degree, state)
        hit = self._cache_get(key)
        if hit:
            return hit
        prompt = PROMPT.format(
            university=university,
            institute_line=f'Institute / affiliated college: "{institute}"\n' if institute else "",
            degree_line=f'Programme: "{degree}"\n' if degree else "",
            state_line=f'State (hint): "{state}"\n' if state else "",
            institute_keys=INSTITUTE_KEYS if institute else "")
        guard.check_public({"prompt": prompt})
        model = self.s.openai_model
        t0 = time.time()
        r = self._client_().responses.create(model=model, tools=[{"type": "web_search"}],
                                             reasoning={"effort": "low"}, input=prompt)
        n_search = sum(1 for o in r.output if getattr(o, "type", "") == "web_search_call")
        pi, po = PRICES.get(model, (1.0, 4.0))
        it = getattr(r.usage, "input_tokens", 0) or 0
        ot = getattr(r.usage, "output_tokens", 0) or 0
        cost = round(it / 1e6 * pi + ot / 1e6 * po + n_search * WEB_SEARCH_CALL_USD, 5)
        data = _parse_json(r.output_text)
        guard.audit(self.s.audit_dir, "name-resolution",
                    {"model": model, "prompt": prompt, "searches": n_search, "usd": cost,
                     "answer": {k: data.get(k) for k in ("university_official_name", "institute_official_name",
                                                          "university_website", "category", "country")}})
        res = Resolution(
            university_names=_names(data.get("university_official_name"), data.get("university_other_names")),
            institute_names=_names(data.get("institute_official_name"), data.get("institute_other_names")),
            website=_str(data.get("university_website")), state=_str(data.get("university_state")),
            country=_str(data.get("country")), category=_str(data.get("category")), notes=_str(data.get("notes")),
            model=model, cost_usd=cost, seconds=round(time.time() - t0, 1))
        self._cache_put(key, res)
        return res


def _str(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _names(official, others) -> list[str]:
    out = []
    for n in [official] + (list(others) if isinstance(others, list) else []):
        if isinstance(n, str) and len(n.strip()) > 2 and n.strip() not in out:
            out.append(n.strip())
    return out[:12]


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        d = json.loads(m.group(0) if m else text)
        return d if isinstance(d, dict) else {}
    except Exception:
        log.warning("resolver: non-JSON answer: %s", text[:200])
        return {}
