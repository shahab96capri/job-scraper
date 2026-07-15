"""
`CategoryRepository` — manages the self-referential `categories` tree.

`get_or_create` is scoped by `(name, parent_id)`, matching the model's
unique constraint — so "برنامه‌نویسی" as a top-level category and
"برنامه‌نویسی" as a sub-category under a different parent are correctly
treated as distinct rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.category import Category
from app.repositories.base_repository import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    async def get_by_name_and_parent(
        self, name: str, parent_id: uuid.UUID | None
    ) -> Category | None:
        stmt = select(Category).where(Category.name == name, Category.parent_id == parent_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, name: str | None, parent_id: uuid.UUID | None = None
    ) -> Category | None:
        name = (name or "").strip()
        if not name:
            return None
        existing = await self.get_by_name_and_parent(name, parent_id)
        if existing is not None:
            return existing
        return await self.add(Category(name=name, parent_id=parent_id))
