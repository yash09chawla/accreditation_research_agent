# Decisions

1. **Independent engine in its own folder** (2026-11-25, owner). `accreditation_research_agent/` has its own
   package, requirements, `.env`, data and docs; nothing is imported from the closure project. Code was rewritten,
   not linked, from `app/research/accreditation.py`. *Why:* reusable in any future project without code changes.

2. **Accreditation is decided only by the official lists.** UGC university lists (4 categories) and the AICTE
   approved-institution list. OpenAI can only propose names/website to try; a result is "Accredited" only when a
   record exists in an official list. *Why:* a search result or model answer is not evidence.

3. **Both lists are always searched; the route only decides priority.** Technical/professional degree (B.E.,
   B.Tech, M.E., M.Tech, MBA/PGDM, MCA/BCA, pharmacy, architecture/planning, hotel management, applied arts,
   design) or a technical institute name → AICTE first; otherwise UGC first. *Why:* AICTE regulates those
   programmes; searching both is cheap (local) and the other listing is still reported.

4. **Body reported** = first body in the route order that lists the institution (institute row preferred over the
   university row within AICTE). **Listed by either UGC or AICTE = Accredited** (owner, 2026-11-25): a technical
   programme whose university is only in UGC is Accredited (UGC), with no warning.

5. **Matching thresholds:** score = max(ratio, token_sort_ratio) on normalised names; accept UGC ≥ 92,
   AICTE ≥ 93; exact normalised equality = 100. *Why:* conservative — wrong "Accredited" is worse than sending a
   name to the resolver.

6. **Fuzzy matches need the distinctive words to agree** (≥ 70 %, ratio or token-set, after removing generic words
   like UNIVERSITY / COLLEGE / ENGINEERING / GOVERNMENT …), and shortened variants must keep a distinctive word.
   *Why:* "College of Engineering Pune" scored 94 against "P.E.S. College of Engineering" on generic words alone.

7. **State handling:** given state + same state → +2; other state: exact names accepted with a warning, fuzzy names
   −10 (rejected). Same name in several states without a state → first record + `alternatives` + warning.
   *Why:* UGC has 9 "Amity University" records; a wrong state in the input should not hide an exact listing.

8. **Two-letter abbreviations (AU, MU, DU…) are not expanded.** Each stands for several universities; they go to
   the resolver with the context given.

9. **Official-spelling table** for known misspellings in the UGC list (Vesveswaraiah = VTU, "(Kainada)" = JNTU
   Kakinada). Small and explicit; extend when a new one is found.

10. **AICTE index from the PDF's table cells** (PyMuPDF table finder), not fixed x-positions; name + city and name +
    district also indexed. *Why:* see research.md — the fixed-column parser produced wrong rows.

11. **Evidence — both UGC and AICTE captured in the browser with the link** (owner, 2026-11-25).
    UGC = live ugc.gov.in page in headless Chrome, search box filled, row highlighted. AICTE = the official PDF
    downloaded live from aicte.gov.in, the matched row given a highlight annotation, then shown in Chrome's own PDF
    viewer at the official URL (`#page=N&zoom=150,…&navpanes=0`) and captured — the PDF counterpart of colouring the
    UGC row. Captures at 2× resolution (JPEG q85). Each capture sits under an address bar showing the URL of the
    captured page, and the URL is repeated above it as a hyperlink. If the browser capture fails, the page is rendered
    locally and a warning is added; if the live download fails, the cached copy is used and a warning gives its date.

12. **Not found = still a proof.** Screenshots of all four UGC list searches ("No matching records found"), the
    AICTE PDF with the text-search count and the number of rows/pages searched. The "closest entries below the
    threshold" table was removed on the owner's request (2026-11-25). Statement: "Non-Accredited with UGC and AICTE".

13. **Non-Accredited response:** `accreditation_body`, `accreditation_url`, `country` = `null`; only the proof is
    given (owner: "for non-Accredited we need Accreditation proof only"). The OpenAI country guess is kept in
    `name_resolution` only — it echoed the prompt's "in India" for a made-up name, so it is not reported as fact.

14. **Input guard:** inputs that look like personal data are rejected (422); every OpenAI prompt is logged in
    `data/audit/outbound.jsonl`. *Why:* the engine needs public institution info only, and the name goes to OpenAI.

15. **Same OpenAI key as the closure project**, copied into this folder's git-ignored `.env` (owner). Model
    `gpt-5.4-mini` with web search, configurable (`ARA_OPENAI_MODEL`).

16. **Synchronous API** (one call returns the full result in ~15–30 s) with a 240 s timeout; results and PDFs are
    stored per request and downloadable later. An async job API can be added if callers need it (tasks.md).

17. **AICTE Public Notice 2025-26 is cited whenever AICTE is the accreditation body** (owner, 2026-11-25).
    `https://www.aicte.gov.in/sites/default/files/approval/2025-26/Public%20Notice%202025-26.pdf` page 2 holds the
    approval-process groups and the region → states table. The institution's group (from its row in the list) and
    region are highlighted on that page, captured in Chrome like the list, named in the summary / statement / sources
    table, returned in `matched_institution.details.approval_group`, and listed in `accreditation_citations`.
    Group texts (from the notice): Group-1/2 = existing institutions/universities running other than BBA/BCA/BMS
    (Group-1: CR, ER, NR, NWR; Group-2: WR, SR, SWR, SCR); Group-3 = new technical institutions/universities incl.
    BBA/BCA/BMS; Group-4 = existing institutions/universities with standalone BBA/BCA/BMS. The notice URL is
    configurable (`ARA_AICTE_NOTICE_URL`) for the next session.

18. **Proof PDF sources table depends on the result** (owner, 2026-11-25). Accredited → table titled
    "Accreditation source(s)" lists only the official sources where the institution was found (e.g. UGC State list,
    AICTE list, AICTE Public Notice); lists where it was not found are left out. Non-Accredited → "Sources consulted"
    lists every official source checked, followed by "The institution was not found in any of the N official sources
    listed above." The API field `sources_checked` still lists every source checked, so callers keep the full audit
    trail.
