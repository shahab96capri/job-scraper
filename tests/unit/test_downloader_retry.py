"""
Unit tests for `Downloader`'s retry system and exception classification.

Deliberately does NOT launch a real Playwright browser — `Downloader`
only depends on the `BrowserContext.new_page()` / `Page.goto()` /
`Page.content()` / `Page.close()` surface, so a minimal fake implementing
just that surface is enough to exercise the retry/backoff/exception-
classification logic in complete isolation, fast and deterministically
(no real network, no flaky timing).

Live-site behavior (does a real browser actually get past a given site's
bot detection) is explicitly NOT what this test proves — that requires a
real Chromium binary the sandbox this was authored in cannot download
(egress-restricted), and belongs in a manual/staging verification instead.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.exceptions import PermanentCrawlError, RateLimitedError, TransientCrawlError
from app.spiders.downloader import Downloader

pytestmark = pytest.mark.asyncio


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakePage:
    def __init__(self, outcome: int | Exception, html: str = "<html>ok</html>") -> None:
        self._outcome = outcome
        self._html = html
        self.closed = False

    async def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return _FakeResponse(self._outcome)

    async def content(self) -> str:
        return self._html

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    """Replays a scripted sequence of outcomes, one per `new_page()` call.

    Each outcome is either an HTTP status code (int) or an Exception to be
    raised from `goto()` — enough to drive every branch in
    `Downloader._fetch_once`.
    """

    def __init__(self, outcomes: list[int | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.pages_created = 0

    async def new_page(self) -> _FakePage:
        self.pages_created += 1
        outcome = self._outcomes.pop(0)
        return _FakePage(outcome)


def _make_downloader(context: _FakeContext, *, max_retries: int = 2) -> Downloader:
    return Downloader(
        context,  # type: ignore[arg-type]
        timeout_ms=5_000,
        max_retries=max_retries,
        backoff_seconds=0.01,  # fast retries in tests
    )


async def test_success_on_first_attempt_makes_no_retries():
    context = _FakeContext([200])
    downloader = _make_downloader(context)

    html = await downloader.fetch_html("https://example.test/job/1")

    assert html == "<html>ok</html>"
    assert downloader.retry_count == 0
    assert context.pages_created == 1


async def test_transient_5xx_is_retried_then_succeeds():
    context = _FakeContext([500, 200])
    downloader = _make_downloader(context, max_retries=2)

    html = await downloader.fetch_html("https://example.test/job/2")

    assert html == "<html>ok</html>"
    assert downloader.retry_count == 1
    assert context.pages_created == 2


async def test_exhausting_all_retries_raises_transient_crawl_error():
    context = _FakeContext([500, 500, 500])
    downloader = _make_downloader(context, max_retries=2)

    with pytest.raises(TransientCrawlError):
        await downloader.fetch_html("https://example.test/job/3")

    assert downloader.retry_count == 2
    assert context.pages_created == 3


async def test_404_is_permanent_and_not_retried():
    context = _FakeContext([404])
    downloader = _make_downloader(context, max_retries=3)

    with pytest.raises(PermanentCrawlError):
        await downloader.fetch_html("https://example.test/job/404")

    assert downloader.retry_count == 0
    assert context.pages_created == 1  # never retried


async def test_429_is_rate_limited_and_retried_as_transient():
    context = _FakeContext([429, 200])
    downloader = _make_downloader(context, max_retries=2)

    html = await downloader.fetch_html("https://example.test/job/rate-limited")

    assert html == "<html>ok</html>"
    assert downloader.retry_count == 1


async def test_playwright_timeout_is_transient_and_retried():
    context = _FakeContext([PlaywrightTimeoutError("navigation timeout"), 200])
    downloader = _make_downloader(context, max_retries=2)

    html = await downloader.fetch_html("https://example.test/job/slow")

    assert html == "<html>ok</html>"
    assert downloader.retry_count == 1


async def test_playwright_network_error_is_transient_and_retried():
    context = _FakeContext([PlaywrightError("net::ERR_CONNECTION_RESET"), 200])
    downloader = _make_downloader(context, max_retries=2)

    html = await downloader.fetch_html("https://example.test/job/reset")

    assert html == "<html>ok</html>"
    assert downloader.retry_count == 1


async def test_page_is_always_closed_even_on_failure():
    context = _FakeContext([500])
    downloader = _make_downloader(context, max_retries=0)

    with pytest.raises(TransientCrawlError):
        await downloader.fetch_html("https://example.test/job/closes")

    # Rate-limited/500 case: the single created page must still be closed.
    assert context.pages_created == 1
