# Accreditation Research Agent

An API engine that checks whether an Indian **university / institute is accredited by UGC or AICTE** and returns
the answer together with a **proof PDF** — screenshots of the official sources, taken in Google Chrome at the
official URLs, with the matching entry highlighted and every source cited as a clickable link.

| You send | You get back |
|---|---|
| `university_name` (required) | `accreditation_status` — `Accredited` / `Non-Accredited` |
| `institute_name` (optional) | `accreditation_proof` — PDF (download URL, SHA-256, page count) |
| `degree` (optional) | `accreditation_body` — `UGC` / `AICTE` |
| `state` (optional, Indian state/UT) | `accreditation_url` — official list used |
| | `country` — `India` |

The optional fields are never required: the engine works on the university name alone. They help it decide which
body to check first (AICTE regulates technical/professional programmes such as B.E., B.Tech, MBA, MCA, B.Pharm,
B.Arch) and tell apart universities that share a name in different states.

---

## Requirements

| | |
|---|---|
| Python | 3.11 or newer (tested on 3.14) |
| Browser | **Google Chrome** installed (used headless for screenshots and the PDF). Without Chrome, run `.venv/bin/playwright install chromium` and set `ARA_BROWSER_CHANNEL=` (empty) |
| OpenAI API key | used only to look up the official name of an institution that is not found directly. Without a key the engine still works with direct matches |
| Internet | access to `www.ugc.gov.in`, `aicte.gov.in` / `www.aicte.gov.in`, `api.openai.com` |
| Disk | ~20 MB for the cached official lists, plus ~0.5–2.5 MB per proof PDF |

Python packages (installed automatically, pinned in `requirements.txt`): FastAPI, Uvicorn, Pydantic, httpx,
PyMuPDF, RapidFuzz, Playwright, OpenAI.

---

## Install and run

### macOS / Linux

```bash
git clone https://github.com/yash09chawla/accreditation_research_agent.git
cd accreditation_research_agent
cp .env.example .env              # then edit .env and set OPENAI_API_KEY=...
./run.sh                          # creates .venv, installs requirements, starts the server
```

### Windows (PowerShell)

```powershell
git clone https://github.com/yash09chawla/accreditation_research_agent.git
cd accreditation_research_agent
copy .env.example .env            # then edit .env and set OPENAI_API_KEY=...
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn accreditation_engine.api:app --host 127.0.0.1 --port 8100
```

The server runs on **http://127.0.0.1:8100**:

| URL | What |
|---|---|
| http://127.0.0.1:8100/ | test page — type a university name and see the result and the proof PDF |
| http://127.0.0.1:8100/docs | interactive API documentation (Swagger) |
| http://127.0.0.1:8100/health | `"ready": true` once the official lists are loaded |

**First start:** the engine downloads the official UGC lists and the AICTE list and indexes the AICTE PDF. This takes
about **2 minutes, once** (the data is cached in `data/` and refreshed automatically). To do it before starting the
server: `.venv/bin/python -m accreditation_engine warm`.

Other port / host: `PORT=9000 HOST=0.0.0.0 ./run.sh`.

---

## Use the API

### Request

```bash
curl -s -X POST http://127.0.0.1:8100/v1/accreditation/research \
  -H 'Content-Type: application/json' \
  -d '{"university_name": "Anna University", "degree": "B.E. Civil Engineering", "state": "Tamil Nadu"}'
```

| Field | Required | Example |
|---|---|---|
| `university_name` | **yes** | `"Anna University"`, `"VTU"`, `"IGNOU"`, `"University of Mumbai"` |
| `institute_name` | no | `"R.V. College of Engineering"` |
| `degree` | no | `"B.E. Computer Science"`, `"MBA"`, `"B.Sc"` |
| `state` | no | `"Tamil Nadu"` (aliases like `TN`, `Orissa` work) |
| `include_pdf_base64` | no | `true` → the PDF is also returned inside the JSON |

### Response (shortened)

```json
{
  "request_id": "ara_20261125_120505_c7850b",
  "accreditation_status": "Accredited",
  "accredited": true,
  "accreditation_body": "AICTE",
  "accreditation_body_name": "All India Council for Technical Education",
  "accreditation_url": "https://aicte.gov.in/sites/default/files/approval/2025-26/Groupwise-List%20of%20Institutions_compressed.pdf",
  "country": "India",
  "accreditation_proof": {
    "filename": "Accreditation - Anna University.pdf",
    "url": "http://127.0.0.1:8100/v1/reports/ara_20261125_120505_c7850b/proof.pdf",
    "pages": 4,
    "sha256": "…"
  },
  "accreditation_citations": [
    {"title": "AICTE — Approved institutions 2025-26", "url": "…Groupwise-List%20of%20Institutions_compressed.pdf#page=115"},
    {"title": "AICTE — Public Notice 2025-26 (approval group Group-2)", "url": "…Public%20Notice%202025-26.pdf#page=2"}
  ],
  "matched_institution": {"body": "AICTE", "name": "ANNA UNIVERSITY", "state": "Tamil Nadu", "match_method": "exact"},
  "other_listings": [{"body": "UGC", "name": "Anna University", "category": "State University"}],
  "warnings": []
}
```

For **Non-Accredited** results `accreditation_body`, `accreditation_url` and `country` are `null`; the proof PDF
shows every official source searched and that none of them lists the institution.

### Other endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/reports/{request_id}` | saved result of an earlier request |
| GET | `/v1/reports/{request_id}/proof.pdf` | download the proof PDF |
| GET | `/v1/sources` | status of the cached official lists |
| POST | `/v1/sources/refresh` | re-download the official lists |
| GET | `/health` | server status |

