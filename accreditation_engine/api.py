"""HTTP API (FastAPI).

    uvicorn accreditation_engine.api:app --port 8100          # or: python -m accreditation_engine serve

Endpoints (status/api.md):
  POST /v1/accreditation/research     run a research → ResearchResponse
  GET  /v1/reports/{id}               saved result JSON
  GET  /v1/reports/{id}/proof.pdf     proof PDF
  GET  /v1/sources                    official-source cache status
  POST /v1/sources/refresh            re-download UGC + AICTE lists
  GET  /health                        liveness + readiness
  GET  /                              single-file test UI
Auth: set ARA_API_KEYS=key1,key2 → every /v1 call needs header `X-API-Key: <key>` (or `?api_key=` for links).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import guard
from .engine import VERSION, AccreditationEngine
from .models import ErrorResponse, ResearchRequest, ResearchResponse
from .settings import PROJECT_ROOT, Settings

log = logging.getLogger("accreditation_engine.api")
RID_RE = re.compile(r"^ara_\d{8}_\d{6}_[0-9a-f]{6}$")
RESEARCH_TIMEOUT_S = 240


def create_app(settings: Settings | None = None, engine: AccreditationEngine | None = None) -> FastAPI:
    eng = engine or AccreditationEngine(settings)
    s = eng.s

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.warm_task = asyncio.create_task(eng.start())   # sources load in the background
        yield
        await eng.close()

    app = FastAPI(title="Accreditation Research Agent", version=VERSION, lifespan=lifespan,
                  description="Finds whether an Indian university / institute is listed by UGC or AICTE and returns "
                              "the result with a hyperlinked proof PDF.")
    app.state.engine = eng
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["GET", "POST"],
                           allow_headers=["*"])

    def require_key(x_api_key: str | None = Header(None), api_key: str | None = Query(None)):
        given = x_api_key or api_key or ""          # query form is for links/iframes (e.g. the proof PDF)
        if s.api_keys and not any(secrets.compare_digest(given, k) for k in s.api_keys):
            raise HTTPException(401, "missing or invalid X-API-Key")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        detail = "; ".join(f"{'.'.join(str(x) for x in err['loc'][1:]) or 'body'}: {err['msg']}"
                           for err in exc.errors())
        return JSONResponse(status_code=422, content={"error": "invalid_request", "detail": detail})

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {401: "unauthorized", 404: "not_found", 422: "invalid_request",
                                               500: "internal_error", 503: "not_ready", 504: "timeout"}.get(exc.status_code, "error"),
                                     "detail": str(exc.detail)})

    @app.get("/", include_in_schema=False)
    def ui():
        return FileResponse(PROJECT_ROOT / "ui" / "index.html")

    @app.get("/health")
    def health():
        st = eng.status()
        return {"status": "ok", "ready": st["ready"], "engine_version": VERSION, "llm": st["llm"]["available"]}

    @app.post("/v1/accreditation/research", response_model=ResearchResponse, response_model_exclude_none=False,
              responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
                         504: {"model": ErrorResponse}}, dependencies=[Depends(require_key)])
    async def research(body: ResearchRequest, request: Request):
        try:
            return await asyncio.wait_for(eng.research(body, str(request.base_url).rstrip("/")),
                                          RESEARCH_TIMEOUT_S)
        except guard.InputRejected as e:
            raise HTTPException(422, str(e))
        except asyncio.TimeoutError:
            raise HTTPException(504, f"research did not finish within {RESEARCH_TIMEOUT_S} s")
        except HTTPException:
            raise
        except RuntimeError as e:
            if "unavailable" in str(e):
                raise HTTPException(503, str(e))
            log.exception("research failed")
            raise HTTPException(500, f"research failed: {e}")
        except Exception as e:                       # always answer JSON, never a bare 500 page
            log.exception("research failed")
            raise HTTPException(500, f"research failed: {e.__class__.__name__}: {e}")

    def _report_dir(rid: str):
        if not RID_RE.match(rid):
            raise HTTPException(404, "unknown report id")
        d = s.reports_dir / rid
        if not d.is_dir():
            raise HTTPException(404, "unknown report id")
        return d

    @app.get("/v1/reports/{rid}", dependencies=[Depends(require_key)])
    def report(rid: str):
        p = _report_dir(rid) / "result.json"
        if not p.exists():
            raise HTTPException(404, "result not saved")
        return json.loads(p.read_text(encoding="utf-8"))

    @app.get("/v1/reports/{rid}/proof.pdf", dependencies=[Depends(require_key)])
    def proof(rid: str):
        d = _report_dir(rid)
        pdfs = sorted(d.glob("*.pdf"))
        if not pdfs:
            raise HTTPException(404, "proof not found")
        return FileResponse(pdfs[0], media_type="application/pdf", filename=pdfs[0].name,
                            content_disposition_type="inline")

    @app.get("/v1/sources", dependencies=[Depends(require_key)])
    def sources():
        return eng.status()

    @app.post("/v1/sources/refresh", dependencies=[Depends(require_key)])
    async def refresh():
        return await asyncio.to_thread(eng.refresh_sources)

    return app


def _default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()


app = _default_app()
