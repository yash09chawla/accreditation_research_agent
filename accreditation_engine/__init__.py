"""Accreditation Research Agent — find whether an Indian university / institute is listed by UGC or AICTE and
produce a hyperlinked proof PDF.

Library use (no HTTP):
    from accreditation_engine import AccreditationEngine
    engine = AccreditationEngine()                       # settings from env / .env
    result = engine.research_sync({"university_name": "Anna University"})
    print(result.accreditation_status, result.accreditation_body, result.accreditation_proof.path)

HTTP use: see accreditation_engine.api (python -m accreditation_engine serve).
"""
from .engine import VERSION, AccreditationEngine
from .models import ResearchRequest, ResearchResponse
from .settings import Settings

__all__ = ["AccreditationEngine", "ResearchRequest", "ResearchResponse", "Settings", "VERSION"]
__version__ = VERSION
