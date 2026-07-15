"""
`EmploymentType` is a lookup table (FULL_TIME, PART_TIME, CONTRACT,
INTERNSHIP, PROJECT_BASED, FREELANCE) rather than a raw string column,
so every site's "تمام وقت" / "کارمند تمام‌وقت" / "Full-time" collapses to
one canonical row that the platform can filter/aggregate on.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.job import Job


class EmploymentType(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employment_types"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    """Canonical code, e.g. FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP,
    PROJECT_BASED, FREELANCE."""

    label_fa: Mapped[str] = mapped_column(String(100), nullable=False)
    label_en: Mapped[str] = mapped_column(String(100), nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="employment_type")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmploymentType {self.code}>"
