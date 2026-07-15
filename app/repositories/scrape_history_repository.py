"""
`ScrapeHistoryRepository` — manages the `scrape_history` table.

`get_last_successful_run()` is what the Incremental Crawling feature
(Commit 3) is built on: the pipeline reads this before starting a new
crawl to decide whether it can skip pages of already-seen, unchanged job
postings instead of re-crawling a source from page 1 every single run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.enums import ScrapeStatus
from app.models.scrape_history import ScrapeHistory
from app.repositories.base_repository import BaseRepository


class ScrapeHistoryRepository(BaseRepository[ScrapeHistory]):
    model = ScrapeHistory

    async def start_run(self, source_id: uuid.UUID) -> ScrapeHistory:
        run = ScrapeHistory(
            source_id=source_id,
            status=ScrapeStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        return await self.add(run)

    async def finish_run(
        self,
        run: ScrapeHistory,
        *,
        status: ScrapeStatus,
        pages_crawled: int = 0,
        jobs_found: int = 0,
        jobs_created: int = 0,
        jobs_updated: int = 0,
        jobs_skipped_duplicate: int = 0,
        companies_created: int = 0,
        companies_updated: int = 0,
        retry_count: int = 0,
        error_count: int = 0,
    ) -> ScrapeHistory:
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.pages_crawled = pages_crawled
        run.jobs_found = jobs_found
        run.jobs_created = jobs_created
        run.jobs_updated = jobs_updated
        run.jobs_skipped_duplicate = jobs_skipped_duplicate
        run.companies_created = companies_created
        run.companies_updated = companies_updated
        run.retry_count = retry_count
        run.error_count = error_count
        await self.session.flush()
        return run

    async def get_last_successful_run(self, source_id: uuid.UUID) -> ScrapeHistory | None:
        stmt = (
            select(ScrapeHistory)
            .where(
                ScrapeHistory.source_id == source_id,
                ScrapeHistory.status == ScrapeStatus.SUCCESS,
            )
            .order_by(ScrapeHistory.finished_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
