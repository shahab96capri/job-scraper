"""
`Job` is the central entity of the platform. Every field listed in the
spec's "JOB MODEL" section is represented below.

Notes on a few deliberate design choices:

- `technologies` (raw ARRAY(String)) vs the `skills` relationship
  (via `JobSkill` -> `Skill`): these serve different purposes.
  `technologies` is the raw, source-specific list extracted by the Parser
  before normalization ("React.js", "Node.js", "Rest API" verbatim from
  the page). `skills` is the normalized, deduplicated, cross-source
  entity graph built by the Normalizer from that raw list (Commit 4+).
  Keeping both means we never lose the original signal even if
  normalization logic improves later and needs to be re-run.
- `category` / `sub_category` both point at the same `categories` table
  (self-referential tree) via two separate foreign keys, matching the
  spec's explicit "Category" + "Sub Category" fields while reusing one
  lookup table instead of two.
- `(source_id, website_job_id)` is the natural key for duplicate/update
  detection in the Pipeline layer (Commit 3): "have we seen this exact
  job posting from this exact source before?"
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    Currency,
    EducationLevel,
    ExperienceLevel,
    Gender,
    JobStatus,
    MilitaryStatus,
    WorkMode,
)

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.company import Company
    from app.models.employment_type import EmploymentType
    from app.models.location import Location
    from app.models.skill import JobSkill
    from app.models.source import Source


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "website_job_id", name="uq_job_source_website_id"),
    )

    # --- Source linkage ---
    source_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    website_job_id: Mapped[str] = mapped_column(String(150), nullable=False)
    """The job's identifier on the source website (e.g. the '1094514' in
    jobvision.ir/jobs/1094514/...). Used with source_id for dedup."""
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    # --- Core content ---
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)

    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    sub_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    employment_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employment_types.id", ondelete="SET NULL"), nullable=True
    )

    work_mode: Mapped[WorkMode] = mapped_column(
        SAEnum(WorkMode, name="work_mode_enum"), default=WorkMode.UNKNOWN, nullable=False
    )
    experience_level: Mapped[ExperienceLevel] = mapped_column(
        SAEnum(ExperienceLevel, name="experience_level_enum"),
        default=ExperienceLevel.UNKNOWN,
        nullable=False,
    )
    education: Mapped[EducationLevel] = mapped_column(
        SAEnum(EducationLevel, name="education_level_enum"),
        default=EducationLevel.UNKNOWN,
        nullable=False,
    )

    # --- Compensation ---
    salary_min: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2), nullable=True)
    salary_max: Mapped[Optional[Numeric]] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[Currency] = mapped_column(
        SAEnum(Currency, name="currency_enum"), default=Currency.IRT, nullable=False
    )

    # --- Location ---
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )

    # --- Candidate requirements ---
    gender: Mapped[Gender] = mapped_column(
        SAEnum(Gender, name="gender_enum"), default=Gender.UNKNOWN, nullable=False
    )
    military_status: Mapped[MilitaryStatus] = mapped_column(
        SAEnum(MilitaryStatus, name="military_status_enum"),
        default=MilitaryStatus.UNKNOWN,
        nullable=False,
    )

    # --- Free text content ---
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requirements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    benefits: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)

    # --- Extracted signals ---
    technologies: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    """Raw technology mentions as extracted by the Parser, pre-normalization."""
    languages: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    """Required spoken/written languages, e.g. ['English-Intermediate']."""

    # --- Lifecycle ---
    published_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expires_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status_enum"), default=JobStatus.ACTIVE, nullable=False
    )
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Relationships ---
    source: Mapped["Source"] = relationship(back_populates="jobs")
    company: Mapped[Optional["Company"]] = relationship(back_populates="jobs")
    location: Mapped[Optional["Location"]] = relationship(back_populates="jobs")
    employment_type: Mapped[Optional["EmploymentType"]] = relationship(back_populates="jobs")
    category: Mapped[Optional["Category"]] = relationship(
        back_populates="jobs", foreign_keys=[category_id]
    )
    sub_category: Mapped[Optional["Category"]] = relationship(
        back_populates="jobs_as_subcategory", foreign_keys=[sub_category_id]
    )
    skill_links: Mapped[list["JobSkill"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Job id={self.id} title={self.title!r}>"
