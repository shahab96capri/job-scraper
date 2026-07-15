"""
Browser Singleton: one Playwright driver + one Chromium `Browser` process
per application process.

Design decisions:
- Launching a browser process is expensive (hundreds of ms, a chunk of
  memory). Every spider run needs *a* browser, but none of them should pay
  that cost or spawn a competing process — so `get_browser()` is cached
  behind an `asyncio.Lock`-guarded singleton, the "Browser Singleton"
  requirement from the architecture spec.
- The **Browser** itself is shared; **BrowserContext**s are not.
  `new_context()` hands each spider run an isolated context (its own
  cookies/local-storage/cache), so concurrent spiders (`MAX_CONCURRENT_
  SPIDERS`) never leak session state into one another, while still only
  ever running one underlying browser process. This mirrors real browser
  usage: one Chrome process, many independent "windows".
- A plain module-level global + `asyncio.Lock` (rather than
  `functools.lru_cache`) is required here because browser creation is
  itself a coroutine — `lru_cache` cannot cache the *result* of an
  in-flight async call, only a completed one, which would let two
  concurrent callers each launch their own browser (double-checked
  locking avoids that race).
- Context creation applies a realistic Iranian-locale fingerprint
  (`fa-IR` locale, Tehran timezone, a current desktop Chrome UA, a
  standard viewport) — the two sandboxed HTTP tests performed for this
  project (Commit 1) showed all four target sites return HTTP 403 to a
  bare `requests` client; a real, consistently-fingerprinted browser
  context is the platform's mitigation, though it is not guaranteed to
  bypass every bot-detection system a site may run.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.config.settings import get_settings
from app.core.logging import logger

_playwright: Playwright | None = None
_browser: Browser | None = None
_lock = asyncio.Lock()

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
DEFAULT_LOCALE = "fa-IR"
DEFAULT_TIMEZONE = "Asia/Tehran"
DEFAULT_VIEWPORT = {"width": 1366, "height": 768}


async def get_browser() -> Browser:
    """Return the process-wide `Browser` singleton, launching it on first use."""
    global _playwright, _browser

    if _browser is not None and _browser.is_connected():
        return _browser

    async with _lock:
        # Re-check after acquiring the lock: another coroutine may have
        # already launched the browser while we were waiting on it.
        if _browser is not None and _browser.is_connected():
            return _browser

        settings = get_settings()
        if _playwright is None:
            _playwright = await async_playwright().start()

        _browser = await _playwright.chromium.launch(
            headless=settings.playwright_headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        logger.bind(component="core.browser").info(
            f"Browser launched | headless={settings.playwright_headless}"
        )
        return _browser


async def new_context(**overrides: object) -> BrowserContext:
    """Create a fresh, isolated `BrowserContext` from the shared browser.

    Every spider run should call this once and dispose of the context
    (via `context.close()`) when the run finishes — never share a context
    across concurrent spiders, and never reuse one across runs (stale
    cookies from a previous run should not bleed into the next).
    """
    browser = await get_browser()
    context_kwargs: dict[str, object] = dict(
        user_agent=DEFAULT_USER_AGENT,
        locale=DEFAULT_LOCALE,
        timezone_id=DEFAULT_TIMEZONE,
        viewport=DEFAULT_VIEWPORT,
        extra_http_headers={"Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7"},
    )
    context_kwargs.update(overrides)
    return await browser.new_context(**context_kwargs)


async def dispose_browser() -> None:
    """Close the shared browser and stop the Playwright driver.

    Call once, on graceful application shutdown (`main.py`'s `finally`
    block) — never per-spider-run, since the browser is shared.
    """
    global _playwright, _browser

    async with _lock:
        if _browser is not None:
            await _browser.close()
            _browser = None
            logger.bind(component="core.browser").info("Browser closed")
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None