Errors are JSON `{"error": "...", "detail": "..."}`: `401` wrong/missing API key, `422` invalid input (missing
`university_name`, unknown field, personal data such as an e-mail or ID number), `503` official lists unavailable,
`504` timeout. A research request normally takes **10–30 seconds**.

Complete contract: [status/api.md](status/api.md).

### Postman

Import `postman/Accreditation_Research_Agent.postman_collection.json` and
`postman/Accreditation_Research_Agent.local.postman_environment.json` (15 ready-made requests with example
responses). The OpenAPI schema is in `postman/openapi.json` and live at `/openapi.json`.

---

## Use it from Python (no HTTP)

```python
from accreditation_engine import AccreditationEngine

engine = AccreditationEngine()          # reads settings from the environment / .env
result = engine.research_sync({"university_name": "IGNOU"})

print(result.accreditation_status)      # Accredited
print(result.accreditation_body)        # UGC
print(result.accreditation_proof.path)  # local path of the proof PDF
```

In async code: `result = await engine.research({...})` and `await engine.close()` on shutdown.
To add the API to another FastAPI app: `from accreditation_engine.api import create_app` → `app.mount("/accreditation", create_app())`.
To install as a package in another project: `pip install -e /path/to/accreditation_research_agent`.

Command line:

```bash
.venv/bin/python -m accreditation_engine research "Nagpur University" --degree "B.Sc"
.venv/bin/python -m accreditation_engine serve --port 8100
```

---

## Configuration (`.env`)

Only `OPENAI_API_KEY` is needed; everything else has a default. See [.env.example](.env.example).

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI key for name resolution |
| `ARA_DISABLE_LLM` | — | `1` = never call OpenAI (direct matches only) |
| `ARA_OPENAI_MODEL` | `gpt-5.4-mini` | model used for name resolution |
| `ARA_API_KEYS` | (none) | comma-separated keys; when set every `/v1` call needs header `X-API-Key` |
| `ARA_CORS_ORIGINS` | (none) | browser origins allowed to call the API |
| `ARA_PUBLIC_BASE_URL` | request host | e.g. `https://ara.example.com` → absolute proof URLs behind a proxy |
| `ARA_DATA_DIR` | `./data` | cache, proof PDFs, results, audit log |
| `ARA_AICTE_LIST_URL` / `ARA_AICTE_SESSION` | 2025-26 list | switch to a new AICTE session |
| `ARA_AICTE_NOTICE_URL` | Public Notice 2025-26 | AICTE notice cited for the approval group |
| `ARA_BROWSER_CHANNEL` | `chrome` | empty = Playwright's bundled Chromium |
| `ARA_MAX_BROWSER_PAGES` | `4` | parallel browser pages |

---

## How it works

1. **Route** — technical/professional degree or institute → AICTE first, otherwise UGC first. Both are always checked.
2. **Match** the name against the official lists, cached locally: UGC university lists (Central, State, State
   Private, Deemed — 1,305 universities) and the AICTE list of approved institutions 2025-26 (13,694 rows). Handles
   abbreviations (VTU, IGNOU, AKTU…), word order, city suffixes, former names and same names in different states.
3. **Not found directly** → OpenAI web search (public institution information only) suggests the official / former
   names and website, which are matched against the official lists again. OpenAI never decides accreditation; only
   a record in an official list does.
4. **Evidence** — captured in headless Chrome at the official URLs: the live UGC page with the row highlighted; the
   AICTE list PDF (downloaded live) in Chrome's PDF viewer with the row highlighted; for AICTE results also the
   AICTE Public Notice 2025-26 with the institution's approval group and region highlighted. When nothing is found:
   every UGC list showing "No matching records found" and the AICTE list with the text-search result.
5. **Proof PDF** — summary, accreditation source(s) with links, evidence screenshots.

Every OpenAI request is logged in `data/audit/outbound.jsonl`. Inputs that look like personal data are rejected.

Design notes and measurements: [status/](status/) (research, architecture, API, decisions, plan, tasks, changes).

---

## Project layout

```
accreditation_research_agent/
├── accreditation_engine/     the engine (Python package)
│   ├── api.py                HTTP API (FastAPI)
│   ├── engine.py             research flow
│   ├── models.py             request / response schema
│   ├── matcher.py            name matching against the official lists
│   ├── resolver.py           OpenAI name resolution
│   ├── routing.py            AICTE-first / UGC-first
│   ├── text.py, states.py    name normalisation, abbreviations, Indian states
│   ├── guard.py              input guard + audit log
│   ├── settings.py           configuration
│   ├── sources/              UGC lists, AICTE PDF index, downloads
│   └── evidence/             browser, screenshots, proof PDF
├── ui/index.html             test page
├── postman/                  Postman collection + environment, OpenAPI schema
├── status/                   project notes
├── requirements.txt, pyproject.toml, run.sh, .env.example
└── data/                     created at runtime (not in git)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `/health` shows `"ready": false` | first start is still downloading/indexing the official lists (~2 min) |
| browser / Chrome error | install Google Chrome, or `.venv/bin/playwright install chromium` and set `ARA_BROWSER_CHANNEL=` |
| `503 not_ready` | ugc.gov.in / aicte.gov.in unreachable and no cached copy yet — check the internet connection |
| `"llm": false` in `/health` | `OPENAI_API_KEY` missing in `.env` (direct matches still work) |
| a warning says a capture failed | the official site was slow; the report used a fallback and says so — retry for a live capture |
