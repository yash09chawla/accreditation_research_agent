# Changes

## 2026-11-25 — Postman
- Added `postman/`: collection (15 requests, real example responses, tests that save `requestId`), local
  environment, exported OpenAPI schema. All requests replayed against the local server (refresh skipped).

## 2026-11-25 — v1.1.2 (owner feedback round 3)
- Proof PDF: the "Closest entries in the official lists" table is removed from Non-Accredited reports (owner).
  The AICTE text-search note no longer refers to it. +1 test → 61.

## 2026-11-25 — v1.1.1 (owner feedback round 2)
- Proof PDF: for **Accredited** results the sources table ("Accreditation source(s)") lists only the sources where
  the institution was found; for **Non-Accredited** results it lists all sources consulted plus the statement that
  none of them lists the institution. API `sources_checked` unchanged (full list). +2 tests → 60.

## 2026-11-25 — v1.1.0 (owner feedback round 1)
- **UGC or AICTE = Accredited**: the warning for a technical programme found only in UGC is removed.
- **AICTE evidence in the browser**: the official list PDF is downloaded live, the row highlighted, and the page
  captured in Chrome's PDF viewer at the official URL (`#page=N&zoom=150,…&navpanes=0`) — same treatment as the UGC
  page. Not-found AICTE evidence is also a Chrome capture of the live PDF. All captures now 2× JPEG (sharper,
  smaller). Drawn PDF toolbar removed (the real viewer toolbar is in the capture); local render kept as fallback.
- **AICTE Public Notice 2025-26** cited for every AICTE result: page 2 captured in Chrome with the approval group
  and the region row highlighted; group shown in the summary, statement and sources table; new response fields
  `accreditation_citations` and `matched_institution.details.approval_group`; setting `ARA_AICTE_NOTICE_URL`.
- Tests: +4 (annotation of list rows, re-published list, notice group/region, group/region tables) → 58.

## 2026-11-25 — v1.0.0 (first version)

Built from scratch as an independent engine; logic carried over (rewritten) from the closure project's
`app/research/accreditation.py`, `app/research/sources.py`, `app/evidence/*`.

New compared with the closure project's accreditation step:
- **API engine** with a stable contract (`/v1/accreditation/research`), report storage and download, source status /
  refresh, health, optional API keys, CORS, JSON errors, 240 s timeout; library + CLI use.
- **AICTE index rebuilt** from the PDF's table cells — fixes wrong rows (region text in names, split states, header
  text in ids). 36 clean states, 13,694 rows.
- **Matching:** former names from UGC brackets, place-word stripping, official-spelling table, two-letter
  abbreviations removed, distinctive-word guard against generic matches, name + city/district keys for AICTE,
  state disambiguation with alternatives and warnings, website-domain matching from the OpenAI answer.
- **Routing** by degree / institute (AICTE-first for technical programmes) with a reason in the response.
- **Resolver:** university + institute in one OpenAI call, answer cached 30 days, every prompt audited.
- **Evidence:** live UGC screenshots highlight the row by name **and state** (e.g. one of 9 Amity rows); not-found
  proof now also covers AICTE (PDF text-search count, rows searched, closest entries); two not-found UGC captures per
  page.
- **Proof PDF:** result badge, statement, sources table, closest entries, evidence on its own pages, page numbers,
  clickable links on URLs and screenshots.
- **Response:** body / URL / country are `null` for Non-Accredited (proof only).
- Test UI `ui/index.html`, 54 tests, README and `status/` notes.

Bugs found and fixed during the build: generic-word false matches (decision 6); ambiguity warning crashed on a
string concatenation (caught in the parallel end-to-end run); unexpected errors returned plain-text 500 (now JSON).
