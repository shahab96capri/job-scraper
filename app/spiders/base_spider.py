"""
`BaseSpider` — the crawling/navigation layer every site-specific spider
(JobVision, Jobinja, IranTalent, Ponisha — Commit 4) inherits from.

Strict responsibilities (per the architecture spec, "A spider NEVER:
writes SQL, exports JSON, exports Excel, contains business logic, opens a
browser manually"):
- Knows how to build a listing-page URL for a given page number.
- Knows how to pull job/company detail URLs out of a listing page's HTML.
- Knows when to stop paginating (max pages reached, an empty page, or —
  for Incremental Crawling — a page containing only already-known IDs).
- Delegates the actual HTTP/browser work to an injected `Downloader`.

It does NOT parse job data fields (that's `BaseParser`, Commit 4), does
NOT touch the database (that's the Repository layer via the Pipeline),
and does NOT decide what happens to the HTML it fetches beyond yielding it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from app.core.logging import logger
from app.spiders.downloader import Downloader

DEFAULT_INCREMENTAL_STOP_STREAK = 2
"""Number of consecutive listing pages yielding *zero new* job IDs before
an incremental crawl gives up early. A single page of overlap is expected
(pagination can shift by one item between requests as new jobs get
posted); two in a row is a reliable signal we've caught up to where the
last successful run left off."""


@dataclass(frozen=True, slots=True)
class CrawlPageResult:
    """What a spider extracts from one listing page — URLs only, no data
    fields. `job_urls`/`company_urls` may overlap in practice (a listing
    page often links directly to both), sites are free to populate only
    the one they support."""

    job_urls: list[str]
    company_urls: list[str]


class BaseSpider(ABC):
    """Abstract base for all site-specific spiders.

    Subclasses set `SITE_CODE` / `SITE_NAME` / `BASE_URL` (matching a
    `Source` row) and implement `build_listing_url()` +
    `extract_page_urls()`. Everything else — pagination bookkeeping,
    incremental stop logic, delegating to the `Downloader` — is handled
    here so no per-site duplication of that control flow exists.
    """

    SITE_CODE: str
    SITE_NAME: str
    BASE_URL: str

    def __init__(self, downloader: Downloader, *, max_pages: int) -> None:
        self.downloader = downloader
        self.max_pages = max_pages
        self.pages_fetched = 0
        self._logger = logger.bind(component=f"spiders.{self.SITE_CODE}")

    # --- Methods every concrete spider must implement ---

    @abstractmethod
    def build_listing_url(self, page: int) -> str:
        """Return the URL of the `page`-th listing page (1-indexed)."""

    @abstractmethod
    def extract_page_urls(self, listing_html: str) -> CrawlPageResult:
        """Pull job/company detail URLs out of one listing page's HTML."""

    # --- Shared crawling control flow ---

    async def crawl_job_urls(
        self, known_website_job_ids: set[str] | None = None
    ) -> AsyncIterator[str]:
        """Yield job detail URLs across listing pages, respecting
        `max_pages` and, if `known_website_job_ids` is provided, stopping
        early once pagination has clearly caught up to already-seen jobs
        (Incremental Crawling).

        `known_website_job_ids` contains *website* job IDs (as stored on
        `Job.website_job_id`), not URLs — so subclasses must be able to
        derive one from the other; `website_job_id_from_url()` does that
        and has a sane default implementation most sites don't need to
        override.
        """
        known_ids = known_website_job_ids or set()
        consecutive_all_known_pages = 0

        for page_number in range(1, self.max_pages + 1):
            url = self.build_listing_url(page_number)
            self._logger.info(f"Fetching listing page {page_number}: {url}")
            html = await self.downloader.fetch_html(url)
            self.pages_fetched += 1
            result = self.extract_page_urls(html)

            if not result.job_urls:
                self._logger.info(f"Page {page_number} had no job links; stopping pagination.")
                return

            new_count = 0
            for job_url in result.job_urls:
                website_job_id = self.website_job_id_from_url(job_url)
                if website_job_id not in known_ids:
                    new_count += 1
                yield job_url

            if known_ids:
                if new_count == 0:
                    consecutive_all_known_pages += 1
                else:
                    consecutive_all_known_pages = 0
                if consecutive_all_known_pages >= DEFAULT_INCREMENTAL_STOP_STREAK:
                    self._logger.info(
                        f"Incremental crawl stop: {consecutive_all_known_pages} consecutive "
                        f"pages contained only already-known jobs."
                    )
                    return

    async def fetch_job_html(self, job_url: str) -> str:
        return await self.downloader.fetch_html(job_url)

    async def fetch_company_html(self, company_url: str) -> str:
        return await self.downloader.fetch_html(company_url)

    # --- Default helper, overridable per site ---

    def website_job_id_from_url(self, url: str) -> str:
        """Best-effort extraction of the site's job ID from its detail URL.

        Default implementation takes the last purely-numeric path segment
        (matches JobVision/Jobinja/IranTalent URL conventions observed:
        `.../jobs/1094514/some-slug`). Sites that don't follow this
        convention (e.g. Ponisha's project slugs) override this method.
        """
        segments = [s for s in url.rstrip("/").split("/") if s]
        for segment in reversed(segments):
            if segment.isdigit():
                return segment
        # Fall back to the last path segment verbatim if nothing numeric
        # was found — still a stable, unique-enough key per URL.
        return segments[-1] if segments else url
