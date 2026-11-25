# Research — official sources and measured results

All facts verified on 2026-11-25 from this machine.

## UGC — university lists

- Public pages: `https://www.ugc.gov.in/universitydetails/university?type=<token>` — one page per category.
  Tokens: Central `ddmCMsxJZgXH2S/m0uMOKQ==`, State `LZ1FUMk6U2JWGNLvhWfVSA==`, State Private
  `0wBmFB1Rb4JGVzq9UP/iOg==`, Deemed `UCL6fMspL2LJS89kv++N3A==`.
- Data behind the pages: `https://www.ugc.gov.in/universitydetails/Getuniversity_details?unitypeID=<1..4>` (JSON,
  key `List`; needs header `X-Requested-With: XMLHttpRequest`). Responds in ~0.7 s.
- Record counts: Central 57, State 523, State Private 561, Deemed 164 → **1,305**.
- Useful fields: `uni_name`, `address`, `Zip`, `state` (often with a trailing space), `status`, `url`.
- `status` values seen: `2(f)`, `2(f) & 12B`, `2(f) & 12B Category-I/II`, `2(f) & Category-I/II`, `Section-III`,
  `Section-III & 12B`, `Section-III & Category-I` …
- Page DOM (used for screenshots): table body `#tbodyuni`, search box `#tbl_filter input` (DataTables), info line
  `#tbl_info`. Columns: Sr.No, Type, Name of the University, Address, Zip, state, Status, URL. Page loads in ~3 s.
  A search with no hit shows "No matching records found". DataTables search is word-based ("Anna University" also
  shows Annamalai University, Tamil Nadu Open University…), so the engine highlights the exact row.
- Quirks that affect matching:
  - **Same name, several states**: 9 × "Amity University" (Karnataka, Punjab, Rajasthan, Madhya Pradesh,
    Maharashtra, Chhattisgarh, West Bengal, Jharkhand, Bihar), 2 × "Jawaharlal Nehru Technological University"
    (Telangana, Andhra Pradesh), 2 × "SRM University".
  - **Former names in brackets**: "Hemchand Yadav Vishwavidyalaya(Earlier known as Durg Vishwavidyalaya)",
    "… (Formerly Sikkim State University)", "( previously Rashtriya Sanskrit Vidyapeeth)".
  - **City in the name**: "Maharashtra National Law University, Mumbai", "Atharva University, Mumbai".
  - **Misspellings in the official list**: "Vesveswaraiah Technological University" (= VTU),
    "Jawaharlal Nehru Technological University (Kainada)" (= JNTU Kakinada).
  - Names UGC uses that differ from common usage: "Mumbai University", "Madras University", "University of Delhi".
  - 46 names contain a comma.

## AICTE — approved institutions 2025-26

- List: `https://aicte.gov.in/sites/default/files/approval/2025-26/Groupwise-List%20of%20Institutions_compressed.pdf`
  (~2 MB, **287 pages**, text PDF, title "Groupwise Bifurcation of Institutions for Approval Process 2025-26").
- It is a ruled table: Sr.No | AICTE Permanent Id | Institute Name | Region | State | District | City | User Group.
  **13,694 rows**. 36 distinct states/UTs after normalisation.
- Text in the Region/State/District/City columns is **centred**, and long names wrap to two lines. The closure
  project's parser used fixed x-boundaries, which produced wrong rows: region text inside names
  ("GURU NANAK INSTITUTE OF TECHNOLOGY South-Central"), split states ("Pradesh", "Karnataka BANGALORE"), header text
  in the first row's id. This engine reads cells from PyMuPDF's table finder (cell boxes are identical on every page:
  x = 17/46/111/266/317/381/449/522/575), giving clean rows. Indexing takes ~2 min once per download
  (~0.4 s per page).
- The list keeps the town in its own column (e.g. name "GOVERNMENT POLYTECHNIC", city "BELLAMPALLY"; 9 rows named
  exactly "GOVERNMENT POLYTECHNIC" in the sample checked), and has its own typos ("GOVERNMENT PLYTECHNIC, GADWAL",
  "GOVERNMENT POLYTCHNIC"). The matcher therefore also indexes name + city and name + district.
- Universities that run AICTE programmes appear in the list too (e.g. ANNA UNIVERSITY, Sr.No 5427, page 115;
  VISVESVARAYA TECHNOLOGICAL UNIVERSITY; UNIVERSITY OF DELHI).

## AICTE Public Notice 2025-26

