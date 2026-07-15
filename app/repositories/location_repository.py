"""
`LocationRepository` — manages the normalized `(province, city)` table.

`get_or_create` returns `None` when both `province` and `city` are empty
(a job/company with genuinely unknown location should have `location_id
IS NULL`, not a fabricated "Unknown, Unknown" row polluting location-based
analytics).
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.location import Location
from app.repositories.base_repository import BaseRepository


class LocationRepository(BaseRepository[Location]):
    model = Location

    async def get_by_province_city(self, province: str, city: str) -> Location | None:
        stmt = select(Location).where(Location.province == province, Location.city == city)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, province: str | None, city: str | None
    ) -> Location | None:
        province = (province or "").strip()
        city = (city or "").strip()
        if not province and not city:
            return None
        # A city without a known province (or vice versa) still gets a row —
        # better to have a partially-known location than to drop the signal.
        existing = await self.get_by_province_city(province, city)
        if existing is not None:
            return existing
        return await self.add(Location(province=province, city=city))
