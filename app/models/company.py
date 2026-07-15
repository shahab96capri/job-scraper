"""
`Company` model — every field explicitly requested in the spec is
represented. `website_company_id` + `source_id` together form the natural
key used for duplicate detection during crawling (Commit 3's pipeline
resolves "have we already seen this company from this source?" via that
pair, not by fuzzy-matching company names).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    ARRAY,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CompanySize

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.location import Location
    from app.models.source import Source


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("source_id", "website_company_id", name="uq_company_source_website_id"),
    )

    # --- Source linkage ---
    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    website_company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    """The company's identifier/slug on the source website, e.g. the
    '4245' in jobvision.ir/companies/4245/... Nullable because some sites
    don't expose a stable company ID separate from the slug."""
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    # --- Core identity ---
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_size: Mapped[CompanySize] = mapped_column(
        SAEnum(CompanySize, name="company_size_enum"),
        default=CompanySize.UNKNOWN,
        nullable=False,
    )
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Contact ---
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Location ---
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )

    # --- Social ---
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    instagram_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    benefits: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)

    # --- Crawl bookkeeping ---
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Relationships ---
    source: Mapped["Source"] = relationship(back_populates="companies")
    location: Mapped[Optional["Location"]] = relationship(back_populates="companies")
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company id={self.id} name={self.name!r}>"
