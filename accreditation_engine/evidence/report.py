"""Proof PDF — HTML template rendered to A4 by Chrome (links stay clickable in the PDF).

Layout: summary (result, body, official URL, country) → sources consulted (every official URL checked, with its
result) → evidence screenshots, each in a browser frame whose address bar shows the real URL of the page captured,
with the URL repeated above it as a hyperlink.
"""
from __future__ import annotations

import base64
import html as H
import re
from dataclasses import dataclass, field
from pathlib import Path


def e(s) -> str:
    return H.escape(str(s if s is not None else ""))


def data_url(path: Path) -> str:
    mime = "jpeg" if Path(path).suffix.lower() in (".jpg", ".jpeg") else "png"
    return f"data:image/{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


@dataclass
class EvidenceBlock:
    heading: str
    url: str                      # page the screenshot shows (hyperlinked)
    image: Path | None = None
    kind: str = "web"             # "web" (Chrome tab) | "pdf" (Chrome PDF viewer)
    pdf_title: str = ""
    page_info: str = ""
    find_text: str = ""
    find_result: str = ""
    caption: str = ""
    note: str = ""
    found: bool | None = None


@dataclass
class Report:
    title: str
    status: str                   # "Accredited" | "Non-Accredited"
    summary: list[tuple[str, str]]
    sources: list[dict]           # {name, url, result, found}
    blocks: list[EvidenceBlock] = field(default_factory=list)
    statement: str = ""
    footer: str = ""


def _val(v: str) -> str:
    v = str(v or "—")
    return f'<a href="{e(v)}">{e(v)}</a>' if re.match(r"https?://", v) else e(v)


def _frame(b: EvidenceBlock) -> str:
    short = re.sub(r"^https?://", "", b.url)
    pdfbar = ""
    if b.kind == "pdf":
        find = ""
        if b.find_text:
            find = (f'<span class="find">🔍 {e(b.find_text)}<span class="fr">{e(b.find_result)}</span></span>')
        pdfbar = (f'<div class="pv"><span>☰&nbsp;&nbsp;{e(b.pdf_title)}</span><span>{e(b.page_info)}'
                  f'&nbsp;&nbsp;|&nbsp;&nbsp;−&nbsp; 100% &nbsp;+</span><span>{find}⤓ &nbsp;🖶</span></div>')
    img = f'<a href="{e(b.url)}"><img src="{data_url(b.image)}"></a>' if b.image and Path(b.image).exists() else ""
    return (f'<div class="bf"><div class="tb"><span class="nav">←&nbsp; →&nbsp; ⟳</span><div class="addr">'
            f'<span class="lock">🔒</span><span class="u">{e(short)}</span></div><span class="nav">☆ ⋮</span></div>'
            f'{pdfbar}<div class="shot{" dark" if b.kind == "pdf" else ""}">{img}</div></div>')


