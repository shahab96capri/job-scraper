"""
`EmploymentTypeRepository` — manages the `employment_types` lookup table.

Unlike `Category`/`Location`/`Skill`, employment types form a small, known,
closed set (FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP, PROJECT_BASED,
FREELANCE) that the Normalizer maps every source's free text onto. This
repository still exposes `get_or_create` (rather than requiring a fixed
seed migration) so the Normalizer's mapping table remains the single
source of truth for valid codes — adding a new employment type code is a
Normalizer change, not a migration.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.employment_type import EmploymentType
from app.repositories.base_repository import BaseRepository


class EmploymentTypeRepository(BaseRepository[EmploymentType]):
    model = EmploymentType

    async def get_by_code(self, code: str) -> EmploymentType | None:
        stmt = select(EmploymentType).where(EmploymentType.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, *, code: str, label_fa: str = "", label_en: str = ""
    ) -> EmploymentType:
        existing = await self.get_by_code(code)
        if existing is not None:
            return existing
        return await self.add(
            EmploymentType(code=code, label_fa=label_fa or code, label_en=label_en or code)
        )
