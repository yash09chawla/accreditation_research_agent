"""AccreditationEngine — the whole research flow behind one call.

    engine = AccreditationEngine()                     # Settings.from_env()
    result = await engine.research({"university_name": "Anna University", "degree": "B.E. Civil"})

Flow (status/architecture.md):
  1 validate + guard (public institution info only)
  2 route: technical programme → AICTE first, else UGC first (both lists are always searched)
  3 direct match against the cached official lists (UGC: 4 university lists; AICTE: approved institutions)
  4 no match → OpenAI resolves official / former names (public info) → match the official lists again
  5 decide: first body in the route order that lists the institution → Accredited; none → Non-Accredited
  6 evidence: live UGC page screenshots (search + highlighted row) / AICTE PDF page with highlighted row; on a miss,
    screenshots of every UGC list showing "No matching records found" + the AICTE text-search result
  7 proof PDF (hyperlinked sources) + JSON result saved under data/reports/<request_id>/
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

import pymupdf

from . import guard, routing
from .evidence import capture
from .evidence.browser import BrowserPool
from .evidence.report import EvidenceBlock, Report, render_html
from .matcher import Match, Matcher
from .models import MatchedInstitution, Proof, ResearchRequest, ResearchResponse, SourceChecked
from .resolver import Resolver
from .settings import UGC_LIST_TYPES, Settings
from .sources.aicte import AicteRow, AicteSource
from .sources.http import atomic_write, fetch
from .sources.ugc import UgcRecord, UgcSource
from .states import canonical_state
from .text import search_term

VERSION = "1.1.2"
BODY_NAMES = {"UGC": "University Grants Commission", "AICTE": "All India Council for Technical Education"}
log = logging.getLogger("accreditation_engine")


def _safe(s: str, n: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9 ._()-]+", " ", s or "").strip()[:n].strip() or "institution"


def _plural(category: str) -> str:
    return category.replace("University", "Universities")


class AccreditationEngine:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings.from_env()
        self.s.ensure_dirs()
        self.ugc = UgcSource(self.s)
        self.aicte = AicteSource(self.s)
        self.resolver = Resolver(self.s)
        self.browser = BrowserPool(self.s)
        self._matcher: Matcher | None = None
        self._matcher_key = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def warm(self) -> None:
        """Load (download/index if needed) both official lists and build the matcher. Blocking."""
        self.matcher()

    async def start(self) -> None:
        await asyncio.to_thread(self.warm)
        try:
            await self.browser.start()
        except Exception as e:      # evidence capture will report it per request
            log.warning("browser start failed: %s", e)

    async def close(self) -> None:
        await self.browser.close()

    def matcher(self) -> Matcher:
        with self._lock:
            ugc, aicte = self.ugc.records(), self.aicte.rows()
            key = (id(ugc), id(aicte))
            if self._matcher is None or self._matcher_key != key:
                self._matcher, self._matcher_key = Matcher(ugc, aicte), key
            return self._matcher

    def refresh_sources(self) -> dict:
        self.ugc.records(refresh=True)
        self.aicte.rows(refresh=True)
        self.matcher()
        return self.status()

    def status(self) -> dict:
        return {"engine_version": VERSION, "llm": {"available": self.resolver.available,
                                                   "model": self.s.openai_model},
                "sources": {"UGC": self.ugc.status(), "AICTE": self.aicte.status()},
                "ready": self._matcher is not None}

    def research_sync(self, request: ResearchRequest | dict, base_url: str = "") -> ResearchResponse:
        """Blocking call for non-async code. Starts and closes its own browser."""
        async def _run():
            try:
                return await self.research(request, base_url)
            finally:
                await self.browser.close()
        return asyncio.run(_run())

    # ------------------------------------------------------------------ research
    async def research(self, request: ResearchRequest | dict, base_url: str = "") -> ResearchResponse:
        req = request if isinstance(request, ResearchRequest) else ResearchRequest.model_validate(request)
        guard.check_public({"university_name": req.university_name, "institute_name": req.institute_name,
                            "degree": req.degree, "state": req.state})
        t0 = time.time()
        now = datetime.now().astimezone()
        rid = f"ara_{now.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}"
        rdir = self.s.reports_dir / rid
        work = rdir / "work"
        work.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        cost = 0.0

        route = routing.decide(req.university_name, req.institute_name, req.degree)
        state = canonical_state(req.state)
        if req.state and not state:
            warnings.append(f"State '{req.state}' is not a recognised Indian state/UT — not used for matching.")
        m = await asyncio.to_thread(self.matcher)
        warnings += [f"Source warning: {x}" for x in self.ugc.errors + self.aicte.errors[-1:]]

        uni, inst = req.university_name, req.institute_name
        ugc, a_uni, a_inst = await asyncio.gather(
            asyncio.to_thread(m.match_ugc, [uni], state),
            asyncio.to_thread(m.match_aicte, [uni], state, "", uni),
            asyncio.to_thread(m.match_aicte, [inst], state, "", inst) if inst else asyncio.sleep(0, None))

        # ---- OpenAI name resolution (only when the official lists gave no direct answer)
        resolution = None
        need = (not ugc and not a_uni) or bool(inst and route.technical and not a_inst)
        if need and self.resolver.available:
            try:
                res = await asyncio.to_thread(self.resolver.resolve, uni, inst, req.degree, req.state)
                cost += res.cost_usd
                hint_state = state or canonical_state(res.state)
                resolution = {"used": True, "cached": res.cached, "model": res.model,
                              "university_names": res.university_names, "institute_names": res.institute_names,
                              "website": res.website, "state": res.state, "country": res.country,
                              "category": res.category, "notes": res.notes, "cost_usd": res.cost_usd}
                if not ugc and (res.university_names or res.website):
                    ugc = await asyncio.to_thread(m.match_ugc, res.university_names, hint_state, res.website,
                                                  "resolved_name:")
                if not a_uni and res.university_names:
                    a_uni = await asyncio.to_thread(m.match_aicte, res.university_names, hint_state,
                                                    "resolved_name:", uni)
                if inst and not a_inst and res.institute_names:
                    a_inst = await asyncio.to_thread(m.match_aicte, res.institute_names, hint_state,
                                                     "resolved_name:", inst)
            except guard.InputRejected:
                raise
            except Exception as e:
                warnings.append(f"Name resolution (OpenAI) failed — only direct matches were used: {e}")
                resolution = {"used": False, "error": str(e)}
        elif need:
            warnings.append("OpenAI is not configured — only direct matches against the official lists were used.")
            resolution = {"used": False, "error": "OpenAI not configured"}

        # ---- decision
        aicte_hit = a_inst or a_uni
        found = {"UGC": ugc, "AICTE": aicte_hit}
        body = next((b for b in route.order if found[b]), None)
        primary: Match | None = found[body] if body else None
        for mt in (ugc, a_uni, a_inst):
            if mt and mt.state_check is False:
                warnings.append(f"{mt.body}: '{mt.name}' is listed in {mt.record.state}, not in the given state "
                                f"{state} — accepted on exact name; please confirm.")
            if mt and mt.alternatives:
                states = sorted({getattr(a, "state", "") for a in mt.alternatives} | {mt.record.state})
                warnings.append(f"{mt.body}: {len(mt.alternatives) + 1} listed records match '{mt.query_name}' "
                                f"({', '.join(s for s in states if s)}). Reported: '{mt.name}' ({mt.record.state}). "
                                + (f"Send 'state' to disambiguate." if not state else "Please confirm the right one."))

        # ---- AICTE approval group (Public Notice 2025-26) — cited whenever AICTE is the accreditation body
        group_info = self._group_info(aicte_hit.record) if body == "AICTE" else None

        # ---- evidence
        blocks, ev_warn = await self._evidence(req, ugc, a_uni, a_inst, body, work, m, group_info)
        warnings += ev_warn

        # ---- sources consulted
        sources = []
        for t, (label, _) in UGC_LIST_TYPES.items():
            hit = bool(ugc and ugc.record.list_type == t)
            sources.append(SourceChecked(body="UGC", name=f"UGC — List of {_plural(label)}", url=self.s.ugc_page(t),
                                         found=hit, result=f"Listed: {ugc.name} ({ugc.record.state})" if hit
                                         else "Not listed"))
        aicte_res = "; ".join(f"{lbl}: {h.name} — Sr.No {h.record.sr}, page {h.record.page}"
                              for lbl, h in (("Institute", a_inst), ("University", a_uni)) if h)
        sources.append(SourceChecked(body="AICTE", name=f"AICTE — Approved institutions {self.s.aicte_session}",
                                     url=self.s.aicte_list_url, found=bool(aicte_hit),
                                     result=aicte_res or "Not listed"))
        if group_info:
            sources.append(SourceChecked(body="AICTE", name=f"AICTE — Public Notice {self.s.aicte_session} "
                                                            f"(approval groups)",
                                         url=group_info["notice_url"], found=True,
                                         result=f"{group_info['group']}: {group_info['description']} — "
                                                f"{group_info['regions']}"))

        # ---- result fields
        accredited = body is not None
        body_url = None
        if body == "UGC":
            body_url = self.s.ugc_page(ugc.record.list_type)
        elif body == "AICTE":
            body_url = self.s.aicte_list_url
        # both bodies are Indian regulators → India when listed; Non-Accredited carries the proof only (the
        # resolver's country guess stays in name_resolution, it is not verified)
        country = "India" if accredited else None
        matched = self._matched(primary) if primary else None
        others = [self._matched(x) for x in (ugc, a_inst, a_uni) if x and x is not primary
                  and not (x is a_uni and a_inst is not None and x.record is a_inst.record)]
        alternatives = [self._alt(a) for a in (primary.alternatives if primary else [])]
        if group_info and matched:
            matched.details["approval_group"] = group_info
        citations = []
        if body == "UGC":
            citations.append({"title": f"UGC — List of {_plural(ugc.record.category)}", "url": body_url})
        elif body == "AICTE":
            citations += [{"title": f"AICTE — Approved institutions {self.s.aicte_session}",
                           "url": f"{self.s.aicte_list_url}#page={aicte_hit.record.page}"},
                          {"title": f"AICTE — Public Notice {self.s.aicte_session} (approval group "
                                    f"{group_info['group']})", "url": group_info["notice_url"]}]

        # ---- proof PDF
        summary = [("University (requested)", uni)]
        if inst:
            summary.append(("Institute (requested)", inst))
        if req.degree:
            summary.append(("Degree (requested)", req.degree))
        if req.state:
            summary.append(("State (requested)", req.state))
        if primary:
            summary.append(("Name in official list", f"{primary.name} — {matched.category}"
                                                     + (f", {primary.record.state}" if primary.record.state else "")))
        summary += [("Accreditation status", "Accredited" if accredited else "Non-Accredited"),
                    ("Accreditation body", f"{body} — {BODY_NAMES[body]}" if body else "None (not listed by UGC or AICTE)"),
                    ("Official source URL", body_url or "—"),
                    ("Country", country or "—")]
        if body == "UGC":
            summary.append(("UGC status", ugc.record.status or "—"))
            if ugc.record.website:
                summary.append(("Official website (per UGC)", ugc.record.website))
        elif body == "AICTE":
            r = aicte_hit.record
            summary.append(("AICTE listing", f"{r.aicte_id} · Sr.No {r.sr} · page {r.page} · {r.region} region · "
                                             f"{r.district} · {r.group}"))
            summary.append(("AICTE approval group", f"{group_info['group']} — {group_info['description']} "
                                                    f"({group_info['regions']})"))
            summary.append(("Citation — AICTE Public Notice", group_info["notice_url"]))
        summary += [("Report ID", rid), ("Researched at", now.strftime("%d-%m-%Y %H:%M:%S %Z (UTC%z)"))]
        if accredited:
            statement = (f"{primary.name} is listed in the official {body} list "
                         f"({matched.category}) — Accredited by the {BODY_NAMES[body]} ({body}).")
            if group_info:
                statement += (f" AICTE approval group: {group_info['group']} ({group_info['region']} region), "
                              f"per the AICTE Public Notice {self.s.aicte_session}.")
        else:
            statement = (f"\"{uni}\"{f' / {inst!r}' if inst else ''} was not found in the official UGC university "
                         f"lists (Central, State, State Private, Deemed to be Universities) or in the AICTE list of "
                         f"approved institutions {self.s.aicte_session}. It is Non-Accredited with UGC and AICTE.")
        report = Report(
            title="Accreditation Verification Report", status="Accredited" if accredited else "Non-Accredited",
            summary=summary, sources=[s.model_dump() for s in sources], blocks=blocks, statement=statement,
            footer=(f"Generated by Accreditation Research Agent v{VERSION} on {now.strftime('%d-%m-%Y %H:%M:%S %Z')}. "
                    f"Sources: UGC university lists (ugc.gov.in, data cached {self._cached_at('UGC')}) and the AICTE "
                    f"approved-institution list {self.s.aicte_session} (aicte.gov.in, cached "
                    f"{self._cached_at('AICTE')}). All screenshots are taken in Google Chrome at the official URL: UGC pages "
                    f"live with the site's own search; AICTE PDFs downloaded live from aicte.gov.in and shown in "
                    f"Chrome's PDF viewer. Highlights are added by the engine to mark the matched record. The address "
                    f"bar above each capture shows the URL of the captured page."))
        pdf_name = f"Accreditation - {_safe(uni)}.pdf"
        pdf_path = rdir / pdf_name
        await self.browser.html_to_pdf(render_html(report), str(pdf_path))
        data = pdf_path.read_bytes()
        pages = pymupdf.open(str(pdf_path)).page_count
        base = (self.s.public_base_url or base_url or "").rstrip("/")
        proof = Proof(filename=pdf_name, url=f"{base}/v1/reports/{rid}/proof.pdf", path=str(pdf_path),
                      sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), pages=pages)

        resp = ResearchResponse(
            request_id=rid, accreditation_status="Accredited" if accredited else "Non-Accredited",
            accredited=accredited, accreditation_body=body, accreditation_body_name=BODY_NAMES.get(body),
            accreditation_url=body_url, country=country, accreditation_proof=proof, matched_institution=matched,
            other_listings=others, alternatives=alternatives, routing=route.as_dict(), sources_checked=sources,
            name_resolution=resolution, warnings=list(dict.fromkeys(warnings)), accreditation_citations=citations,
            query=req.model_dump(exclude={"include_pdf_base64"}), researched_at=now.isoformat(timespec="seconds"),
            duration_seconds=round(time.time() - t0, 2), cost_usd=round(cost, 5), engine_version=VERSION)
        (rdir / "result.json").write_text(resp.model_dump_json(indent=2), encoding="utf-8")
        if req.include_pdf_base64:
            import base64
            resp.accreditation_proof.base64 = base64.b64encode(data).decode()
        log.info("%s %s → %s %s (%.1fs)", rid, uni, resp.accreditation_status, body or "", resp.duration_seconds)
        return resp

    # ------------------------------------------------------------------ helpers
    def _cached_at(self, body: str) -> str:
        p = self.s.cache_dir / "ugc_2.json" if body == "UGC" else self.aicte.pdf_path
        return time.strftime("%d-%m-%Y", time.localtime(p.stat().st_mtime)) if p.exists() else "—"

    @staticmethod
    def _matched(mt: Match) -> MatchedInstitution:
        r = mt.record
        if isinstance(r, UgcRecord):
            return MatchedInstitution(body="UGC", name=r.name, category=r.category, state=r.state or None,
                                      details={"ugc_status": r.status, "website": r.website, "address": r.address,
                                               "pin": r.pin},
                                      match_score=mt.score, match_method=mt.method, matched_on=mt.query_name,
                                      state_check=mt.state_check)
        return MatchedInstitution(body="AICTE", name=r.name, category="AICTE approved institution",
                                  state=r.state or None, details=r.as_dict(), match_score=mt.score,
                                  match_method=mt.method, matched_on=mt.query_name, state_check=mt.state_check)

    def _group_info(self, r: AicteRow) -> dict:
        desc, regions = capture.AICTE_GROUPS.get(r.group, ("", ""))
        label, states, _ = capture.AICTE_REGIONS.get(r.region, (r.region, "", 0))
        return {"group": r.group, "description": desc, "regions": regions,
                "region": capture.REGION_DISPLAY.get(r.region, label or r.region),
                "region_states": states, "notice_url": f"{self.s.aicte_notice_url}#page=2"}

    async def _live_pdf(self, url: str, cache: Path) -> tuple[bytes, str | None]:
        """Download an official PDF now; on failure use the cached copy. Returns (bytes, warning or None)."""
        try:
            data = await asyncio.to_thread(fetch, url, self.s.user_agent, 120)
            if not data.startswith(b"%PDF"):
                raise RuntimeError("response is not a PDF")
            if not cache.exists() or cache.stat().st_size != len(data):
                await asyncio.to_thread(atomic_write, cache, data)
            return data, None
        except Exception as e:
            if cache.exists():
                when = time.strftime("%d-%m-%Y", time.localtime(cache.stat().st_mtime))
                return cache.read_bytes(), (f"Live download of {url} failed ({e}); the copy downloaded on {when} "
                                            f"was shown instead.")
            raise

    @staticmethod
    def _alt(r) -> dict:
        if isinstance(r, UgcRecord):
            return {"body": "UGC", "name": r.name, "category": r.category, "state": r.state, "website": r.website}
        return {"body": "AICTE", "name": r.name, "state": r.state, "district": r.district, "aicte_id": r.aicte_id}

    async def _evidence(self, req: ResearchRequest, ugc: Match | None, a_uni: Match | None, a_inst: Match | None,
                        body: str | None, work: Path, m: Matcher,
                        group_info: dict | None = None) -> tuple[list[EvidenceBlock], list[str]]:
        warnings: list[str] = []
        s = self.s
        pdf = self.aicte.pdf_path
        n_pages = self.aicte.page_count
        pdf_title = Path(s.aicte_list_url).name.replace("%20", " ")

        async def pdf_capture(url: str, data: bytes, page_no: int, png: Path, top: float | None = None,
                              fit: bool = False, title: str = "", height: int = 900) -> tuple[str, str]:
            """Chrome PDF viewer capture at the official URL; local render if the browser fails.
            Returns (url shown, frame kind)."""
            try:
                shown = await capture.pdf_in_browser(self.browser, url, data, page_no, png, top_pt=top, fit_page=fit,
                                                     height=height)
                return shown, "web"
            except Exception as e:
                warnings.append(f"Browser capture of {title or url} failed ({e.__class__.__name__}: {e}) — the PDF "
                                f"page was rendered locally instead.")
                await asyncio.to_thread(capture.render_pdf_page, data, page_no, png)
                return f"{url.split('#')[0]}#page={page_no}", "pdf"

        async def ugc_found_block() -> EvidenceBlock:
            r: UgcRecord = ugc.record
            url = s.ugc_page(r.list_type)
            png = work / "ugc_match.jpg"
            caption = (f"{r.name} · {r.address} {r.pin} · {r.state} · UGC status {r.status} · website {r.website}")
            if s.live_ugc_screenshots:
                try:
                    facts = await capture.ugc_live(self.browser, url, r.name, png, [(r.name, r.state)])
                    if not facts.get("highlighted"):
                        warnings.append("UGC live page: the matched row could not be highlighted on the page.")
                    return EvidenceBlock(heading=f"UGC — List of {_plural(r.category)} — search \"{r.name}\"",
                                         url=url, image=png, caption=f"{caption} · page shows: {facts.get('info')}",
                                         found=True)
                except Exception as e:
                    warnings.append(f"UGC live page could not be captured ({e.__class__.__name__}: {e}) — evidence "
                                    f"shows the record from UGC's official data endpoint instead.")
            return EvidenceBlock(heading=f"UGC — List of {_plural(r.category)} (official data)", url=url,
                                 note=f"Record in the official UGC list: {caption}", found=True)

        async def ugc_missing_blocks() -> list[EvidenceBlock]:
            term = search_term(req.university_name)
            out: list[EvidenceBlock] = []

            async def one(t: int, label: str) -> EvidenceBlock:
                url = s.ugc_page(t)
                png = work / f"ugc_search_{t}.jpg"
                head = f"UGC — List of {_plural(label)} — search \"{term}\""
                if s.live_ugc_screenshots:
                    try:
                        facts = await capture.ugc_live(self.browser, url, term, png, height=720)   # 2 per page
                        cap = ("The official list returns no matching records." if facts.get("empty") else
                               f"The site's text search shows rows containing the search words ({facts.get('info')}); "
                               f"none of them is \"{req.university_name}\" (no record above the match threshold).")
                        return EvidenceBlock(heading=head, url=url, image=png, caption=cap, found=False)
                    except Exception as e:
                        warnings.append(f"UGC {label} page could not be captured: {e.__class__.__name__}: {e}")
                return EvidenceBlock(heading=head, url=url, found=False,
                                     note=f"All records of the official UGC {label} list (data endpoint) were searched "
                                          f"for \"{req.university_name}\": no match.")
            out = await asyncio.gather(*(one(t, lbl) for t, (lbl, _) in UGC_LIST_TYPES.items()))
            return list(out)

        async def aicte_found_blocks() -> list[EvidenceBlock]:
            targets = []
            for label, mt in (("Institute", a_inst), ("University", a_uni)):
                if mt and all(mt.record is not t[1].record for t in targets):
                    targets.append((label, mt))
            if not targets:
                return []
            raw, warn = await self._live_pdf(s.aicte_list_url, pdf)
            if warn:
                warnings.append(warn)
            data, where = await asyncio.to_thread(capture.annotate_list, raw, [mt.record for _, mt in targets])
            out = []
            for label, mt in targets:
                r: AicteRow = mt.record
                page_no, top = where.get(r.sr, (r.page, r.bbox[1]))
                png = work / f"aicte_{r.sr}.jpg"
                shown, kind = await pdf_capture(s.aicte_list_url, data, page_no, png, top=top - 130,
                                                title="AICTE list")
                out.append(EvidenceBlock(
                    heading=f"AICTE — Approved institutions {s.aicte_session} — {label}: {r.name}",
                    url=shown, image=png, kind=kind, pdf_title=pdf_title, page_info=f"{page_no} / {n_pages}",
                    caption=f"Sr.No {r.sr} · AICTE Permanent Id {r.aicte_id} · {r.name} · {r.region} region · "
                            f"{r.state} · {r.district} · {r.city} · {r.group}", found=True))
            return out

        async def notice_block() -> EvidenceBlock | None:
            if not group_info:
                return None
            gi = group_info
            raw, warn = await self._live_pdf(s.aicte_notice_url, s.cache_dir / f"aicte_notice_{s.aicte_session}.pdf")
            if warn:
                warnings.append(warn)
            data, found = await asyncio.to_thread(capture.annotate_notice, raw, gi["group"],
                                                  (a_inst or a_uni).record.region)
            if not (found["group"] and found["region"]):
                warnings.append("AICTE Public Notice: the group/region rows could not be located for highlighting "
                                f"(group found: {found['group']}, region found: {found['region']}).")
            png = work / "aicte_notice.jpg"
            shown, kind = await pdf_capture(s.aicte_notice_url, data, 2, png, top=30, height=1450,
                                            title="AICTE Public Notice")   # both notice tables in view
            return EvidenceBlock(
                heading=f"AICTE — Public Notice {s.aicte_session} — approval group {gi['group']}, {gi['region']} region",
                url=shown, image=png, kind=kind, pdf_title=Path(s.aicte_notice_url).name.replace("%20", " "),
                page_info="2 / 2",
                caption=f"{gi['group']}: {gi['description']} — {gi['regions']}. {gi['region']} covers "
                        f"{gi['region_states']}.", found=True)

        async def aicte_missing_block() -> EvidenceBlock:
            png = work / "aicte_list.jpg"
            raw, warn = await self._live_pdf(s.aicte_list_url, pdf)
            if warn:
                warnings.append(warn)
            shown, kind = await pdf_capture(s.aicte_list_url, raw, 1, png, top=0, title="AICTE list")
            terms = [search_term(req.university_name)] + ([search_term(req.institute_name)] if req.institute_name else [])
            hits = {t: await asyncio.to_thread(capture.aicte_text_hits, pdf, t) for t in terms}
            n_rows = len(m.aicte)
            note = (f"All {n_pages} pages / {n_rows:,} rows of the official AICTE list were searched. "
                    + " ".join(f"Text search for \"{t}\": {h} occurrence(s)." for t, h in hits.items())
                    + f" Name match against every row (exact and fuzzy ≥ 93 %): no matching institution.")
            if any(hits.values()):
                note += " (Text occurrences are only parts of other, longer institution names.)"
            return EvidenceBlock(heading=f"AICTE — Approved institutions {s.aicte_session} — search \"{terms[0]}\"",
                                 url=shown, image=png, kind=kind, pdf_title=pdf_title, page_info=f"1 / {n_pages}",
                                 note=note, found=False)

        blocks: list[EvidenceBlock] = []
        if body == "UGC":
            first, rest = await asyncio.gather(ugc_found_block(), aicte_found_blocks())
            blocks += [first] + rest
        elif body == "AICTE":
            listed, notice, ugc_b = await asyncio.gather(aicte_found_blocks(), notice_block(),
                                                         ugc_found_block() if ugc else asyncio.sleep(0, None))
            blocks += listed + [b for b in (notice, ugc_b) if b]
        else:
            ugc_blocks, aicte_block = await asyncio.gather(ugc_missing_blocks(), aicte_missing_block())
            blocks += ugc_blocks + [aicte_block]
        return blocks, warnings
