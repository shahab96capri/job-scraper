"""
`Downloader` — the only class that actually drives a Playwright `Page`.

Sits between `BaseSpider` and the Browser Singleton: spiders ask the
downloader for HTML by URL and never touch `playwright` themselves ("a
spider never opens a browser manually" — architecture spec). This also
means the retry system lives in exactly one place, shared by every spider
regardless of site.

Design decisions:
- **Exception classification** happens here, once: Playwright timeouts and
  `None` responses become `TransientCrawlError`; HTTP 404 becomes
  `PermanentCrawlError` (retrying won't fix a deleted job posting); HTTP
  429 or a response whose final URL looks like a bot-challenge page
  becomes `RateLimitedError` (still transient, but worth a longer backoff
  than a plain network blip — see `retry_wait_seconds`); HTTP 5xx and any
  other Playwright/network exception become `TransientCrawlError`. This is
  what `BaseSpider`'s retry loop branches on.
- **`tenacity.AsyncRetrying`** is constructed per-call (not a static
  `@retry` decorator) so `max_retries` / `retry_backoff_seconds` come from
  the injected `Settings` instance rather than being frozen at import
  time — the same `Downloader` class behaves differently in tests
  (few/no retries, fast) vs production (real backoff) purely through
  configuration.
- **A fresh `Page` per request**, always closed in a `finally` block, even
  on failure — leaking pages inside a long-lived `BrowserContext` is a
  real memory leak across a multi-hour crawl.
"""

from __future__ import annotations

from playwright.async_api import BrowserContext, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import PermanentCrawlError, RateLimitedError, TransientCrawlError
from app.core.logging import logger

RATE_LIMIT_STATUS = 429
NOT_FOUND_STATUS = 404
SERVER_ERROR_THRESHOLD = 500


class Downloader:
    """Fetches rendered HTML for a URL through a shared browser context,
    with retry/backoff on transient failures."""

    def __init__(
        self,
        context: BrowserContext,
        *,
        timeout_ms: int,
        max_retries: int,
        backoff_seconds: float,
    ) -> None:
        self._context = context
        self._timeout_ms = timeout_ms
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._retry_count = 0

    @property
    def retry_count(self) -> int:
        """Total number of retry attempts made across every `fetch_html`
        call on this downloader instance — surfaced by the Pipeline into
        `ScrapeHistory.retry_count` for operational visibility."""
        return self._retry_count

    async def fetch_html(self, url: str) -> str:
        """Return the fully-rendered HTML for `url`.

        Raises `PermanentCrawlError` immediately (no retry) for failures
        that will not resolve themselves. Raises `TransientCrawlError` (or
        the `RateLimitedError` subclass) after exhausting
        `max_retries` retries with exponential backoff.
        """
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(TransientCrawlError),
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(
                multiplier=self._backoff_seconds, min=self._backoff_seconds, max=60
            ),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    if attempt.retry_state.attempt_number > 1:
                        self._retry_count += 1
                        logger.bind(component="spiders.downloader").warning(
                            f"Retry {attempt.retry_state.attempt_number - 1}/"
                            f"{self._max_retries} for {url}"
                        )
                    return await self._fetch_once(url)
        except RetryError as exc:  # all attempts exhausted
            raise TransientCrawlError(
                f"Exhausted {self._max_retries} retries fetching {url}"
            ) from exc

        raise AssertionError("unreachable")  # pragma: no cover

    async def _fetch_once(self, url: str) -> str:
        page = await self._context.new_page()
        try:
            try:
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self._timeout_ms
                )

                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(5000)

            except PlaywrightTimeoutError as exc:
                raise TransientCrawlError(f"Timeout navigating to {url}") from exc
            except PlaywrightError as exc:
                raise TransientCrawlError(f"Navigation error for {url}: {exc}") from exc

            if response is None:
                raise TransientCrawlError(f"No response received for {url}")

            status = response.status
            if status == NOT_FOUND_STATUS:
                raise PermanentCrawlError(f"{url} returned HTTP 404")
            if status == RATE_LIMIT_STATUS:
                raise RateLimitedError(f"{url} returned HTTP 429 (rate limited)")
            if status >= SERVER_ERROR_THRESHOLD:
                raise TransientCrawlError(f"{url} returned HTTP {status}")
            if status >= 400:
                # Other 4xx (401/403/etc): the site is actively refusing
                # this request. Retrying with the exact same fingerprint
                # will not help, so this is permanent from this
                # downloader's point of view — a human needs to adjust
                # the crawl strategy (headers, proxy, cadence).
                raise PermanentCrawlError(f"{url} returned HTTP {status}")

            html=await page.content()

            with open("debug_jobvision.html", "w", encoding="utf-8") as f:
                f.write(html)
            return html
        finally:
            await page.close()
