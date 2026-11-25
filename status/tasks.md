# Tasks

## Done (2026-11-25)
- [x] Folder + package `accreditation_engine`, own requirements / pyproject / `.env` / `run.sh`
- [x] UGC source: 4 JSON lists, cache, stale fallback, former names indexed
- [x] AICTE source: PDF download, table-cell index (13,694 rows), cache
- [x] Matcher: normalisation, abbreviations, official spellings, word order, city suffixes, state handling,
      alternatives, generic-word guard, AICTE name + city keys, nearest entries
- [x] Routing AICTE-first / UGC-first
- [x] OpenAI resolver (web search) with cache, cost and audit log; website-domain matching
- [x] Evidence: UGC live screenshots (found + not found), AICTE page render with highlight, AICTE text search
- [x] Proof PDF: summary, statement, sources table with hyperlinks, evidence
- [x] API: research, reports, proof download, sources status/refresh, health; optional API keys; JSON errors
- [x] Test UI (single file), CLI, 54 tests, docs (README + status/)

## Open
- [ ] Phase 2 validation on real names (plan.md) — measure precision, collect misses for the spelling table
- [ ] UGC "fake universities" list: check it and never return Accredited for a listed fake (needs the official
      source URL/format verified first)
- [ ] Async job mode (`POST` returns id, `GET` polls) if callers cannot hold a 30 s request
- [ ] Report retention / deletion endpoint
- [ ] Dockerfile + deployment notes (Chrome in the image)
- [ ] Alert when the UGC page DOM changes (selectors `#tbodyuni`, `#tbl_filter input`) — today it falls back to a
      text note and adds a warning
- [ ] Next AICTE session list (2026-27) when published: set `ARA_AICTE_LIST_URL` / `ARA_AICTE_SESSION`

## Done (2026-11-25, owner feedback round 1)
- [x] Listed in UGC **or** AICTE = Accredited; removed the "technical programme only in UGC" warning
- [x] AICTE evidence captured in Chrome's PDF viewer at the official URL (like UGC), sidebar hidden, 150 % zoom, 2×
- [x] AICTE Public Notice 2025-26 cited for AICTE results: group + region highlighted, group in summary / statement /
      sources / response (`approval_group`, `accreditation_citations`)
- [x] Tests for the annotation code (58 tests)

## Done (2026-11-25, owner feedback round 2)
- [x] Proof PDF: Accredited → only the sources where found; Non-Accredited → all sources + "not found in any" (60 tests)

## Done (2026-11-25, owner feedback round 3)
- [x] Removed "Closest entries" from Non-Accredited reports (61 tests)

## Answered questions
1. Technical programme found only in UGC → Accredited (UGC). (owner)
2. Evidence → both UGC and AICTE in the browser with the link. (owner)

## Open questions for the owner / ops
1. Where will the engine run (same server as closure, separate service)? Determines auth and URL settings.
2. Group-3 (new institutions) does not occur in the 2025-26 list; should a future Group-3 institution be treated
   differently?
