"""UGC university lists — the JSON endpoint behind ugc.gov.in/universitydetails (the same data the public pages
show), one list per category: Central, State, State Private, Deemed to be University. Cached on disk and
refreshed after `ugc_max_age_days`; a stale cache is used if the site is down."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field

from ..settings import UGC_LIST_TYPES, Settings
from ..states import canonical_state
from ..text import base_name, former_names, norm
from .http import atomic_write, fetch, is_fresh

log = logging.getLogger("accreditation_engine.sources")


@dataclass(eq=False)
class UgcRecord:
    list_type: int
    category: str                 # "State University" …
    name: str                     # exactly as UGC lists it
    state: str
    address: str
    pin: str
    status: str                   # e.g. "2(f) & 12B"
    website: str
    keys: list[str] = field(default_factory=list)   # normalised names used for matching (official + former)

    def as_dict(self) -> dict:
        return {"name": self.name, "category": self.category, "state": self.state, "address": self.address,
                "pin": self.pin, "ugc_status": self.status, "website": self.website}


class UgcSource:
    def __init__(self, settings: Settings):
        self.s = settings
        self._lock = threading.Lock()
        self._records: list[UgcRecord] | None = None
        self.loaded_at: float | None = None
        self.errors: list[str] = []

    def _path(self, t: int):
        return self.s.cache_dir / f"ugc_{t}.json"

    def _download(self, t: int) -> None:
        raw = fetch(self.s.ugc_api_url.format(t=t), self.s.user_agent, 40, {"X-Requested-With": "XMLHttpRequest"})
        data = json.loads(raw)
        rows = data.get("List") if isinstance(data, dict) else None
        if not rows:
            raise RuntimeError(f"UGC list {t}: unexpected response (no 'List')")
        atomic_write(self._path(t), json.dumps(rows).encode())

    def records(self, refresh: bool = False) -> list[UgcRecord]:
        with self._lock:
            if self._records is not None and not refresh:
                return self._records
            out, errors = [], []
            for t, (label, _) in UGC_LIST_TYPES.items():
                p = self._path(t)
                if refresh or not is_fresh(p, self.s.ugc_max_age_days):
                    try:
                        self._download(t)
                    except Exception as e:
                        errors.append(f"UGC {label} list download failed: {e}")
                        log.warning("UGC list %s download failed: %s", t, e)
                if not p.exists():
                    continue
                for r in json.loads(p.read_text(encoding="utf-8")):
                    name = (r.get("uni_name") or "").strip()
                    if not name:
                        continue
                    keys = []
                    for k in (name, base_name(name), base_name(name).split(",")[0], *former_names(name)):
                        n = norm(k)
                        if n and n not in keys:
                            keys.append(n)
                    out.append(UgcRecord(
                        list_type=t, category=label, name=" ".join(name.split()),
                        state=canonical_state(r.get("state")) or (r.get("state") or "").strip(),
                        address=" ".join((r.get("address") or "").split()), pin=(r.get("Zip") or "").strip(),
                        status=(r.get("status") or "").strip(), website=(r.get("url") or "").strip(), keys=keys))
            if not out:
                raise RuntimeError("UGC lists unavailable (no cache and download failed): " + "; ".join(errors))
            self._records, self.errors, self.loaded_at = out, errors, time.time()
            return out

    def status(self) -> dict:
        files = {t: self._path(t) for t in UGC_LIST_TYPES}
        return {"records": len(self._records or []),
                "lists": {UGC_LIST_TYPES[t][0]: {"cached": p.exists(),
                                                 "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                                            time.localtime(p.stat().st_mtime))
                                                 if p.exists() else None}
                          for t, p in files.items()},
                "errors": self.errors}
