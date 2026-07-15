"""
Integration test for `JobIngestionPipeline` (Commit 3).

Uses fake `BaseSpider` / `BaseParser` / `BaseNormalizer` implementations
(in-memory fixture data, no real HTTP/browser) against the real
PostgreSQL database — this is exactly what Dependency Injection buys us:
the full Spider->...->Repository orchestration is provable *before*
Commit 4 writes a single real site's Parser/Normalizer.

What this test does NOT prove: that a real site's HTML can actually be
parsed, or that a real browser gets past that site's bot detection. That
requires Commit 4's concrete parsers and a real Chromium binary
respectively (the sandbox this was authored in cannot download Chromium —
network egress restricted to package registries).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest

from app.database.session import get_db_session
from app.dto.company_dto import CompanyDTO
from app.dto.job_dto import JobDTO
from app.dto.raw_dto import RawCompanyDTO, RawJobDTO
from app.models.enums import CompanySize, JobStatus, ScrapeStatus, WorkMode
from app.normalizers.base_normalizer import BaseNormalizer
from app.parsers.base_parser import BaseParser
from app.pipelines.job_pipeline import JobIngestionPipeline
from app.repositories import CompanyRepository, JobRepository, SourceRepository
from app.spiders.base_spider import BaseSpider, CrawlPageResult
from app.spiders.downloader import Downloader

pytestmark = pytest.mark.asyncio


# --- Fixture "site": three jobs across two listing pages, one broken. ---

_FIXTURE_JOBS = {
    "https://fixture.test/jobs/1": {"id": "1", "title": "Backend Developer", "broken": False},
    "https://fixture.test/jobs/2": {"id": "2", "title": "Frontend Developer", "broken": False},
    "https://fixture.test/jobs/3": {"id": "3", "title": "", "broken": True},  # fails validation
}
_FIXTURE_COMPANY_URL = "https://fixture.test/companies/nova"


class _FakeDownloader(Downloader):
    """Bypasses real HTTP/browser entirely: `fetch_html` looks up
    canned HTML by URL from an in-memory fixture instead of navigating."""

    def __init__(self) -> None:
        # Intentionally do not call super().__init__ — no real
        # BrowserContext exists in this test.
        self._retry_count = 0

    async def fetch_html(self, url: str) -> str:  # type: ignore[override]
        if url == _FIXTURE_COMPANY_URL:
            return "<html>company page</html>"
        if url in _FIXTURE_JOBS:
            return f"<html>job page for {url}</html>"
        raise AssertionError(f"unexpected URL requested in fixture: {url}")


class _FakeSpider(BaseSpider):
    SITE_CODE = "fixture_site"
    SITE_NAME = "Fixture Site"
    BASE_URL = "https://fixture.test"

    def build_listing_url(self, page: int) -> str:
        return f"https://fixture.test/jobs?page={page}"

    def extract_page_urls(self, listing_html: str) -> CrawlPageResult:
        # Not actually exercised: `crawl_job_urls` is overridden below to
        # yield the fixture directly, since this fixture "site" needs no
        # real pagination HTTP round-trip. Still implemented (rather than
        # left `raise NotImplementedError`) to keep this a concrete,
        # instantiable `BaseSpider` subclass.
        return CrawlPageResult(job_urls=list(_FIXTURE_JOBS.keys()), company_urls=[])

    async def crawl_job_urls(self, known_website_job_ids=None) -> AsyncIterator[str]:  # type: ignore[override]
        # Simplified for the fixture: yield once, no real pagination HTTP
        # calls needed (still exercises the Pipeline's consumption side).
        self.pages_fetched = 1
        for url in _FIXTURE_JOBS:
            yield url


class _FakeParser(BaseParser):
    SITE_CODE = "fixture_site"

    def parse_job_page(self, html: str, *, source_url: str) -> RawJobDTO:
        fixture = _FIXTURE_JOBS[source_url]
        return RawJobDTO(
            source_code=self.SITE_CODE,
            website_job_id=fixture["id"],
            source_url=source_url,
            raw_title=fixture["title"],
            raw_company_name="نواویژن",
            raw_company_url=_FIXTURE_COMPANY_URL if fixture["id"] == "1" else None,
            raw_work_mode="دورکاری",
            raw_skills=["Django", "PostgreSQL"],
        )

    def parse_company_page(self, html: str, *, source_url: str) -> RawCompanyDTO:
        return RawCompanyDTO(
            source_code=self.SITE_CODE,
            website_company_id="nova",
            source_url=source_url,
            raw_name="نواویژن",
            raw_company_size="11-50",
        )


class _FakeNormalizer(BaseNormalizer):
    SITE_CODE = "fixture_site"

    def normalize_job(self, raw: RawJobDTO) -> JobDTO:
        return JobDTO(
            source_code=raw.source_code,
            website_job_id=raw.website_job_id,
            source_url=raw.source_url,
            title=raw.raw_title or "",
            company_name=raw.raw_company_name,
            work_mode=WorkMode.REMOTE if raw.raw_work_mode == "دورکاری" else WorkMode.UNKNOWN,
            skills=raw.raw_skills,
            status=JobStatus.ACTIVE,
            scraped_at=datetime.now(timezone.utc),
        )

    def normalize_company(self, raw: RawCompanyDTO) -> CompanyDTO:
        return CompanyDTO(
            source_code=raw.source_code,
            website_company_id=raw.website_company_id,
            source_url=raw.source_url,
            name=raw.raw_name or "",
            company_size=CompanySize.SIZE_11_50,
            scraped_at=datetime.now(timezone.utc),
        )


async def test_pipeline_end_to_end_with_fake_spider_against_real_postgres():
    # A fresh, random SITE_CODE per test invocation keeps this test
    # correct and idempotent regardless of leftover data from previous
    # runs against the same persistent PostgreSQL instance (unlike a
    # throwaway/ephemeral test database, rows here outlive a single `pytest`
    # invocation).
    site_code = f"fixture_site_{uuid.uuid4().hex[:8]}"

    async with get_db_session() as session:
        spider = _FakeSpider(_FakeDownloader(), max_pages=1)
        spider.SITE_CODE = site_code  # instance override, see class docstring
        pipeline = JobIngestionPipeline(
            session,
            spider=spider,
            parser=_FakeParser(),
            normalizer=_FakeNormalizer(),
        )

        run = await pipeline.run()

        # 2 of 3 fixture jobs are valid; the third has an empty title and
        # must fail JobValidator without aborting the whole run.
        assert run.jobs_found == 3
        assert run.jobs_created == 2
        assert run.error_count == 1
        assert run.status == ScrapeStatus.PARTIAL_SUCCESS
        assert run.pages_crawled == 1

        source_repo = SourceRepository(session)
        source = await source_repo.get_by_code(site_code)
        assert source is not None

        job_repo = JobRepository(session)
        job1 = await job_repo.get_by_source_and_website_id(source.id, "1")
        assert job1 is not None
        assert job1.title == "Backend Developer"
        assert job1.work_mode == WorkMode.REMOTE

        job3 = await job_repo.get_by_source_and_website_id(source.id, "3")
        assert job3 is None  # failed validation, never persisted

        company_repo = CompanyRepository(session)
        company = await company_repo.get_by_source_and_website_id(source.id, "nova")
        assert company is not None
        assert company.name == "نواویژن"

        # job 1 got the fully-crawled company (via raw_company_url); job 2
        # has no company URL in the fixture, so it falls back to a
        # name-only company lookup and links to the SAME company row
        # (get_by_source_and_name), not a duplicate.
        job2 = await job_repo.get_by_source_and_website_id(source.id, "2")
        assert job2.company_id == company.id

        # Re-running the pipeline against unchanged fixture data must be a
        # pure update pass: no new jobs/companies, everything updated.
        run2 = await pipeline.run()
        assert run2.jobs_created == 0
        assert run2.jobs_updated == 2