CSS = """
*{box-sizing:border-box} body{font-family:'Segoe UI',Calibri,Helvetica,Arial,sans-serif;color:#1f2328;margin:0;font-size:12.5px}
a{color:#0b57d0;text-decoration:underline;word-break:break-all}
h1{font-size:20px;margin:0} h2{font-size:14.5px;margin:20px 0 6px;border-bottom:2px solid #e5e7eb;padding-bottom:4px}
h3{font-size:13px;margin:16px 0 3px}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #1f3a68;padding-bottom:8px;margin-bottom:10px}
.badge{font-size:14px;font-weight:700;padding:6px 14px;border-radius:6px;color:#fff;white-space:nowrap}
.badge.ok{background:#15803d} .badge.no{background:#b91c1c}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #d6d9de;padding:5px 7px;text-align:left;vertical-align:top}
table.kv td:first-child{width:30%;background:#f6f8fa;font-weight:600}
table.src th{background:#f0f2f5;font-size:11.5px} table.src td{font-size:11.5px}
td.ok{color:#15803d;font-weight:600} td.no{color:#b91c1c;font-weight:600}
.stmt{border:1px solid #f2b8b5;background:#fdf1f0;padding:9px 12px;margin:10px 0;font-size:13px;font-weight:600;color:#8c1d18}
.stmt.ok{border-color:#a7d8b4;background:#effaf2;color:#14532d}
.srcnote{font-size:12px;font-weight:600;color:#b91c1c;margin:6px 0 0}
.lnk{font-size:11.5px;margin:2px 0 4px} .cap{font-size:11px;color:#555;margin:4px 0 0}
.note{border:1px solid #e5c07b;background:#fffbea;padding:7px 10px;font-size:11.5px;margin:6px 0}
.blk{page-break-inside:avoid;margin-bottom:14px}
.foot{margin-top:16px;font-size:10px;color:#6b7280;border-top:1px solid #e5e7eb;padding-top:6px}
.bf{border:1px solid #c9c9c9;border-radius:8px;overflow:hidden;margin:4px 0 4px;box-shadow:0 1px 3px rgba(0,0,0,.12)}
.tb{background:#f1f3f4;display:flex;align-items:center;gap:10px;padding:6px 10px;border-bottom:1px solid #ddd}
.nav{color:#5f6368;font-size:12px;white-space:nowrap}
.addr{flex:1;background:#fff;border:1px solid #c4c7c5;border-radius:16px;padding:3px 12px;font-size:11px;display:flex;gap:6px;
align-items:center;overflow:hidden} .addr .u{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pv{background:#323639;color:#f1f1f1;font-size:10.5px;display:flex;justify-content:space-between;padding:6px 12px}
.find{background:#fff;color:#222;border-radius:3px;padding:1px 8px;margin-right:12px} .fr{color:#b91c1c;margin-left:8px;font-weight:600}
.shot{background:#fff;text-align:center;line-height:0} .shot.dark{background:#525659;padding:8px 0}
.shot img{max-width:100%;max-height:800px;object-fit:contain}
h2.ev{page-break-before:always;margin-top:0}
"""


def render_html(r: Report) -> str:
    ok = r.status == "Accredited"
    out = [f'<div class="top"><h1>{e(r.title)}</h1><span class="badge {"ok" if ok else "no"}">{e(r.status)}</span>'
           f'</div><table class="kv">']
    out += [f"<tr><td>{e(k)}</td><td>{_val(v)}</td></tr>" for k, v in r.summary]
    out.append("</table>")
    if r.statement:
        out.append(f'<div class="stmt{" ok" if ok else ""}">{e(r.statement)}</div>')
    # Accredited → only the sources where the institution was found (the accreditation sources);
    # Non-Accredited → every official source consulted, with the statement that none lists the institution.
    shown = [s for s in r.sources if s.get("found")] if ok else list(r.sources)
    heading = "Accreditation source" + ("s" if len(shown) > 1 else "") if ok else "Sources consulted"
    out.append(f'<h2>{heading}</h2><table class="src"><tr><th style="width:26%">Official source</th>'
               '<th>URL</th><th style="width:28%">Result</th></tr>')
    for s in shown:
        out.append(f'<tr><td>{e(s["name"])}</td><td>{_val(s["url"])}</td>'
                   f'<td class="{"ok" if s.get("found") else "no"}">{e(s["result"])}</td></tr>')
    out.append("</table>")
    if not ok:
        out.append(f'<p class="srcnote">The institution was not found in any of the {len(shown)} official sources '
                   f'listed above.</p>')
    out.append('<h2 class="ev">Evidence</h2>')
    for b in r.blocks:
        out.append(f'<div class="blk"><h3>{e(b.heading)}</h3><p class="lnk"><a href="{e(b.url)}">{e(b.url)}</a></p>')
        if b.image:
            out.append(_frame(b))
        if b.note:
            out.append(f'<div class="note">{e(b.note)}</div>')
        if b.caption:
            out.append(f'<p class="cap">{e(b.caption)}</p>')
        out.append("</div>")
    out.append(f'<div class="foot">{e(r.footer)}</div>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{e(r.title)}</title><style>{CSS}</style>'
            f'</head><body>{"".join(out)}</body></html>')
