"""CLI.

    python -m accreditation_engine serve [--host 127.0.0.1] [--port 8100]
    python -m accreditation_engine research "Anna University" [--institute X] [--degree "B.E."] [--state "Tamil Nadu"]
    python -m accreditation_engine warm          # download + index the official lists
"""
from __future__ import annotations

import argparse
import json
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="accreditation_engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8100)
    rs = sub.add_parser("research")
    rs.add_argument("university_name")
    rs.add_argument("--institute")
    rs.add_argument("--degree")
    rs.add_argument("--state")
    sub.add_parser("warm")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("accreditation_engine.api:app", host=a.host, port=a.port)
        return 0
    from .engine import AccreditationEngine
    eng = AccreditationEngine()
    if a.cmd == "warm":
        eng.warm()
        print(json.dumps(eng.status(), indent=2))
        return 0
    res = eng.research_sync({"university_name": a.university_name, "institute_name": a.institute,
                             "degree": a.degree, "state": a.state})
    print(res.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
