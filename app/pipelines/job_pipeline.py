"""
`JobIngestionPipeline` — orchestrates one full crawl run for a single
source, wiring together every layer built so far:

    Spider -> Downloader -> Parser -> Normalizer -> Validator
           -> Repositories -> Database

Design decisions:
- **Depends only on abstractions** (`BaseSpider`, `BaseParser`,
  `BaseNormalizer`) injected through the constructor — Dependency
  Injection / Dependency Inversion. This class is fully written and
  testable (Commit 3) before a single concrete site implementation
  (Commit 4) exists; the integration test in this commit proves it with
  fakes.
- **One `AsyncSession` / one transaction for the whole run.** The pipeline
  receives a session (via `get_db_session()` in `main.py`, Commit 5) and
  constructs every repository against it, so a crash mid-run rolls back
  cleanly instead of leaving half a crawl committed.
- **Per-job error isolation**: a failure parsing/normalizing/validating/
  persisting *one* job is caught, logged to the `Error` table via
  `ErrorRepository`, and the loop continues — one broken selector must
  not lose an entire run's worth of otherwise-good data. A failure in the
  Spider's *pagination* itself (can't even fetch a listing page) is
  allowed to propagate, since without a listing page there is nothing
  left to iterate.
- **Duplicate/Update Detection** is delegated entirely to
  `CompanyRepository.upsert()` / `JobRepository.upsert()` (Commit 2); this
  class only counts `created` vs not to populate `ScrapeHistory`.
- **Incremental Crawling**: `list_website_job_ids_by_source()` is read
  once up front and handed to the spider, which uses it to stop
  paginating once it's clearly caught up (see `BaseSpider.crawl_job_urls`).
- **Company resolution** prefers a full company-page crawl
  (`raw_company_url`, if the Parser found one) over a name-only fallback,
  matching the spec's "crawl company pages, extract company information"
  requirement — but degrades gracefully to a name-only `Company` row
  (still linked, just thin) if no company URL was extractable, rather
  than failing the whole job.
"""

from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.config.settings import get_settings
from app.core.exceptions import PlatformError
from app.core.logging import logger
from app.dto.company_dto import CompanyDTO
from app.dto.raw_dto import RawJobDTO
from app.models.enums import ScrapeStatus
from app.models.error import ErrorStageEnum
from app.models.scrape_history import ScrapeHistory
from app.normalizers.base_normalizer import BaseNormalizer
from app.parsers.base_parser import BaseParser
from app.repositories import (
    CategoryRepository,
    CompanyRepository,
    EmploymentTypeRepository,
    ErrorRepository,
    JobRepository,
    LocationRepository,
    ScrapeHistoryRepository,
    SkillRepository,
    SourceRepository,
)
from app.spiders.base_spider import BaseSpider
from app.validators.company_validator import CompanyValidator
from app.validators.job_validator import JobValidator

# Exception -> Error.stage mapping, in the same order as the architecture's
# Spider -> Parser -> Normalizer -> Validator -> Repository pipeline.
_STAGE_BY_EXCEPTION_PREFIX: dict[str, ErrorStageEnum] = {
    "CrawlError": ErrorStageEnum.CRAWL,
    "TransientCrawlError": ErrorStageEnum.CRAWL,
    "PermanentCrawlError": ErrorStageEnum.CRAWL,
    "RateLimitedError": ErrorStageEnum.CRAWL,
    "ParsingError": ErrorStageEnum.PARSE,
    "NormalizationError": ErrorStageEnum.NORMALIZE,
    "ValidationFailedError": ErrorStageEnum.VALIDATE,
    "RepositoryError": ErrorStageEnum.PERSIST,
    "EntityNotFoundError": ErrorStageEnum.PERSIST,
    "DuplicateEntityError": ErrorStageEnum.PERSIST,
}


def _stage_for_exception(exc: Exception) -> ErrorStageEnum:
    return _STAGE_BY_EXCEPTION_PREFIX.get(type(exc).__name__, ErrorStageEnum.PERSIST)


