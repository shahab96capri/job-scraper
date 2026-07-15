"""
`Category` models both top-level job categories ("برنامه‌نویسی و توسعه نرم‌افزار")
and sub-categories ("برنامه‌نویس بک‌اند") via a self-referential `parent_id`,
rather than two separate `category` / `sub_category` string columns on
`Job`. This avoids duplicating the same category name thousands of times
across job rows and lets the future Knowledge Graph feature walk the
category tree directly.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "parent_id", name="uq_category_name_parent"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    parent: Mapped[Optional["Category"]] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="category", foreign_keys="Job.category_id"
    )
    jobs_as_subcategory: Mapped[list["Job"]] = relationship(
        back_populates="sub_category", foreign_keys="Job.sub_category_id"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name!r}>"
