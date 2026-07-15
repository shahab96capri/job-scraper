"""`LogRepository` — writes curated lifecycle events to the `logs` table.

See `app/models/log.py` for why this is a small, deliberately-curated
table rather than a mirror of every Loguru file-log line.
"""

from __future__ import annotations

import uuid

from app.models.enums import LogLevel
from app.models.log import Log
from app.repositories.base_repository import BaseRepository


class LogRepository(BaseRepository[Log]):
    model = Log

    async def create(
        self,
        *,
        level: LogLevel,
        component: str,
        message: str,
        context: dict | None = None,
        source_id: uuid.UUID | None = None,
    ) -> Log:
        return await self.add(
            Log(
                level=level,
                component=component,
                message=message,
                context=context,
                source_id=source_id,
            )
        )
