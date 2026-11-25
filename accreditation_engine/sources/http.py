"""HTTP download with fallbacks (some Indian government sites have broken TLS chains)."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

log = logging.getLogger("accreditation_engine.sources")


def fetch(url: str, user_agent: str, timeout: float = 60, headers: dict | None = None, retries: int = 2) -> bytes:
    """GET → bytes. Strict TLS first, then relaxed TLS, then curl; retried with backoff."""
    h = {"User-Agent": user_agent, **(headers or {})}
    last: Exception | None = None
    for attempt in range(retries + 1):
        for verify in (True, False):
            try:
                with httpx.Client(headers=h, follow_redirects=True, timeout=timeout, verify=verify) as c:
                    r = c.get(url)
                    r.raise_for_status()
                    return r.content
            except httpx.HTTPStatusError as e:
                last = e
                if e.response.status_code < 500:
                    raise
                break
            except Exception as e:      # TLS / timeout / connection → next strategy
                last = e
        try:
            r = subprocess.run(["curl", "-sSLf", "-m", str(int(timeout)), "-A", user_agent, url],
                               capture_output=True, timeout=timeout + 5)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed for {url}: {last}")


def atomic_write(dest: Path, data: bytes) -> None:
    """Write to a temp file then rename, so a crash never leaves a half-written cache file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def is_fresh(p: Path, max_age_days: int) -> bool:
    return p.exists() and (time.time() - p.stat().st_mtime) < max_age_days * 86400
