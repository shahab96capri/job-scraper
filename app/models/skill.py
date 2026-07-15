"""
`Skill` + `JobSkill` model the many-to-many relationship between jobs and
the skills/technologies they require.

`JobSkill` is implemented as an explicit association *model* (not a bare
`Table()`) because it already carries extra attributes the future AI
Classification / Recommendation Engine features will need per pair
(`is_required`, `proficiency_level`, `mention_count`) — an implicit
many-to-many table cannot hold that without a schema change later.

`normalized_name` is what uniqueness/deduplication is keyed on (lowercased,
trimmed, e.g. "Node.js" / "nodejs" / "NodeJS" -> "nodejs"), while `name`
retains the best-observed display form for exports/UI.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Skill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)

    job_links: Mapped[list["JobSkill"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Skill {self.name!r}>"


class JobSkill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Association entity between `Job` and `Skill`."""

    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id", name="uq_job_skill"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )

    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    """True if the skill was listed under requirements; False if it only
    appeared in the free-text description (weaker signal)."""

    proficiency_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    """E.g. 'Basic' / 'Intermediate' / 'Advanced', when the source site
    provides a per-skill proficiency rating (JobVision does)."""

    mention_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="skill_links")
    skill: Mapped["Skill"] = relationship(back_populates="job_links")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JobSkill job_id={self.job_id} skill_id={self.skill_id}>"
