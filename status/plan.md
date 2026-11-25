# Plan

## Phase 1 — Accreditation engine v1 (done 2026-11-25)
Standalone API engine: UGC + AICTE lists, routing, matching, OpenAI name resolution, evidence screenshots, proof
PDF, test UI, tests, docs. See changes.md.

## Phase 2 — Validate on real cases (next)
- Run the engine on the closure project's real cases (`../Cases/Case1…6`) and on a list of 50–100 university /
  institute names from ops (including known non-accredited ones); record precision per body in research.md.
- Ops review of the proof PDF format (is the drawn browser frame acceptable? is the AICTE page render enough?).
- Decide the open questions in tasks.md (fake-universities list, async API, where to host).

## Phase 3 — Production hardening
- Deploy as a service (container image, `ARA_API_KEYS`, `ARA_PUBLIC_BASE_URL`, persistent `ARA_DATA_DIR`).
- Report retention / cleanup policy for `data/reports/`.
- Monitoring: source-download failures, UGC page DOM changes (screenshot selectors), OpenAI errors and cost.
- Yearly AICTE list switch (new session URL) — make it a checked config step.

## Phase 4 — Integrate
- Closure project calls this engine over HTTP instead of `app/research/accreditation.py`.

## Phase 5 — Passing Marks Criteria engine
Same pattern (separate folder, API, status notes), started after the accreditation engine is accepted.
