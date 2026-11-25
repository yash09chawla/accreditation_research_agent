"""Match a name against the official UGC and AICTE lists (local, milliseconds).

Rules (see status/decisions.md):
  * score = max(ratio, token_sort_ratio) between normalised name variants and the list's names (0-100); a fuzzy
    score also needs the distinctive (non-generic) words to be ≥ 70 % similar
  * accept ≥ UGC_MIN (92) / AICTE_MIN (93); exact normalised equality = 100
  * state given and the record is in another state: exact names are still accepted (with a warning); fuzzy names
    get −10, which rejects them
  * several records accepted with the same name (e.g. 9 × "Amity University"): the given state picks one; without
    a state the best is returned with the others (within 5 points) as `alternatives` and an ambiguity warning
  * the OpenAI resolver can only add NAMES to try; a match always comes from the official list itself
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .sources.aicte import AicteRow
from .sources.ugc import UgcRecord
from .states import canonical_state, same_state
from .text import GENERIC as _STOP, norm, variants, website_domain

UGC_MIN = 92
AICTE_MIN = 93
STATE_MISMATCH_PENALTY = 10


@dataclass
class Match:
    body: str                            # "UGC" | "AICTE"
    record: UgcRecord | AicteRow
    score: float
    method: str                          # "exact" | "fuzzy" | "website" (+ "resolved_name:" prefix)
    query_name: str                      # the input/resolved name that matched
    matched_key: str                     # normalised list name it matched
    state_check: bool | None             # True same state, False different, None unknown
    alternatives: list = field(default_factory=list)   # other accepted records (UgcRecord | AicteRow)

    @property
    def name(self) -> str:
        return self.record.name


DISTINCT_MIN = 70


def _distinct(n: str) -> str:
    return " ".join(t for t in n.split() if t not in _STOP)


def _score(a: str, b: str) -> float:
    """Similarity 0-100. Fuzzy (non-exact) scores also need the DISTINCTIVE words to agree (≥ 70 %), so
    'COLLEGE OF ENGINEERING PUNE' does not match 'PES COLLEGE OF ENGINEERING' just because the generic words do."""
    if a == b:
        return 100.0
    s = max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b))
    da, db = _distinct(a), _distinct(b)
    if not da or not db or max(fuzz.ratio(da, db), fuzz.token_set_ratio(da, db)) < DISTINCT_MIN:
        return min(s, 50.0)
    return s


class Matcher:
    def __init__(self, ugc: list[UgcRecord], aicte: list[AicteRow]):
        self.ugc = ugc
        self.aicte = aicte
        self._aicte_norms = [r.norm for r in aicte]
        # search keys: the name, and name + city / district (the list keeps the town in its own column, so
        # "Government Polytechnic, Bellampally" must be able to match "GOVERNMENT POLYTECHNIC" in BELLAMPALLY)
        self._aicte_keys: list[str] = []
        self._aicte_key_row: list[int] = []
        for i, r in enumerate(aicte):
            for k in dict.fromkeys([r.norm, norm(f"{r.name} {r.city}"), norm(f"{r.name} {r.district}")]):
                self._aicte_keys.append(k)
                self._aicte_key_row.append(i)
        places = set()
        for r in aicte:
            for t in f"{r.district} {r.city}".upper().split():
                t = re.sub(r"[^A-Z]", "", t)
                if len(t) >= 4 and t not in _STOP:
                    places.add(t)
        from .states import STATES
        for s in STATES:
            places.update(w for w in norm(s).split() if w not in _STOP and len(w) >= 3)
        self.place_words = frozenset(places)

    # ---------------------------------------------------------------- UGC
    def match_ugc(self, names: list[str], state: str | None = None, website: str | None = None,
                  method_prefix: str = "") -> Match | None:
        cands: dict[int, tuple[float, str, str, str]] = {}   # id(record) → (score, method, query, key)
        for q in [n for n in names if n and n.strip()]:
            for v in variants(q, self.place_words):
                for rec in self.ugc:
                    for key in rec.keys:
                        s = _score(v, key)
                        if s >= UGC_MIN - STATE_MISMATCH_PENALTY and s > cands.get(id(rec), (0,))[0]:
                            cands[id(rec)] = (s, "exact" if s == 100 else "fuzzy", q, key)
        dom = website_domain(website)
        if dom:
            for rec in self.ugc:
                if rec.website and website_domain(rec.website) == dom:
                    best_name = max((max(_score(v, k), fuzz.token_set_ratio(v, k))
                                     for q in names if q for v in variants(q, self.place_words)
                                     for k in rec.keys), default=0)
                    if best_name >= 80:   # same official domain + similar name (word subset allowed)
                        s = max(cands.get(id(rec), (0,))[0], 95.0)
                        cands[id(rec)] = (s, "website", website or "", rec.keys[0])
        by_id = {id(r): r for r in self.ugc}
        return self._pick("UGC", {by_id[i]: c for i, c in cands.items()}, state, UGC_MIN, method_prefix)

    # ---------------------------------------------------------------- AICTE
    def match_aicte(self, names: list[str], state: str | None = None, method_prefix: str = "",
                    place_hint: str = "") -> Match | None:
        cands: dict[int, tuple[float, str, str, str]] = {}
        for q in [n for n in names if n and n.strip()]:
            for v in variants(q, self.place_words):
                hits = process.extract(v, self._aicte_keys, scorer=fuzz.ratio,
                                       score_cutoff=AICTE_MIN - STATE_MISMATCH_PENALTY, limit=80)
                hits += process.extract(v, self._aicte_keys, scorer=fuzz.token_sort_ratio,
                                        score_cutoff=AICTE_MIN - STATE_MISMATCH_PENALTY, limit=80)
                for key, _, j in hits:
                    i = self._aicte_key_row[j]
                    s = _score(v, key)
                    if s > cands.get(i, (0,))[0]:
                        cands[i] = (s, "exact" if s == 100 else "fuzzy", q, key)
        pool = {self.aicte[i]: c for i, c in cands.items()}
        hint = norm(place_hint)
        if hint:   # city/district written in the input ("Government Polytechnic, Gadwal") → prefer that row
            for r, (s, m, q, k) in list(pool.items()):
                if any(w in hint.split() for w in norm(f"{r.district} {r.city}").split() if len(w) >= 4):
                    pool[r] = (s + 1.5, m, q, k)
        return self._pick("AICTE", pool, state, AICTE_MIN, method_prefix)

    # ---------------------------------------------------------------- common
    @staticmethod
    def _pick(body: str, pool: dict, state: str | None, minimum: float, prefix: str) -> Match | None:
        state = canonical_state(state)
        scored = []
        for rec, (s, method, q, key) in pool.items():
            sc = same_state(state, rec.state) if state else None
            adj = s
            if sc is True:
                adj += 2
            elif sc is False and s < 100:
                adj -= STATE_MISMATCH_PENALTY
            if adj >= minimum:
                scored.append((adj, s, rec, method, q, key, sc))
        if not scored:
            return None
        # same-state records first, then score; exact-name records in other states stay as fallbacks
        scored.sort(key=lambda x: (x[6] is not False, x[0]), reverse=True)
        adj, s, rec, method, q, key, sc = scored[0]
        alts = [x[2] for x in scored[1:] if x[0] >= adj - 5 and x[6] is not False and
                (x[2].name != rec.name or getattr(x[2], "state", "") != getattr(rec, "state", ""))]
        return Match(body=body, record=rec, score=round(min(s, 100.0), 1), method=prefix + method, query_name=q,
                     matched_key=key, state_check=sc, alternatives=alts[:8])

    # ---------------------------------------------------------------- not-found diagnostics
    def nearest(self, name: str, k: int = 3) -> dict[str, list[dict]]:
        """Closest list entries (below the acceptance threshold) — shown in the not-found evidence."""
        vs = variants(name, self.place_words) or [norm(name)]
        ugc = sorted(((max(_score(v, key) for v in vs for key in r.keys), r) for r in self.ugc),
                     key=lambda x: x[0], reverse=True)[:k]
        aic = {}
        for v in vs:
            for _, s, i in process.extract(v, self._aicte_norms, scorer=fuzz.ratio, limit=k):
                if s > aic.get(i, 0):
                    aic[i] = s
        aicte = sorted(aic.items(), key=lambda x: x[1], reverse=True)[:k]
        return {"UGC": [{"name": r.name, "state": r.state, "score": round(s, 1)} for s, r in ugc],
                "AICTE": [{"name": self.aicte[i].name, "state": self.aicte[i].state, "score": round(s, 1)}
                          for i, s in aicte]}