class JobIngestionPipeline:
    def __init__(
        self,
        session,
        *,
        spider: BaseSpider,
        parser: BaseParser,
        normalizer: BaseNormalizer,
        job_validator: JobValidator | None = None,
        company_validator: CompanyValidator | None = None,
        max_concurrent_requests: int | None = None,
    ) -> None:
        self.spider = spider
        self.parser = parser
        self.normalizer = normalizer
        self.job_validator = job_validator or JobValidator()
        self.company_validator = company_validator or CompanyValidator()
        self.max_concurrent_requests = (
            max_concurrent_requests
            if max_concurrent_requests is not None
            else get_settings().max_concurrent_requests
        )

        self.source_repo = SourceRepository(session)
        self.location_repo = LocationRepository(session)
        self.category_repo = CategoryRepository(session)
        self.employment_type_repo = EmploymentTypeRepository(session)
        self.skill_repo = SkillRepository(session)
        self.company_repo = CompanyRepository(session)
        self.job_repo = JobRepository(session)
        self.history_repo = ScrapeHistoryRepository(session)
        self.error_repo = ErrorRepository(session)

        self._logger = logger.bind(component=f"pipelines.job_ingestion.{spider.SITE_CODE}")

    async def run(self) -> ScrapeHistory:
        source = await self.source_repo.get_or_create(
            code=self.spider.SITE_CODE, name=self.spider.SITE_NAME, base_url=self.spider.BASE_URL
        )
        run = await self.history_repo.start_run(source.id)
        self._logger.info(f"Scrape run started: {run.id}")

        known_ids = await self.job_repo.list_website_job_ids_by_source(source.id)
        self._logger.info(f"{len(known_ids)} known job(s) for incremental crawl comparison")

        jobs_found = jobs_created = jobs_updated = jobs_skipped_duplicate = 0
        companies_created = companies_updated = 0
        error_count = 0

        try:
            # Listing pages still have to be fetched one after another —
            # each page's URL depends on knowing we haven't hit
            # `max_pages`/the incremental-stop condition yet, so this part
            # is inherently sequential. It's also cheap: a handful of pages
            # vs. dozens of job/company detail pages, which is where almost
            # all the crawl time actually goes.
            job_urls = [url async for url in self.spider.crawl_job_urls(known_ids)]
            jobs_found = len(job_urls)

            # --- Phase 1: fetch every job detail page CONCURRENTLY -------
            # Previously each job page was fetched one at a time, so total
            # time scaled linearly with job count. Fetching several at once
            # (bounded by `max_concurrent_requests` open browser tabs) is
            # the single biggest lever for crawl speed.
            job_html_by_url = await self._fetch_many(job_urls, self.spider.fetch_job_html)

            # --- Phase 2: parse each fetched job page (pure CPU, no
            # network) and collect the *unique* company URLs referenced. --
            parsed_by_url: dict[str, RawJobDTO] = {}
            for job_url, html_or_exc in job_html_by_url.items():
                if isinstance(html_or_exc, Exception):
                    error_count += 1
                    await self._record_error(html_or_exc, source_id=source.id, url=job_url)
                    continue
                try:
                    parsed_by_url[job_url] = self.parser.parse_job_page(html_or_exc, source_url=job_url)
                except Exception as exc:  # noqa: BLE001 - isolated per job, same as before
                    error_count += 1
                    await self._record_error(exc, source_id=source.id, url=job_url)

            # --- Phase 3: fetch every *unique* company page CONCURRENTLY -
            # Multiple jobs from the same employer used to trigger a full,
            # separate re-download of that employer's company page for
            # every single job — pure wasted work. Deduplicating by URL
            # before fetching means each company page is downloaded once
            # per crawl, no matter how many jobs link to it.
            unique_company_urls = list(
                {raw.raw_company_url for raw in parsed_by_url.values() if raw.raw_company_url}
            )
            company_html_by_url = await self._fetch_many(
                unique_company_urls, self.spider.fetch_company_html
            )

            # --- Phase 3.5: bonus jobs discovered via company pages ------
            # The normal keyword/category search only ever returns ACTIVE
            # postings. Every company page, though, already embeds that
            # company's own job list — active AND expired, each flagged
            # (`JobVisionParser.parse_company_job_posts`) — and we already
            # downloaded that page in Phase 3, so reading it costs nothing
            # extra. For each job discovered this way that Phase 1/2 didn't
            # already cover, we *try* to fetch its own detail page for the
            # full data (description, requirements, etc.) — but expired
            # postings often don't render normally, so a failure here is
            # expected and non-fatal: we keep the summary data (title,
            # category, salary, dates, ...) already in hand instead of
            # dropping the job entirely.
            parse_company_jobs = getattr(self.parser, "parse_company_job_posts", None)
            job_url_from_id = getattr(self.spider, "job_url_from_id", None)
            if parse_company_jobs and job_url_from_id:
                already_covered_ids = {
                    raw.website_job_id for raw in parsed_by_url.values() if raw.website_job_id
                }
                bonus_by_job_id: dict[str, RawJobDTO] = {}
                for company_url, html_or_exc in company_html_by_url.items():
                    if isinstance(html_or_exc, Exception):
                        continue
                    try:
                        for raw in parse_company_jobs(html_or_exc, source_url=company_url):
                            if not raw.website_job_id or raw.website_job_id in already_covered_ids:
                                continue
                            bonus_by_job_id[raw.website_job_id] = raw
                    except Exception as exc:  # noqa: BLE001 - a malformed bonus payload
                        # shouldn't ever cost us the jobs we already have.
                        self._logger.warning(f"Could not read bonus job list from {company_url}: {exc}")

                if bonus_by_job_id:
                    self._logger.info(
                        f"Found {len(bonus_by_job_id)} additional job(s) via company pages "
                        f"(includes expired postings not visible in normal search)"
                    )
                    candidate_url_by_job_id = {
                        job_id: job_url_from_id(job_id) for job_id in bonus_by_job_id
                    }
                    bonus_html_by_url = await self._fetch_many(
                        list(candidate_url_by_job_id.values()), self.spider.fetch_job_html
                    )
                    for job_id, summary_raw in bonus_by_job_id.items():
                        candidate_url = candidate_url_by_job_id[job_id]
                        bonus_html_or_exc = bonus_html_by_url.get(candidate_url)
                        if isinstance(bonus_html_or_exc, Exception) or bonus_html_or_exc is None:
                            self._logger.info(
                                f"Bonus job {job_id}'s own page didn't load "
                                f"(expected for expired postings) — keeping summary data."
                            )
                            parsed_by_url[candidate_url] = summary_raw.model_copy(
                                update={"source_url": candidate_url}
                            )
                            continue
                        try:
                            parsed_by_url[candidate_url] = self.parser.parse_job_page(
                                bonus_html_or_exc, source_url=candidate_url
                            )
                        except Exception:  # noqa: BLE001 - same graceful fallback
                            self._logger.info(
                                f"Bonus job {job_id}'s own page didn't parse "
                                f"(expected for expired postings) — keeping summary data."
                            )
                            parsed_by_url[candidate_url] = summary_raw.model_copy(
                                update={"source_url": candidate_url}
                            )
                    job_urls = job_urls + list(candidate_url_by_job_id.values())
                    jobs_found = len(job_urls)

            # --- Phase 4: normalize/validate/persist SEQUENTIALLY --------
            # Everything from here on touches the shared database session,
            # which (like the original code) must stay single-threaded —
            # but it no longer waits on the network at all, since every
            # page it needs was already downloaded in phases 1-3.
            for job_url in job_urls:
                raw_job = parsed_by_url.get(job_url)
                if raw_job is None:
                    continue  # already recorded as an error above
                try:
                    created, was_new_company = await self._process_parsed_job(
                        job_url, raw_job, company_html_by_url, source_id=source.id
                    )
                    if created:
                        jobs_created += 1
                    else:
                        jobs_updated += 1
                    if was_new_company is True:
                        companies_created += 1
                    elif was_new_company is False:
                        companies_updated += 1
                except PlatformError as exc:
                    error_count += 1
                    await self._record_error(exc, source_id=source.id, url=job_url)
                except Exception as exc:  # noqa: BLE001 - last-resort isolation per job
                    error_count += 1
                    await self._record_error(exc, source_id=source.id, url=job_url)
        finally:
            status = self._determine_status(jobs_found, error_count)
            await self.history_repo.finish_run(
                run,
                status=status,
                pages_crawled=self.spider.pages_fetched,
                jobs_found=jobs_found,
                jobs_created=jobs_created,
                jobs_updated=jobs_updated,
                jobs_skipped_duplicate=jobs_skipped_duplicate,
                companies_created=companies_created,
                companies_updated=companies_updated,
                retry_count=self.spider.downloader.retry_count,
                error_count=error_count,
            )
            self._logger.info(
                f"Scrape run finished: status={status.value} jobs_found={jobs_found} "
                f"created={jobs_created} updated={jobs_updated} errors={error_count}"
            )

        return run

    @staticmethod
    def _determine_status(jobs_found: int, error_count: int) -> ScrapeStatus:
        if jobs_found == 0 and error_count > 0:
            return ScrapeStatus.FAILED
        if error_count > 0:
            return ScrapeStatus.PARTIAL_SUCCESS
        return ScrapeStatus.SUCCESS

    async def _fetch_many(
        self, urls: list[str], fetch_fn: Callable[[str], Awaitable[str]]
    ) -> dict[str, str | Exception]:
        """Fetch several URLs at once, capped at `self.max_concurrent_requests`
        simultaneous requests. A failure on one URL is captured and returned
        alongside the successes (never raised) so one bad page can never take
        down the rest of the batch — the caller decides what to do with each
        result, same error-isolation guarantee the old one-at-a-time loop had.
        """
        if not urls:
            return {}

        semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        async def _bounded_fetch(url: str) -> tuple[str, str | Exception]:
            async with semaphore:
                try:
                    return url, await fetch_fn(url)
                except Exception as exc:  # noqa: BLE001 - classified by the caller
                    return url, exc

        results = await asyncio.gather(*(_bounded_fetch(url) for url in urls))
        return dict(results)

    async def _process_parsed_job(
        self,
        job_url: str,
        raw_job: RawJobDTO,
        company_html_by_url: dict[str, str | Exception],
        *,
        source_id: uuid.UUID,
    ) -> tuple[bool, bool | None]:
        """Persist one already-fetched-and-parsed job. Returns `(job_created,
        company_created)` — `company_created` is `None` if no company could
        be resolved at all."""
        if not raw_job.website_job_id:
            raw_job = raw_job.model_copy(
                update={"website_job_id": self.spider.website_job_id_from_url(job_url)}
            )

        job_dto = self.normalizer.normalize_job(raw_job)
        job_dto = self.job_validator.validate(job_dto)

        company_id, company_created = await self._resolve_company(
            raw_job.raw_company_url, job_dto.company_name, company_html_by_url, source_id=source_id
        )

        location = await self.location_repo.get_or_create(job_dto.province, job_dto.city)
        category = await self.category_repo.get_or_create(job_dto.category_name)
        sub_category = await self.category_repo.get_or_create(
            job_dto.sub_category_name, parent_id=category.id if category else None
        )
        employment_type = None
        if job_dto.employment_type_code:
            employment_type = await self.employment_type_repo.get_or_create(
                code=job_dto.employment_type_code
            )

        job, job_created = await self.job_repo.upsert(
            job_dto,
            source_id=source_id,
            company_id=company_id,
            location_id=location.id if location else None,
            category_id=category.id if category else None,
            sub_category_id=sub_category.id if sub_category else None,
            employment_type_id=employment_type.id if employment_type else None,
        )

        if job_dto.skills:
            skills = await self.skill_repo.get_or_create_many(job_dto.skills)
            await self.job_repo.sync_skills(
                job, [(s.id, True, None, 1) for s in skills]
            )

        return job_created, company_created

    async def _resolve_company(
        self,
        raw_company_url: str | None,
        company_name: str | None,
        company_html_by_url: dict[str, str | Exception],
        *,
        source_id: uuid.UUID,
    ) -> tuple[uuid.UUID | None, bool | None]:
        if raw_company_url:
            html_or_exc = company_html_by_url.get(raw_company_url)
            if isinstance(html_or_exc, Exception):
                self._logger.warning(
                    f"Company page crawl failed for {raw_company_url}, falling back to "
                    f"name-only company record: {html_or_exc}"
                )
                await self._record_error(html_or_exc, source_id=source_id, url=raw_company_url)
            elif html_or_exc is not None:
                try:
                    raw_company = self.parser.parse_company_page(html_or_exc, source_url=raw_company_url)
                    company_dto = self.normalizer.normalize_company(raw_company)
                    company_dto = self.company_validator.validate(company_dto)
                    location = await self.location_repo.get_or_create(
                        company_dto.province, company_dto.city
                    )
                    company, created = await self.company_repo.upsert(
                        company_dto, source_id=source_id, location_id=location.id if location else None
                    )
                    return company.id, created
                except PlatformError as exc:
                    self._logger.warning(
                        f"Company page parsing failed for {raw_company_url}, falling back to "
                        f"name-only company record: {exc}"
                    )
                    await self._record_error(exc, source_id=source_id, url=raw_company_url)

        if company_name:
            existing = await self.company_repo.get_by_source_and_name(source_id, company_name)
            if existing is not None:
                return existing.id, False
            minimal_dto = CompanyDTO(
                source_code=self.spider.SITE_CODE,
                source_url=self.spider.BASE_URL,
                name=company_name,
                scraped_at=datetime.now(timezone.utc),
            )
            company, created = await self.company_repo.upsert(
                minimal_dto, source_id=source_id, location_id=None
            )
            return company.id, created

        return None, None

    async def _record_error(
        self, exc: Exception, *, source_id: uuid.UUID, url: str | None
    ) -> None:
        stage = _stage_for_exception(exc)
        field_errors = getattr(exc, "field_errors", None)
        message = str(exc)
        if field_errors:
            message = f"{message} | fields: {'; '.join(field_errors)}"

        self._logger.error(f"[{stage.value}] {url}: {message}")
        await self.error_repo.create(
            stage=stage,
            error_type=type(exc).__name__,
            message=message,
            url=url,
            traceback="".join(traceback.format_exception(exc)),
            source_id=source_id,
        )
