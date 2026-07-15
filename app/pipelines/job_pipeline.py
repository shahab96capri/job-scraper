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

import traceback
import uuid
from datetime import datetime, timezone

from app.core.exceptions import PlatformError
from app.core.logging import logger
from app.dto.company_dto import CompanyDTO
from app.models.enums import ScrapeStatus
from app.models.error import ErrorStageEnum
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
    ) -> None:
        self.spider = spider
        self.parser = parser
        self.normalizer = normalizer
        self.job_validator = job_validator or JobValidator()
        self.company_validator = company_validator or CompanyValidator()

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

    async def run(self):
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
            async for job_url in self.spider.crawl_job_urls(known_ids):
                jobs_found += 1
                try:
                    created, was_new_company = await self._process_job(job_url, source_id=source.id)
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

    async def _process_job(self, job_url: str, *, source_id: uuid.UUID) -> tuple[bool, bool | None]:
        """Process one job URL end to end. Returns `(job_created,
        company_created)` — `company_created` is `None` if no company
        could be resolved at all."""
        html = await self.spider.fetch_job_html(job_url)
        raw_job = self.parser.parse_job_page(html, source_url=job_url)

        if not raw_job.website_job_id:
            raw_job = raw_job.model_copy(
                update={"website_job_id": self.spider.website_job_id_from_url(job_url)}
            )

        job_dto = self.normalizer.normalize_job(raw_job)
        job_dto = self.job_validator.validate(job_dto)

        company_id, company_created = await self._resolve_company(
            raw_job.raw_company_url, job_dto.company_name, source_id=source_id
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
        self, raw_company_url: str | None, company_name: str | None, *, source_id: uuid.UUID
    ) -> tuple[uuid.UUID | None, bool | None]:
        if raw_company_url:
            try:
                html = await self.spider.fetch_company_html(raw_company_url)
                raw_company = self.parser.parse_company_page(html, source_url=raw_company_url)
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
                    f"Company page crawl failed for {raw_company_url}, falling back to "
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
