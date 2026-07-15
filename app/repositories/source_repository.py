"""
`SourceRepository` — manages the `sources` lookup table.

`get_or_create` is idempotent by design: `main.py` / the pipeline calls it
once per known source (jobvision, jobinja, irantalent, ponisha) at
startup, so registering a brand-new site is a one-line call here, not a
migration — directly satisfying the "unlimited future websites" goal.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.source import Source
from app.repositories.base_repository import BaseRepository


class SourceRepository(BaseRepository[Source]):
    model = Source

    async def get_by_code(self, code: str) -> Source | None:
        stmt = select(Source).where(Source.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, *, code: str, name: str, base_url: str) -> Source:
        existing = await self.get_by_code(code)
        if existing is not None:
            return existing
        return await self.add(Source(code=code, name=name, base_url=base_url))
