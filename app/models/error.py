"""
`Error` stores every failure that survived the retry system (Commit 3):
crawl failures that exhausted retries, parsing failures, validation
failures. This is the concrete "Errors" entity from the spec and is what
lets a future operator answer "which URLs need a selector fix?" with a
single query instead of grepping `errors.log`.

Distinct from `Log`: `Log` is for informational/operational events,
`Error` is exclusively for failures tied to a specific pipeline stage and
(usually) a specific URL, and includes a `resolved` flag so the same
structural failure isn't re-reported forever once a selector is fixed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.source import Source


import enum


class ErrorStageEnum(str, enum.Enum):
    """Identifies which pipeline stage produced the error: Spider/Downloader
    (CRAWL), Parser (PARSE), Normalizer (NORMALIZE), Validator (VALIDATE),
    Repository (PERSIST), or Exporter (EXPORT)."""

    CRAWL = "CRAWL"
    PARSE = "PARSE"
    NORMALIZE = "NORMALIZE"
    VALIDATE = "VALIDATE"
    PERSIST = "PERSIST"
    EXPORT = "EXPORT"


class Error(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "errors"

    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[ErrorStageEnum] = mapped_column(
        SAEnum(ErrorStageEnum, name="error_stage_enum"), nullable=False
    )
    error_type: Mapped[str] = mapped_column(String(150), nullable=False)
    """The exception class name, e.g. 'ParsingError', 'ValidationFailedError'."""
    message: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    source: Mapped[Optional["Source"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Error stage={self.stage} type={self.error_type!r}>"
