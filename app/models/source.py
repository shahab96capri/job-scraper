"""
`Source` represents one crawlable website (JobVision, Jobinja, IranTalent,
Ponisha, and any future site).

Keeping sources as DATA (a table) rather than hardcoded strings scattered
across spiders is what lets the platform "support unlimited future
websites" without schema changes: adding a site is an INSERT + a new
Spider/Parser/Normalizer implementation, never a migration.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.job import Job
    from app.models.scrape_history import ScrapeHistory


class Source(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sources"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    """Machine-readable identifier, e.g. 'jobvision', 'jobinja'. Used by
    spiders/repositories to look the source up without a hardcoded UUID."""

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    respects_robots_txt: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="source")
    companies: Mapped[list["Company"]] = relationship(back_populates="source")
    scrape_history: Mapped[list["ScrapeHistory"]] = relationship(back_populates="source")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Source id={self.id} code={self.code!r}>"
