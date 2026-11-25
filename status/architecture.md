# Architecture

```
 caller (any project / curl / test UI)
        │  POST /v1/accreditation/research  {university_name, institute_name?, degree?, state?}
        ▼
 api.py (FastAPI) ── auth (X-API-Key, optional) ── validation (pydantic, extra fields rejected) ── timeout 240 s
        │
        ▼
 engine.py  AccreditationEngine.research()
   1 guard.check_public      reject e-mails / phones / ID numbers / dates (public institution info only)
   2 routing.decide          technical degree or institute → [AICTE, UGC], else [UGC, AICTE]
   3 matcher (local, ms)     UGC: 1,305 universities (4 lists)     AICTE: 13,694 rows (+ name+city keys)
        │ no direct match
        ▼
   4 resolver (OpenAI)       web search, public info → official name, former names, website   (cached 30 days)
        │ names / website      → matched against the official lists AGAIN (only a list hit counts)
        ▼
   5 decision                first body in route order with a hit → Accredited; none → Non-Accredited
   6 evidence (parallel)     all captured in headless Chrome at the official URL (2×, JPEG):
                             UGC: live page, search box filled, row highlighted
                             AICTE: list PDF downloaded live → row highlighted → Chrome PDF viewer at #page=N
                             AICTE body: + Public Notice 2025-26 p.2, approval group + region highlighted (citation)
                             not found: 4 UGC searches "No matching records found" + AICTE PDF + text-search count
   7 report → Chrome PDF     summary · statement · sources table (links) · evidence
        │
        ▼
 data/reports/<request_id>/{Accreditation - <name>.pdf, result.json, work/*.png}
```

## Sources and caches

| Source | Fetched from | Cache file | Refresh |
|---|---|---|---|
| UGC lists (4) | UGC JSON endpoint | `data/cache/ugc_<1..4>.json` | 7 days (`ARA_UGC_MAX_AGE_DAYS`) |
| AICTE list | official PDF | `data/cache/aicte_<session>.pdf` | 30 days (`ARA_AICTE_MAX_AGE_DAYS`) |
| AICTE index | built from the PDF | `data/cache/aicte_<session>_index_v2.json` | rebuilt when the PDF changes |
| AICTE Public Notice | official PDF (live per request) | `data/cache/aicte_notice_<session>.pdf` | fallback copy |

The AICTE PDFs shown as evidence are downloaded live for each request (the cached copy is the fallback).
| OpenAI answers | Responses API + web_search | `data/cache/resolver_cache.json` | 30 days |

A download failure falls back to the stale cache (reported in `warnings`); with no cache at all the API answers
503. Writes are atomic (temp file + rename). `POST /v1/sources/refresh` forces a re-download.

## Modules

| Module | Responsibility |
|---|---|
| `settings.py` | all configuration (env / `.env`, `ARA_*`), paths, UGC list tokens |
| `models.py` | request / response contract (pydantic) |
| `api.py` | HTTP layer: `create_app(settings, engine)`, auth, error mapping, report download |
| `engine.py` | orchestration (steps 1–7), result + PDF persistence |
| `routing.py` | AICTE-first vs UGC-first |
| `matcher.py` | scoring, thresholds, state disambiguation, alternatives, nearest entries |
| `text.py` | normalisation, variants, abbreviations, official spellings, generic words |
| `states.py` | 36 states / UTs + aliases (TN, Orissa, Pondicherry …) |
| `resolver.py` | OpenAI name resolution, cost, cache, audit |
| `guard.py` | input guard, audit log (`data/audit/outbound.jsonl`) |
| `sources/ugc.py`, `sources/aicte.py`, `sources/http.py` | download, cache, index |
| `evidence/browser.py` | one headless Chrome per engine, page semaphore (`ARA_MAX_BROWSER_PAGES`) |
| `evidence/capture.py` | UGC live screenshots, AICTE PDFs in Chrome's PDF viewer, row / group / region highlight annotations, group + region tables of the Public Notice, PDF text search |
| `evidence/report.py` | proof HTML template |
| `ui/index.html` | test console (no build step) |

## Concurrency

FastAPI async; matching and PDF rendering run in worker threads; screenshots share one Chrome with at most
`ARA_MAX_BROWSER_PAGES` (4) pages at a time. Source loading is guarded by locks, so parallel first requests download
once. 7 parallel requests took 22 s wall clock (research.md).

## Reuse in other projects

- HTTP: run the service and call `POST /v1/accreditation/research`.
- Python: `pip install -e accreditation_research_agent` (pyproject) → `from accreditation_engine import AccreditationEngine`.
- Embedded FastAPI: `app.mount("/accreditation", create_app())`.
No code change is needed for a new host; everything host-specific is configuration.
