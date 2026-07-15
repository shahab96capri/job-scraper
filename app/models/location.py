"""
`Location` normalizes (province, city) pairs to a single reusable row,
instead of storing free-text location strings on every `Job`/`Company` row.

This lets salary/job-count analytics group cleanly by city — critical for
the future "Salary Intelligence" feature — without needing to fuzzy-match
strings like "تهران" vs "تهران، ایران" vs "Tehran" at query time; that
fuzzy-matching happens once, in the Normalizer layer, when the row is
created.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.job import Job


class Location(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("province", "city", name="uq_location_province_city"),)

    province: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="location")
    companies: Mapped[list["Company"]] = relationship(back_populates="location")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Location {self.city}, {self.province}>"