- `https://www.aicte.gov.in/sites/default/files/approval/2025-26/Public%20Notice%202025-26.pdf` — 2 pages. Page 2
  is a **scanned image with an OCR text layer** (imperfect: "Group - 2:" and region labels are searchable,
  "South West (SWR)" only as "South West").
- Page 2, table 1 "Submission Deadlines": Group-1 / Group-2 = existing institutions / universities running other
  than BBA/BCA/BMS (Group-1: Central, Eastern, Northern, North West regions; Group-2: Western, Southern, South West,
  South Central); Group-3 = new technical institutions / universities incl. BBA/BCA/BMS (all regions); Group-4 =
  existing institutions / universities with standalone BBA/BCA/BMS (all regions).
- Page 2, table 2 regions → states: CR Chhattisgarh, Gujarat, MP · ER A&N, Arunachal, Assam, Jharkhand, Manipur,
  Meghalaya, Mizoram, Nagaland, Orissa, Sikkim, Tripura, WB · NR Uttarakhand, UP, Bihar · NWR Chandigarh, Delhi,
  Haryana, HP, J&K, Ladakh, Punjab, Rajasthan · WR Dadra & Nagar Haveli, Daman & Diu, Goa, Maharashtra · SR Tamil
  Nadu, Puducherry · SWR Karnataka, Kerala, Lakshadweep · SCR Andhra Pradesh, Telangana.
- Groups in the 2025-26 list: Group-1 4,171 rows, Group-2 4,702, Group-4 4,821 (no Group-3). Regions in the list:
  Central, Eastern, Northern, North-West, Western, Southern, South-West, South-Central.

## Chrome PDF viewer (headless)

- Headless Chrome (Playwright, channel "chrome") renders PDFs in its own viewer, including the toolbar
  (title, page x / N, zoom). URL fragments honoured: `#page=N`, `zoom=<pct>,<left>,<top>` (top in PDF points from
  the page top), `view=Fit`, `navpanes=0` (hides the thumbnail sidebar). Verified 2026-11-25.

## Name matching — checks on real names (2026-11-25)

| Input | Result |
|---|---|
| Anna University, Chennai / Anna University Chennai | UGC Anna University (exact), AICTE ANNA UNIVERSITY |
| IGNOU / AKTU / VTU / JNTU Kakinada | the right UGC record (abbreviation / official spelling table) |
| University of Mumbai / Delhi University | Mumbai University / University of Delhi (word order) |
| Durg Vishwavidyalaya | Hemchand Yadav Vishwavidyalaya (former name) |
| Amity University (+ state Rajasthan) | Rajasthan record; without state: Karnataka + 8 alternatives + warning |
| Punjab University | Punjabi University with Panjab University as alternative + warning |
| College of Engineering Pune | AICTE "COLLEGE OF ENGINEERING", district PUNE (not P.E.S. College, Aurangabad) |
| Government Polytechnic, Bellampally | AICTE row "GOVERNMENT POLYTCHNIC", city BELLAMPALLY |
| Nagpur University | OpenAI → Rashtrasant Tukadoji Maharaj Nagpur University → UGC exact |
| University of Pune | OpenAI website unipune.ac.in = UGC website → Savitribai Phule Pune University |
| Oxford Global University of Excellence, Sunrise Global Institute of Advanced Learning | Non-Accredited |

False matches found during development and fixed: "College of Engineering Pune" → "P.E.S. College of Engineering"
(generic words carried the score), "Anna University Chennai" → generic variant. Fix: decision 6.

## Measured performance (MacBook, 2026-11-25)

| Case | Engine time | OpenAI cost | Proof pages |
|---|---|---|---|
| Direct match, UGC only (IGNOU) | 14–17 s | $0 | 2 |
| Direct match, AICTE + notice + UGC (Anna University, B.E.) — round 1 | 21 s | $0 | 4 (≈2 MB) |
| AICTE institute + university + notice + UGC (VTU / RVCE) — round 1 | 23 s | $0 | 5 (≈2.5 MB) |
| OpenAI name resolution (Nagpur University) | 24 s | $0.057 | 2 |
| Not found anywhere (OpenAI tried) | 22–28 s | $0.054 (first time), $0 cached | 4–6 |
| 7 requests in parallel | 22 s wall clock | — | — |

Most of the time is the live ugc.gov.in page load (~3 s per page) and PDF rendering; matching takes milliseconds.
OpenAI cost per resolution is mostly web-search calls (~$0.01 each); answers are cached 30 days.
