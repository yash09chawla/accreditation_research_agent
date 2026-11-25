# Status — Accreditation Research Agent

Project notes for the accreditation engine only (the closure project keeps its own notes in `../../status/`).
Facts here are verified on the date given; nothing is estimated unless marked as such.

| File | What it holds |
|---|---|
| [research.md](research.md) | the official sources (formats, counts, quirks) and measured results |
| [architecture.md](architecture.md) | components, flow, data layout |
| [api.md](api.md) | HTTP contract: endpoints, request, response, errors, auth |
| [decisions.md](decisions.md) | numbered decisions with the reason for each |
| [plan.md](plan.md) | phases and what comes next |
| [tasks.md](tasks.md) | done / open tasks and open questions |
| [changes.md](changes.md) | change log |

## Current state (2026-11-25)

- **v1.1.2 running locally** on http://127.0.0.1:8100 (`./run.sh`), test UI at `/`.
- Independent of the closure project: own package `accreditation_engine`, own `requirements.txt`, `.env`, `data/`.
  The same OpenAI key is used (copied into this folder's git-ignored `.env`).
- Both official sources download and index automatically (UGC 1,305 universities; AICTE 13,694 rows / 287 pages).
- 61 automated tests pass (no network). End-to-end runs verified for: UGC found, AICTE found (institute + university),
  same name in several states, OpenAI-resolved names (old names, website match), not found anywhere.
- Owner feedback round 1 applied (2026-11-25): UGC-or-AICTE = Accredited; AICTE evidence captured in Chrome's PDF
  viewer like UGC; AICTE Public Notice 2025-26 cited with the group highlighted.
- Owner feedback round 2 applied: Accredited reports list only the sources where the institution was found.
- Owner feedback round 3 applied: no "Closest entries" table in Non-Accredited reports.
- Passing-criteria engine: not started (next, per the owner).
