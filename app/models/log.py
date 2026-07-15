"""
`Log` stores structured, queryable application events in the database,
complementing (not replacing) the Loguru file sinks configured in
`app/core/logging.py`.

Rationale for having both: file logs (via Loguru) are the fast, always-on
record used for live debugging/tailing. DB logs are a deliberately
*smaller*, curated subset — significant lifecycle events (scrape started/
finished, pipeline stage summaries) — that need to be queryable with SQL
and joined against `ScrapeHistory` / `Source`, e.g. for a future admin
dashboard. Every HTTP/parse failure does NOT get written here; that belongs
in `Error` (and the file logs), keeping this table small and fast to query.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LogLevel

if TYPE_CHECKING:
    from app.models.source import Source


class Log(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "logs"

    level: Mapped[LogLevel] = mapped_column(
        SAEnum(LogLevel, name="log_level_enum"), default=LogLevel.INFO, nullable=False
    )
    component: Mapped[str] = mapped_column(String(150), nullable=False)
    """Dotted component path, e.g. 'pipelines.job_pipeline'."""
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    """Arbitrary structured context (job_id, url, page number, etc.)."""

    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[Optional["Source"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Log level={self.level} component={self.component!r}>"
