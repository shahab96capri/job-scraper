"""
Application entry point: a Typer CLI that wires every layer built so far
into one runnable command.

    python main.py crawl --site jobvision
    python main.py crawl --site jobvision --pages 2 --keyword "برنامه نویس اندروید"
    python main.py crawl --site jobvision --all-categories --pages 3
    python main.py sites

Design decisions:
- **`SITE_REGISTRY` is the single place a new site gets plugged in.**
  Adding Jobinja/IranTalent/IranTalent later means adding one entry here
  (spider factory + parser class + normalizer class) — nothing else in
  this file changes, because everything downstream depends only on the
  `BaseSpider`/`BaseParser`/`BaseNormalizer` abstractions.
- **Export always reads back from the database, not from the crawl run's
  in-memory DTOs.** After `JobIngestionPipeline.run()` persists
  everything, this command re-queries *every* job/company for that source
  (via `list_by_source_with_relations`) and exports that — so JSON/Excel
  always reflect the full current dataset for a source, not just what
  changed in this particular incremental run. This matches the spec's
  "export JSON, export Excel" being listed as whole-run steps, not
  per-job steps.
- **One `get_db_session()` transaction covers ingestion AND the export
  read-back.** Reading back inside the same transaction (before it
  commits) sees this run's own writes without needing a second round
  trip or worrying about read-committed visibility across transactions.
- **Browser + database engine are disposed in a `finally` block**
  regardless of success/failure, so a crawl error never leaves an orphaned
  Chromium process or an open connection pool behind.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

import typer

from app.config.settings import get_settings
from app.core.browser import dispose_browser, new_context
from app.core.exceptions import PlatformError
from app.core.logging import configure_logging, logger
from app.normalizers.base_normalizer import BaseNormalizer
from app.parsers.base_parser import BaseParser
from app.database.session import dispose_engine, get_db_session
from app.dto.company_export_dto import CompanyExportDTO
from app.dto.job_export_dto import JobExportDTO
from app.exporters.excel_exporter import ExcelExporter
from app.exporters.json_exporter import JSONExporter
from app.normalizers.jobvision_normalizer import JobVisionNormalizer
from app.parsers.jobvision_parser import JobVisionParser
from app.pipelines.job_pipeline import JobIngestionPipeline
from app.repositories import CompanyRepository, JobRepository, SourceRepository
from app.spiders.base_spider import BaseSpider
from app.spiders.downloader import Downloader
from app.spiders.jobvision_spider import ALL_CATEGORIES, JobVisionSpider

app = typer.Typer(add_completion=False, help="Iran Job Intelligence Platform")

DEFAULT_MAX_PAGES = 5


@dataclass(frozen=True)
class SiteConfig:
    spider_factory: Callable[[Downloader, int, list[str]], BaseSpider]
    parser_factory: Callable[[], BaseParser]
    normalizer_factory: Callable[[], BaseNormalizer]


SITE_REGISTRY: dict[str, SiteConfig] = {
    "jobvision": SiteConfig(
        spider_factory=lambda downloader, max_pages, keywords: JobVisionSpider(
            downloader, max_pages=max_pages, keywords=keywords
        ),
        parser_factory=JobVisionParser,
        normalizer_factory=JobVisionNormalizer,
    ),
    # Jobinja / IranTalent / Ponisha land here as they're implemented —
    # nothing else in this file needs to change.
}


@app.command()
def sites() -> None:
    """List every site this platform currently knows how to crawl."""
    for code in SITE_REGISTRY:
        typer.echo(code)


@app.command()
def crawl(
    site: str = typer.Option("jobvision", help="Site to crawl. See `python main.py sites`."),
    pages: int = typer.Option(
        DEFAULT_MAX_PAGES, help="Max listing pages to crawl PER category/keyword."
    ),
    keyword: str = typer.Option(
        None, help="Search a single keyword (JobVision only). Ignored if --all-categories is set."
    ),
    all_categories: bool = typer.Option(
        False,
        "--all-categories",
        help=(
            f"Sweep every JobVision job category ({len(ALL_CATEGORIES)} categories) "
            "instead of a single keyword. Much slower — this multiplies total "
            "listing-page fetches by the number of categories."
        ),
    ),
    concurrency: int = typer.Option(
        None,
        "--concurrency",
        help=(
            "How many pages to fetch at once (default from MAX_CONCURRENT_REQUESTS "
            "in .env, normally 5). Worth raising for large --all-categories runs, "
            "which can surface thousands of jobs to fetch — but higher values mean "
            "more simultaneous requests to the target site, so raise gradually."
        ),
    ),
) -> None:
    """Crawl one site end to end: pages -> jobs -> companies -> database
    -> JSON export -> Excel export."""
    if site not in SITE_REGISTRY:
        typer.echo(f"Unknown site {site!r}. Known sites: {', '.join(SITE_REGISTRY)}", err=True)
        raise typer.Exit(code=1)

    if all_categories:
        keywords = ALL_CATEGORIES
    elif keyword:
        keywords = [keyword]
    else:
        keywords = ["برنامه نویس"]

    asyncio.run(_run_crawl(site, pages, keywords, concurrency))


async def _run_crawl(
    site: str, pages: int, keywords: list[str], concurrency: int | None
) -> None:
    configure_logging()
    settings = get_settings()
    config = SITE_REGISTRY[site]
    run_logger = logger.bind(component="main")

    try:
        context = await new_context()
    except Exception as exc:  # noqa: BLE001
        run_logger.error(
            f"Could not launch the browser: {exc}. "
            f"Have you run `playwright install chromium`?"
        )
        raise typer.Exit(code=1) from exc

    try:
        downloader = Downloader(
            context,
            timeout_ms=settings.playwright_timeout_ms,
            max_retries=settings.max_retries,
            backoff_seconds=settings.retry_backoff_seconds,
        )
        spider = config.spider_factory(downloader, pages, keywords)
        parser = config.parser_factory()
        normalizer = config.normalizer_factory()

        async with get_db_session() as session:
            pipeline = JobIngestionPipeline(
                session,
                spider=spider,
                parser=parser,
                normalizer=normalizer,
                max_concurrent_requests=concurrency,
            )
            run = await pipeline.run()

            source_repo = SourceRepository(session)
            source = await source_repo.get_by_code(site)

            job_export_dtos: list[JobExportDTO] = []
            company_export_dtos: list[CompanyExportDTO] = []
            if source is not None:
                job_repo = JobRepository(session)
                company_repo = CompanyRepository(session)
                jobs_orm = await job_repo.list_by_source_with_relations(source.id)
                companies_orm = await company_repo.list_by_source_with_relations(source.id)
                job_export_dtos = [JobExportDTO.from_orm_job(j) for j in jobs_orm]
                company_export_dtos = [
                    CompanyExportDTO.from_orm_company(c) for c in companies_orm
                ]

        json_path = JSONExporter(settings.output_json_path).export(
            job_export_dtos, company_export_dtos, source_code=site
        )
        excel_path = ExcelExporter(settings.output_excel_path).export(
            job_export_dtos, company_export_dtos, source_code=site
        )

        run_logger.info(
            f"Run complete | status={run.status.value} jobs_found={run.jobs_found} "
            f"created={run.jobs_created} updated={run.jobs_updated} "
            f"errors={run.error_count} | exported {len(job_export_dtos)} job(s), "
            f"{len(company_export_dtos)} compan(y/ies)"
        )
        typer.echo(f"JSON:  {json_path}")
        typer.echo(f"Excel: {excel_path}")

    except PlatformError as exc:
        run_logger.error(f"Crawl failed: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        await context.close()
        await dispose_browser()
        await dispose_engine()


if __name__ == "__main__":
    app()
