"""
`SkillRepository` — manages the `skills` table.

Deduplication key is `normalized_name` (lowercased + trimmed), not `name`,
so "Node.js", "NodeJS", "nodejs " all resolve to the same `Skill` row while
`name` retains whichever display form was first observed. This is what
makes the future Skill Extraction / Knowledge Graph features usable —
without it, the same technology would fragment into dozens of near-
duplicate skill rows across four different sites' inconsistent casing.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.skill import Skill
from app.repositories.base_repository import BaseRepository


class SkillRepository(BaseRepository[Skill]):
    model = Skill

    @staticmethod
    def normalize(name: str) -> str:
        return " ".join(name.strip().lower().split())

    async def get_by_normalized_name(self, normalized_name: str) -> Skill | None:
        stmt = select(Skill).where(Skill.normalized_name == normalized_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str) -> Skill | None:
        name = name.strip()
        if not name:
            return None
        normalized = self.normalize(name)
        existing = await self.get_by_normalized_name(normalized)
        if existing is not None:
            return existing
        return await self.add(Skill(name=name, normalized_name=normalized))

    async def get_or_create_many(self, names: list[str]) -> list[Skill]:
        skills: list[Skill] = []
        seen_normalized: set[str] = set()
        for raw_name in names:
            normalized = self.normalize(raw_name) if raw_name else ""
            if not normalized or normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            skill = await self.get_or_create(raw_name)
            if skill is not None:
                skills.append(skill)
        return skills
