"""
`BaseRepository` — generic CRUD operations shared by every concrete
repository.

Design decisions:
- Generic over `ModelType` (bound to the shared declarative `Base`) so
  `get_by_id`, `add`, `delete`, `list_all` are written exactly once instead
  of copy-pasted into every repository (violates the spec's "no duplicated
  code" rule otherwise).
- The `AsyncSession` is received via **constructor injection**, never
  created or closed by the repository itself. Session lifecycle
  (commit/rollback/close) is owned exclusively by
  `app.database.session.get_db_session()`; a repository that opened its
  own session would make it impossible to compose multiple repository
  calls into one atomic transaction (e.g. "create company AND create job"
  must commit or roll back together).
- `add()` flushes (not commits) so the caller gets a populated primary key
  immediately (needed to link FKs within the same unit of work) while the
  actual commit/rollback boundary stays with `get_db_session()`.
"""

from __future__ import annotations

import uuid
from typing import Generic, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base class every concrete repository inherits from.

    Subclasses must set the `model` class attribute to the SQLAlchemy
    model they manage, e.g. `model = Job`.
    """

    model: Type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelType | None:
        return await self.session.get(self.model, entity_id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, instance: ModelType) -> ModelType:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def count(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
