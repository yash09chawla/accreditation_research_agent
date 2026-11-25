"""Request / response contract (pydantic). This is the public API of the engine — see status/api.md."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    university_name: str = Field(..., min_length=2, max_length=300,
                                 description="Awarding university (mandatory). Abbreviations such as VTU are accepted.")
    institute_name: Optional[str] = Field(None, max_length=300,
                                          description="Affiliated college / institute, if any.")
    degree: Optional[str] = Field(None, max_length=200,
                                  description="Programme, e.g. 'B.E. Civil Engineering' — decides AICTE vs UGC first.")
    state: Optional[str] = Field(None, max_length=80, description="Indian state / UT — disambiguates same names.")
    include_pdf_base64: bool = Field(False, description="Also return the proof PDF inline as base64.")

    @field_validator("institute_name", "degree", "state")
    @classmethod
    def _blank_to_none(cls, v):
        return v or None


class Proof(BaseModel):
    filename: str
    url: str                                   # GET this to download the PDF
    path: str                                  # local path (same machine)
    sha256: str
    size_bytes: int
    pages: int
    base64: Optional[str] = None


class MatchedInstitution(BaseModel):
    body: Literal["UGC", "AICTE"]
    name: str                                  # exactly as the official list writes it
    category: str                              # UGC category, or "AICTE approved institution"
    state: Optional[str] = None
    details: dict = {}                         # list-specific fields (UGC status/website, AICTE id/row/page …)
    match_score: float
    match_method: str                          # exact | fuzzy | website | resolved_name:exact …
    matched_on: str                            # the input or resolved name that matched
    state_check: Optional[bool] = None         # True same state as input, False different, None not checked


class SourceChecked(BaseModel):
    body: Literal["UGC", "AICTE"]
    name: str
    url: str
    found: bool
    result: str


class ResearchResponse(BaseModel):
    request_id: str
    accreditation_status: Literal["Accredited", "Non-Accredited"]
    accredited: bool
    accreditation_body: Optional[Literal["UGC", "AICTE"]] = None
    accreditation_body_name: Optional[str] = None
    accreditation_url: Optional[str] = None
    country: Optional[str] = None
    accreditation_proof: Proof
    accreditation_citations: list[dict] = []   # [{title, url}] — official sources cited for the result
    matched_institution: Optional[MatchedInstitution] = None
    other_listings: list[MatchedInstitution] = []
    alternatives: list[dict] = []
    routing: dict
    sources_checked: list[SourceChecked]
    name_resolution: Optional[dict] = None
    warnings: list[str] = []
    query: dict
    researched_at: str
    duration_seconds: float
    cost_usd: float
    engine_version: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: Optional[str] = None
