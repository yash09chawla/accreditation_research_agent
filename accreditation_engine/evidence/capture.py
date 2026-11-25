"""Screenshots of the official sources — all taken in headless Google Chrome at the official URL.

UGC   — the live ugc.gov.in list page: the name is typed into the site's own search box, the matching row(s) are
        highlighted in the page, and the browser viewport is captured. On a miss the capture shows the site's
        "No matching records found".
AICTE — the official PDF (list of approved institutions / Public Notice) is downloaded live from aicte.gov.in, the
        matched row (or the approval group and region) gets a highlight annotation, and Chrome's own PDF viewer
        displays it at the official URL (#page=N), which is then captured. This is the PDF counterpart of colouring
        the matched row on the UGC page.
Fallback (browser unavailable): the PDF page is rendered locally with PyMuPDF.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pymupdf

from ..sources.aicte import AicteRow
from .browser import BrowserPool

SCALE = 2                # captures at 2× (retina) so text stays sharp when the PDF is zoomed
JPEG_QUALITY = 85
PDF_ZOOM = 150           # Chrome PDF viewer zoom (%) — readable rows in the A4 report
HIGHLIGHT_FILL = (1.0, 0.93, 0.25)
HIGHLIGHT_STROKE = (0.85, 0.1, 0.1)

# ------------------------------------------------------------------ AICTE Public Notice 2025-26 (page 2)
# Group meaning and region → states, as printed in the notice's two tables (verified 2026-11-25).
AICTE_GROUPS = {
    "Group-1": ("Existing institutions / universities running other than BBA / BCA / BMS",
                "Central (CR), Eastern (ER), Northern (NR) and North West (NWR) regions"),
    "Group-2": ("Existing institutions / universities running other than BBA / BCA / BMS",
                "Western (WR), Southern (SR), South West (SWR) and South Central (SCR) regions"),
    "Group-3": ("New technical institutions / universities including BBA, BCA, BMS", "all eight regions"),
    "Group-4": ("Existing institutions / universities with standalone BBA / BCA / BMS courses", "all regions"),
}
AICTE_REGIONS = {  # region value in the list → (label searched in the notice, states covered, half row height pt)
    "Central": ("Central (CR)", "Chhattisgarh, Gujarat, Madhya Pradesh", 8),
    "Eastern": ("Eastern (ER)", "Andaman and Nicobar Islands, Arunachal Pradesh, Assam, Jharkhand, Manipur, "
                                "Meghalaya, Mizoram, Nagaland, Orissa, Sikkim, Tripura, West Bengal", 25),
    "Northern": ("Northern (NR)", "Uttarakhand, Uttar Pradesh, Bihar", 8),
    "North-West": ("North West (NWR)", "Chandigarh, Delhi, Haryana, Himachal Pradesh, Jammu and Kashmir, Ladakh, "
                                       "Punjab, Rajasthan", 15),
    "Western": ("Western (WR)", "Dadra and Nagar Haveli, Daman and Diu, Goa, Maharashtra", 8),
    "Southern": ("Southern (SR)", "Tamil Nadu, Puducherry", 8),
    "South-West": ("South West", "Karnataka, Kerala, Lakshadweep", 8),
    "South-Central": ("South Central (SCR)", "Andhra Pradesh, Telangana", 8),
}
REGION_DISPLAY = {"Central": "Central (CR)", "Eastern": "Eastern (ER)", "Northern": "Northern (NR)",
                  "North-West": "North West (NWR)", "Western": "Western (WR)", "Southern": "Southern (SR)",
                  "South-West": "South West (SWR)", "South-Central": "South Central (SCR)"}

_UGC_JS = """([targets]) => {
  const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const rows = [...document.querySelectorAll('#tbodyuni tr')];
  let n = 0;
  for (const r of rows) {
    const c = r.children;
    if (!c[2]) continue;
    const name = norm(c[2].innerText), state = norm(c[5] ? c[5].innerText : '');
    if (targets.some(t => norm(t[0]) === name && (!t[1] || norm(t[1]) === state))) {
      r.querySelectorAll('td').forEach(td => { td.style.background = '#fff176'; td.style.fontWeight = '600';
                                               td.style.outline = '1px solid #e0b000'; });
      n++;
    }
  }
  const f = document.querySelector('#tbl_filter');
  if (f) window.scrollTo(0, f.getBoundingClientRect().top + window.scrollY - 210);
  const info = document.querySelector('#tbl_info');
  return {highlighted: n, rows: rows.length, info: info ? info.innerText.trim() : '',
          empty: rows.length === 1 && /no matching records/i.test(rows[0].innerText)};
}"""


async def ugc_live(pool: BrowserPool, page_url: str, search_text: str, out_png: Path,
                   highlight: list[tuple[str, str]] | None = None, timeout_ms: int = 45000,
                   height: int = 900) -> dict:
    """Open the UGC list page, search, highlight target rows [(name, state)], screenshot. Returns page facts."""
    async with pool.page(1366, height, scale=SCALE) as page:
        await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_selector("#tbodyuni tr td", timeout=timeout_ms)
        await page.fill("#tbl_filter input", search_text)
        await page.wait_for_timeout(600)
        facts = await page.evaluate(_UGC_JS, [[list(t) for t in (highlight or [])]])
        await page.wait_for_timeout(200)
        await page.screenshot(path=str(out_png), type="jpeg", quality=JPEG_QUALITY)
        return facts


async def pdf_in_browser(pool: BrowserPool, url: str, pdf_bytes: bytes, page_no: int, out_png: Path,
                         top_pt: float | None = None, fit_page: bool = False, height: int = 900,
                         timeout_ms: int = 60000) -> str:
    """Show `pdf_bytes` (the official PDF, downloaded live, with highlight annotations) in Chrome's PDF viewer at the
    official `url` and capture the viewport. Returns the URL shown in the address bar."""
    base = url.split("#")[0]
    frag = (f"#page={page_no}" + ("&view=Fit" if fit_page else f"&zoom={PDF_ZOOM},0,{int(max(0, top_pt or 0))}")
            + "&navpanes=0")                       # navpanes=0 hides the thumbnail sidebar
    async with pool.page(1366, height, scale=SCALE) as page:
        async def serve(route):
            await route.fulfill(status=200, body=pdf_bytes, content_type="application/pdf")
        await page.route(lambda u: u.split("#")[0] == base, serve)
        await page.goto(base + frag, wait_until="load", timeout=timeout_ms)
        await page.wait_for_timeout(3500)          # the PDF viewer renders after 'load'
        await page.screenshot(path=str(out_png), type="jpeg", quality=JPEG_QUALITY)
        return page.url


# ------------------------------------------------------------------ PDF annotation
def _box(page, rect, opacity=0.5):
    a = page.add_rect_annot(rect)
    a.set_colors(stroke=HIGHLIGHT_STROKE, fill=HIGHLIGHT_FILL)
    a.set_border(width=1.3)
    a.set_opacity(opacity)
    a.update()


def annotate_list(pdf_bytes: bytes, rows: list[AicteRow]) -> tuple[bytes, dict[str, tuple[int, float]]]:
    """Highlight each row (located by its AICTE Permanent Id, so a re-published list still works).
    Returns (annotated bytes, {sr: (page_no, row_top_pt)})."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    where = {}
    for r in rows:
        pno, rect = r.page, pymupdf.Rect(*r.bbox)
        hits = doc[pno - 1].search_for(r.aicte_id) if r.aicte_id and pno <= doc.page_count else []
        if not any(abs(h.y0 - rect.y0) < 25 for h in hits):          # list changed → find the id anywhere
            for i, pg in enumerate(doc):
                found = pg.search_for(r.aicte_id) if r.aicte_id else []
                if found:
                    pno, h = i + 1, found[0]
                    rect = pymupdf.Rect(17, h.y0 - 4, 575, h.y1 + 4)
                    break
        page = doc[pno - 1]
        _box(page, pymupdf.Rect(rect.x0 + 1, rect.y0 + 0.5, rect.x1 - 1, rect.y1 - 0.5))
        where[r.sr] = (pno, rect.y0)
    return doc.tobytes(), where


