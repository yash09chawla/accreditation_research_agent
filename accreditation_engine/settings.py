"""Engine settings — read from environment variables (and an optional .env file).

Every setting has a safe default, so the engine runs with nothing but OPENAI_API_KEY set (and even without it:
the OpenAI name-resolution step is then skipped and only direct matches against the official lists are used).
A host project can also build `Settings(...)` itself and pass it to `AccreditationEngine(settings)`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

UGC_LIST_TYPES: dict[int, tuple[str, str]] = {  # UGC unitypeID -> (category label, public page token)
    1: ("Central University", "ddmCMsxJZgXH2S/m0uMOKQ=="),
    2: ("State University", "LZ1FUMk6U2JWGNLvhWfVSA=="),
    3: ("State Private University", "0wBmFB1Rb4JGVzq9UP/iOg=="),
    4: ("Deemed to be University", "UCL6fMspL2LJS89kv++N3A=="),
}


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines); never overrides variables already set in the environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.split(" #", 1)[0].strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    return [x.strip() for x in _env(name).split(",") if x.strip()]


@dataclass
class Settings:
    # --- OpenAI (name resolution only; never decides accreditation by itself) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_timeout_s: int = 90
    llm_enabled: bool = True

    # --- storage ---
    data_dir: Path = PROJECT_ROOT / "data"

    # --- official sources ---
    ugc_page_url: str = "https://www.ugc.gov.in/universitydetails/university?type={token}"
    ugc_api_url: str = "https://www.ugc.gov.in/universitydetails/Getuniversity_details?unitypeID={t}"
    aicte_list_url: str = ("https://aicte.gov.in/sites/default/files/approval/2025-26/"
                           "Groupwise-List%20of%20Institutions_compressed.pdf")
    aicte_notice_url: str = ("https://www.aicte.gov.in/sites/default/files/approval/2025-26/"
                             "Public%20Notice%202025-26.pdf")   # approval groups + regions (cited for AICTE)
    aicte_session: str = "2025-26"
    ugc_max_age_days: int = 7
    aicte_max_age_days: int = 30

    # --- evidence ---
    browser_channel: str = "chrome"          # installed Google Chrome; falls back to Playwright's Chromium
    max_browser_pages: int = 4               # concurrent screenshots across all requests
    live_ugc_screenshots: bool = True        # False → render UGC evidence from the official JSON only (offline)

    # --- API ---
    api_keys: list[str] = field(default_factory=list)   # empty → no auth (local use)
    cors_origins: list[str] = field(default_factory=list)
    public_base_url: str = ""                # e.g. https://ara.example.com → absolute proof URLs in responses
    user_agent: str = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

    @property
    def llm_available(self) -> bool:
        return self.llm_enabled and bool(self.openai_api_key)

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "audit"

    def ensure_dirs(self) -> None:
        for p in (self.cache_dir, self.reports_dir, self.audit_dir):
            p.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, dotenv: Path | None = PROJECT_ROOT / ".env") -> "Settings":
        if dotenv:
            _load_dotenv(dotenv)
        d = cls()
        return cls(
            openai_api_key=_env("OPENAI_API_KEY"),
            openai_model=_env("ARA_OPENAI_MODEL", d.openai_model),
            openai_timeout_s=_env_int("ARA_OPENAI_TIMEOUT_S", d.openai_timeout_s),
            llm_enabled=_env("ARA_DISABLE_LLM") != "1",
            data_dir=Path(_env("ARA_DATA_DIR", str(d.data_dir))).expanduser().resolve(),
            aicte_list_url=_env("ARA_AICTE_LIST_URL", d.aicte_list_url),
            aicte_notice_url=_env("ARA_AICTE_NOTICE_URL", d.aicte_notice_url),
            aicte_session=_env("ARA_AICTE_SESSION", d.aicte_session),
            ugc_max_age_days=_env_int("ARA_UGC_MAX_AGE_DAYS", d.ugc_max_age_days),
            aicte_max_age_days=_env_int("ARA_AICTE_MAX_AGE_DAYS", d.aicte_max_age_days),
            browser_channel=_env("ARA_BROWSER_CHANNEL", d.browser_channel),
            max_browser_pages=max(1, _env_int("ARA_MAX_BROWSER_PAGES", d.max_browser_pages)),
            live_ugc_screenshots=_env("ARA_LIVE_UGC_SCREENSHOTS", "1") != "0",
            api_keys=_env_list("ARA_API_KEYS"),
            cors_origins=_env_list("ARA_CORS_ORIGINS"),
            public_base_url=_env("ARA_PUBLIC_BASE_URL").rstrip("/"),
        )

    def ugc_page(self, list_type: int) -> str:
        return self.ugc_page_url.format(token=UGC_LIST_TYPES[list_type][1])
