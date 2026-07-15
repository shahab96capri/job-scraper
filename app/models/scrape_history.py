"""
`ScrapeHistory` records one crawl run per source and is the backbone of
two spec-required features:

- **Incremental Crawling**: the pipeline reads the most recent successful
  `ScrapeHistory.finished_at` for a source and only processes jobs
  published/updated after that timestamp, instead of re-crawling
  everything on every run.
- **Retry System observability**: `retry_count` / `error_count` let
  operators see, per run, how much the retry system had to compensate
  for transient failures, without grepping log files.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ScrapeStatus

if TYPE_CHECKING:
    from app.models.source import Source


class ScrapeHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scrape_history"

    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[ScrapeStatus] = mapped_column(
        SAEnum(ScrapeStatus, name="scrape_status_enum"),
        default=ScrapeStatus.RUNNING,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    pages_crawled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_skipped_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    companies_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    companies_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source: Mapped["Source"] = relationship(back_populates="scrape_history")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ScrapeHistory source_id={self.source_id} status={self.status}>"
