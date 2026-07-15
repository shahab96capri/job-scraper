"""
`JobVisionSpider` — verified against a real, rendered listing page
(`jobvision.ir/jobs/keyword/برنامه نویس`, 30 results, `pageSize=30`,
provided by the user).

**Listing page finding**: unlike job-detail/company-profile pages (see
`JobVisionParser`'s docstring), the listing page's embedded `ng-state`
JSON does NOT contain the full 30-job result set — only a single job's
detail (whichever is shown in the desktop split-view detail pane). The
job list itself is rendered from `<job-card>` custom elements, each
wrapping an `<a class="... desktop-job-card" href="/jobs/{id}/{slug}?
...">`. `extract_page_urls` therefore uses BeautifulSoup against that
verified structure, not JSON extraction.

**Pagination — VERIFIED by the user directly** (2026-07-14): navigating to
`.../jobs/keyword/{keyword}?page=1` vs `...?page=2` in a real browser
produces different result sets; the URL bar genuinely updates, confirming
this is real server-aware pagination and not purely client-side routing
(the pagination *control itself* still renders `href=""` with a `(click)`
handler in the static HTML — Angular intercepts the click and pushes a new
URL via its router, which the server also honors on direct navigation/
reload). An optional `sort=1` query parameter was also observed
alongside `page` in the confirmed URL; not yet understood (default sort
order vs an explicit one) and left unset here — safe to add later if a
specific sort order becomes important.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.spiders.base_spider import BaseSpider, CrawlPageResult

BASE_URL = "https://jobvision.ir"
JOB_CARD_SELECTOR = "a.desktop-job-card"
COMPANY_LINK_SELECTOR = 'a[href^="/companies/"]'


def _strip_query(url: str) -> str:
    """Drop tracking/query params (`row`, `searchId`, `score`, ...) so the
    same job always yields the same canonical `source_url` across crawls,
    independent of its position in that particular search result."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query="", fragment=""))


class JobVisionSpider(BaseSpider):
    SITE_CODE = "jobvision"
    SITE_NAME = "JobVision"
    BASE_URL = BASE_URL

    def __init__(self, downloader, *, max_pages: int, keyword: str = "برنامه نویس") -> None:
        super().__init__(downloader, max_pages=max_pages)
        self.keyword = keyword

    def build_listing_url(self, page: int) -> str:
        # VERIFIED (2026-07-14): confirmed by direct browser navigation —
        # `?page=1` vs `?page=2` on this exact URL shape returns different
        # job listings. `keyword` matches the sample fixture's own
        # canonical URL structure (`/jobs/keyword/{keyword}`).
        return f"{BASE_URL}/jobs/keyword/{self.keyword}?page={page}"

    def extract_page_urls(self, listing_html: str) -> CrawlPageResult:
        soup = BeautifulSoup(listing_html, "html.parser")

        job_urls: list[str] = []
        for anchor in soup.select(JOB_CARD_SELECTOR):
            href = anchor.get("href")
            if not href:
                continue
            job_urls.append(_strip_query(urljoin(BASE_URL, href)))

        company_urls: list[str] = []
        for anchor in soup.select(COMPANY_LINK_SELECTOR):
            href = anchor.get("href")
            if not href:
                continue
            company_urls.append(_strip_query(urljoin(BASE_URL, href)))

        # Preserve order, drop duplicates (a company can appear on
        # multiple job cards within the same listing page).
        job_urls = list(dict.fromkeys(job_urls))
        company_urls = list(dict.fromkeys(company_urls))

        return CrawlPageResult(job_urls=job_urls, company_urls=company_urls)
