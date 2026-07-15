"""`ErrorRepository` — writes structured pipeline failures to the `errors`
table (failures that survived the Commit 3 retry system).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.error import Error, ErrorStageEnum
from app.repositories.base_repository import BaseRepository


class ErrorRepository(BaseRepository[Error]):
    model = Error

    async def create(
        self,
        *,
        stage: ErrorStageEnum,
        error_type: str,
        message: str,
        url: str | None = None,
        traceback: str | None = None,
        source_id: uuid.UUID | None = None,
    ) -> Error:
        return await self.add(
            Error(
                stage=stage,
                error_type=error_type,
                message=message,
                url=url,
                traceback=traceback,
                source_id=source_id,
            )
        )

    async def get_unresolved(self, *, limit: int = 100) -> list[Error]:
        stmt = (
            select(Error)
            .where(Error.resolved.is_(False))
            .order_by(Error.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_resolved(self, error: Error) -> Error:
        error.resolved = True
        await self.session.flush()
        return error
