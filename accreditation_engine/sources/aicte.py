"""AICTE approved-institution list — the official "Groupwise List of Institutions" PDF for the approval session
(2025-26 by default; set ARA_AICTE_LIST_URL / ARA_AICTE_SESSION for a new session).

The PDF is a ruled table (Sr.No | AICTE Permanent Id | Institute Name | Region | State | District | City | Group).
Rows are indexed from the table's own cell boxes (PyMuPDF table finder), so multi-line names and centred columns
are read correctly. The index is built once per PDF download (~2 min) and cached as JSON.
"""
from __future__ import annotations

import bisect
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass

import pymupdf

from ..settings import Settings
from ..states import canonical_state
from ..text import norm
from .http import atomic_write, fetch, is_fresh

log = logging.getLogger("accreditation_engine.sources")

INDEX_VERSION = 2
COLUMNS = ["sr", "aicte_id", "name", "region", "state", "district", "city", "group"]
# column x-ranges of the 2025-26 PDF — used only if the table finder fails on a page
FALLBACK_X = [(17, 46), (46, 111), (111, 266), (266, 317), (317, 381), (381, 449), (449, 522), (522, 575)]


@dataclass(eq=False)
class AicteRow:
    sr: str
    aicte_id: str
    name: str
    region: str
    state: str
    district: str
    city: str
    group: str
    page: int
    bbox: list[float]
    norm: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("norm", None)
        d.pop("bbox", None)
        return d


def _cells_from_words(words, row_rects, col_ranges_per_row) -> list[dict]:
    """Assign each word to (row, column) by its centre point."""
    tops = [r[1] for r in row_rects]
    cells = [{c: [] for c in COLUMNS} for _ in row_rects]
    for w in words:
        xc, yc = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        i = bisect.bisect_right(tops, yc) - 1
        if i < 0 or yc > row_rects[i][3]:
            continue
        for col, (x0, x1) in zip(COLUMNS, col_ranges_per_row[i]):
            if x0 <= xc < x1:
                cells[i][col].append((round(w[1]), w[0], w[4]))
                break
    out = []
    for c in cells:
        out.append({k: " ".join(t for _, _, t in sorted(v)) for k, v in c.items()})
    return out


def parse_page(page, pno: int) -> list[AicteRow]:
    words = page.get_text("words")
    rows_rects, col_ranges = [], []
    try:
        tabs = page.find_tables().tables
    except Exception:
        tabs = []
    for tb in tabs:
        for r in tb.rows:
            if len(r.cells) != len(COLUMNS) or any(c is None for c in r.cells):
                continue
            rows_rects.append(tuple(r.bbox))
            col_ranges.append([(c[0], c[2]) for c in r.cells])
    if not rows_rects:   # fallback: rows anchored on the Sr.No cells
        anchors = sorted(((w[1] + w[3]) / 2) for w in words if w[0] < 46 and w[4].isdigit())
        for k, y in enumerate(anchors):
            top = (anchors[k - 1] + y) / 2 if k else y - 8
            bot = (y + anchors[k + 1]) / 2 if k + 1 < len(anchors) else y + 8
            rows_rects.append((17, top, 575, bot))
            col_ranges.append(FALLBACK_X)
    order = sorted(range(len(rows_rects)), key=lambda i: rows_rects[i][1])
    rows_rects = [rows_rects[i] for i in order]
    col_ranges = [col_ranges[i] for i in order]
    out = []
    for rect, cells in zip(rows_rects, _cells_from_words(words, rows_rects, col_ranges)):
        if not cells["sr"].isdigit() or not cells["name"]:
            continue
        name = " ".join(cells["name"].replace(" ,", ",").split())
        out.append(AicteRow(sr=cells["sr"], aicte_id=cells["aicte_id"].replace(" ", ""), name=name,
                            region=cells["region"], state=canonical_state(cells["state"]) or cells["state"],
                            district=cells["district"], city=cells["city"], group=cells["group"].replace(" ", ""),
                            page=pno + 1, bbox=[round(v, 2) for v in rect], norm=norm(name)))
    return out


class AicteSource:
    def __init__(self, settings: Settings):
        self.s = settings
        self._lock = threading.Lock()
        self._rows: list[AicteRow] | None = None
        self.page_count = 0
        self.errors: list[str] = []
        self.loaded_at: float | None = None

    @property
    def pdf_path(self):
        return self.s.cache_dir / f"aicte_{self.s.aicte_session}.pdf"

    @property
    def index_path(self):
        return self.s.cache_dir / f"aicte_{self.s.aicte_session}_index_v{INDEX_VERSION}.json"

    def pdf(self, refresh: bool = False):
        p = self.pdf_path
        if refresh or not is_fresh(p, self.s.aicte_max_age_days) or p.stat().st_size < 100_000:
            try:
                data = fetch(self.s.aicte_list_url, self.s.user_agent, 180)
                if not data.startswith(b"%PDF"):
                    raise RuntimeError("AICTE list URL did not return a PDF")
                atomic_write(p, data)
            except Exception as e:
                self.errors.append(f"AICTE list download failed: {e}")
                log.warning("AICTE list download failed: %s", e)
                if not p.exists():
                    raise RuntimeError(f"AICTE list unavailable (no cache and download failed): {e}") from e
        return p

    def rows(self, refresh: bool = False) -> list[AicteRow]:
        with self._lock:
            if self._rows is not None and not refresh:
                return self._rows
            pdf = self.pdf(refresh)
            idx = self.index_path
            doc = pymupdf.open(str(pdf))
            self.page_count = doc.page_count
            if idx.exists() and idx.stat().st_mtime >= pdf.stat().st_mtime:
                rows = [AicteRow(**r) for r in json.loads(idx.read_text(encoding="utf-8"))]
            else:
                t0 = time.time()
                log.info("indexing AICTE list (%d pages) — one-time, about 2 minutes", doc.page_count)
                rows = []
                for pno, page in enumerate(doc):
                    rows.extend(parse_page(page, pno))
                atomic_write(idx, json.dumps([asdict(r) for r in rows]).encode())
                log.info("AICTE index: %d rows in %.0f s", len(rows), time.time() - t0)
            self._rows, self.loaded_at = rows, time.time()
            return rows

    def status(self) -> dict:
        p = self.pdf_path
        return {"rows": len(self._rows or []), "pages": self.page_count, "session": self.s.aicte_session,
                "url": self.s.aicte_list_url, "cached": p.exists(),
                "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime)) if p.exists()
                else None, "errors": self.errors[-3:]}
