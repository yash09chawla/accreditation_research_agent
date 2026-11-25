"""Headless Chrome shared by all requests of one engine instance (launched once, ~1 s per page afterwards).

A semaphore caps concurrent pages (ARA_MAX_BROWSER_PAGES). If the engine is used from a new event loop
(e.g. repeated asyncio.run calls from sync code), the browser is relaunched on that loop.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright

from ..settings import Settings

log = logging.getLogger("accreditation_engine.browser")


class BrowserPool:
    def __init__(self, settings: Settings):
        self.s = settings
        self._pw = None
        self._browser = None
        self._loop = None
        self._lock: asyncio.Lock | None = None
        self._sem: asyncio.Semaphore | None = None

    async def _ensure(self):
        loop = asyncio.get_running_loop()
        if self._loop is not loop:            # first use, or a new event loop
            self._loop, self._browser, self._pw = loop, None, None
            self._lock = asyncio.Lock()
            self._sem = asyncio.Semaphore(self.s.max_browser_pages)
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._pw is None:
                    self._pw = await async_playwright().start()
                try:
                    self._browser = await self._pw.chromium.launch(channel=self.s.browser_channel or None,
                                                                   headless=True)
                except Exception as e:
                    log.warning("Chrome channel '%s' unavailable (%s) — using Playwright Chromium",
                                self.s.browser_channel, e)
                    self._browser = await self._pw.chromium.launch(headless=True)
        return self._browser

    async def start(self) -> None:
        await self._ensure()

    @asynccontextmanager
    async def page(self, width: int = 1366, height: int = 900, scale: float = 1):
        b = await self._ensure()
        async with self._sem:
            ctx = await b.new_context(viewport={"width": width, "height": height}, ignore_https_errors=True,
                                      device_scale_factor=scale,
                                      user_agent=self.s.user_agent, locale="en-IN")
            try:
                yield await ctx.new_page()
            finally:
                await ctx.close()

    async def html_to_pdf(self, html: str, out_path: str) -> None:
        async with self.page(1000, 800) as page:
            await page.set_content(html, wait_until="load")
            await page.emulate_media(media="screen")
            await page.pdf(path=out_path, format="A4", print_background=True,
                           margin={"top": "12mm", "bottom": "14mm", "left": "11mm", "right": "11mm"},
                           display_header_footer=True, header_template="<span></span>",
                           footer_template='<div style="font-size:8px;color:#888;width:100%;text-align:center">'
                                           'Accreditation Research Agent · page <span class="pageNumber"></span> / '
                                           '<span class="totalPages"></span></div>')

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._browser = self._pw = self._loop = None