def annotate_notice(pdf_bytes: bytes, group: str, region: str) -> tuple[bytes, dict]:
    """Highlight the institution's approval group and its region row on page 2 of the AICTE Public Notice."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    found = {"group": False, "region": False, "page": 2}
    if doc.page_count < 2:
        return pdf_bytes, found
    page = doc[1]
    gnum = "".join(ch for ch in group if ch.isdigit())
    labels = {}
    for n in "1234":
        hits = page.search_for(f"Group - {n}")
        if hits:
            labels[n] = hits[0]
    if gnum in labels:
        top = labels[gnum].y0 - 3
        nxt = [labels[n].y0 for n in labels if labels[n].y0 > labels[gnum].y0 + 5]
        bottom = (min(nxt) - 3) if nxt else labels[gnum].y0 + 75
        _box(page, pymupdf.Rect(124, top, 424, bottom), 0.38)
        found["group"] = True
    label, _, half = AICTE_REGIONS.get(region, ("", "", 8))
    if label:
        table_top = max((h.y1 for h in page.search_for("S.No")), default=400)
        hits = [h for h in page.search_for(label) if h.y0 > table_top]
        if hits:
            h = hits[0]
            yc = (h.y0 + h.y1) / 2
            _box(page, pymupdf.Rect(60, yc - half, 585, yc + half), 0.38)
            found["region"] = True
    return doc.tobytes(), found


# ------------------------------------------------------------------ local fallbacks / helpers
def render_pdf_page(pdf_bytes: bytes, page_no: int, out_png: Path, dpi: int = 135) -> None:
    """Fallback when the browser capture fails: render the (annotated) page locally."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    doc[page_no - 1].get_pixmap(dpi=dpi, annots=True).save(str(out_png))


def aicte_text_hits(pdf_path: Path, term: str) -> int:
    """Case-insensitive occurrences of `term` in the PDF's text (what Ctrl+F in a PDF viewer would count)."""
    t = " ".join(term.lower().split())
    if not t:
        return 0
    return sum(p.count(t) for p in _page_texts(str(pdf_path), Path(pdf_path).stat().st_mtime))


@lru_cache(maxsize=2)
def _page_texts(path: str, mtime: float) -> tuple[str, ...]:
    return tuple(" ".join(page.get_text().lower().split()) for page in pymupdf.open(path))
