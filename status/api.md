# API contract — v1

Base URL (local): `http://127.0.0.1:8100`. OpenAPI/Swagger: `/docs`, schema: `/openapi.json`.

Postman: `postman/Accreditation_Research_Agent.postman_collection.json` (v2.1, 15 requests: research examples incl.
errors, reports, PDF download, sources, health; each research request saves `requestId` for the report requests) +
`postman/Accreditation_Research_Agent.local.postman_environment.json` (`baseUrl`, `apiKey`, `requestId`).
`postman/openapi.json` = exported OpenAPI 3 schema (Postman → Import accepts it too).

## Authentication

Off by default (local use). Set `ARA_API_KEYS=key1,key2` to require header `X-API-Key: <key>` on every `/v1`
endpoint. For links that cannot send headers (e.g. opening the proof PDF in a browser) `?api_key=<key>` is accepted.
`/health` and `/` stay open.

## POST /v1/accreditation/research

Request body (JSON). Unknown fields are rejected (422).

| Field | Type | Required | Notes |
|---|---|---|---|
| `university_name` | string 2–300 | **yes** | awarding university; abbreviations like VTU / IGNOU accepted |
| `institute_name` | string ≤ 300 | no | affiliated college / institute |
| `degree` | string ≤ 200 | no | decides AICTE-first (technical) vs UGC-first |
| `state` | string ≤ 80 | no | Indian state/UT; aliases accepted (TN, Orissa…); disambiguates same names |
| `include_pdf_base64` | bool | no | also return the PDF inline (`accreditation_proof.base64`) |

Inputs that look like personal data (e-mail, phone, 7+ digit numbers, dates of birth) → 422.

Response 200 — `ResearchResponse`:

| Field | Meaning |
|---|---|
| `request_id` | `ara_<yyyymmdd>_<hhmmss>_<hex6>` |
| `accreditation_status` | `"Accredited"` or `"Non-Accredited"` |
| `accredited` | boolean of the above |
| `accreditation_body` | `"UGC"`, `"AICTE"` or `null` (Non-Accredited) |
| `accreditation_body_name` | full name of the body or `null` |
| `accreditation_url` | official list URL used (UGC category page / AICTE PDF) or `null` |
| `country` | `"India"` when accredited, `null` when Non-Accredited |
| `accreditation_proof` | `{filename, url, path, sha256, size_bytes, pages, base64?}` — always present |
| `accreditation_citations` | official sources cited for the result, `[{title, url}]`: UGC → the category list page; AICTE → the list at the row's page **and** the AICTE Public Notice 2025-26 (page 2, approval group) |
| `matched_institution` | record that decided the result: `{body, name, category, state, details, match_score, match_method, matched_on, state_check}` or `null`. For AICTE, `details.approval_group` = `{group, description, regions, region, region_states, notice_url}` |
| `other_listings` | the institution's listings in the other body / other role (e.g. university in UGC when AICTE decided) |
| `alternatives` | other records with the same/similar name (ambiguity) |
| `routing` | `{order, technical, reason}` |
| `sources_checked` | every official list checked: `{body, name, url, found, result}` (always the full list; the proof PDF shows only the `found` ones for Accredited results) |
| `name_resolution` | OpenAI step if it ran: names, website, country guess, cost, cached — or `null` |
| `warnings` | anything a reviewer should look at (ambiguity, state mismatch, source/capture problems) |
| `query`, `researched_at`, `duration_seconds`, `cost_usd`, `engine_version` | bookkeeping |

`match_method`: `exact`, `fuzzy`, `website`, each optionally prefixed `resolved_name:` when the name came from the
OpenAI step.

### Errors (always JSON `{"error", "detail"}`)

| Status | `error` | When |
|---|---|---|
| 401 | `unauthorized` | API keys configured and missing/wrong |
| 422 | `invalid_request` | missing `university_name`, unknown field, personal data in input |
| 500 | `internal_error` | unexpected failure (logged) |
| 503 | `not_ready` | official lists unavailable (no cache and download failed) |
| 504 | `timeout` | research exceeded 240 s |

## GET /v1/reports/{request_id}
Saved `ResearchResponse` (JSON) of an earlier request.

## GET /v1/reports/{request_id}/proof.pdf
The proof PDF (`application/pdf`, inline).

## GET /v1/sources · POST /v1/sources/refresh
Cache status of the UGC lists and AICTE list (counts, cached-at, errors) / force re-download and re-index.

## GET /health
`{"status": "ok", "ready": bool, "engine_version", "llm": bool}` — `ready` turns true once both lists are loaded.

## Examples

```bash
# university only
curl -s -X POST localhost:8100/v1/accreditation/research -H 'Content-Type: application/json' \
  -d '{"university_name":"IGNOU"}'

# technical programme at an affiliated college
curl -s -X POST localhost:8100/v1/accreditation/research -H 'Content-Type: application/json' \
  -d '{"university_name":"VTU","institute_name":"R.V. College of Engineering","degree":"B.E.","state":"Karnataka"}'

# download the proof
curl -s -o proof.pdf localhost:8100/v1/reports/<request_id>/proof.pdf
```

Python client:

```python
import httpx
r = httpx.post("http://127.0.0.1:8100/v1/accreditation/research",
               json={"university_name": "Anna University", "degree": "B.E."}, timeout=300).json()
pdf = httpx.get(r["accreditation_proof"]["url"]).content
```
