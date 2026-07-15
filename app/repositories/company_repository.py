"""
`CompanyRepository` — manages the `companies` table, including the
duplicate-detection / update-detection logic ("Update Detection" from the
spec's Special Features) for companies specifically.

Design decision: `upsert()` accepts already-resolved foreign key UUIDs
(`source_id`, `location_id`) rather than resolving them itself. Resolving
a `Location` from raw province/city strings is `LocationRepository`'s job;
`CompanyRepository` must not depend on `LocationRepository` (repositories
stay decoupled from one another — the Pipeline layer, Commit 3, is what
orchestrates calling both in the right order within one transaction).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dto.company_dto import CompanyDTO
from app.models.company import Company
from app.repositories.base_repository import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def list_by_source_with_relations(self, source_id: uuid.UUID) -> list[Company]:
        """Return every `Company` for `source_id` with `location` and
        `source` eager-loaded — the Exporter layer's read path. See
        `JobRepository.list_by_source_with_relations` for the same
        rationale (flat, human-readable export rows without N+1 queries)."""
        stmt = (
            select(Company)
            .where(Company.source_id == source_id)
            .options(selectinload(Company.location), selectinload(Company.source))
            .order_by(Company.scraped_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_source_and_website_id(
        self, source_id: uuid.UUID, website_company_id: str
    ) -> Company | None:
        stmt = select(Company).where(
            Company.source_id == source_id,
            Company.website_company_id == website_company_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_source_and_name(self, source_id: uuid.UUID, name: str) -> Company | None:
        stmt = select(Company).where(Company.source_id == source_id, Company.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        dto: CompanyDTO,
        *,
        source_id: uuid.UUID,
        location_id: uuid.UUID | None,
    ) -> tuple[Company, bool]:
        """Create the company if unseen, otherwise update it in place.

        Returns `(company, created)` where `created` is True only if a new
        row was inserted — used by the pipeline to increment
        `ScrapeHistory.companies_created` vs `companies_updated`.
        """
        existing: Company | None = None
        if dto.website_company_id:
            existing = await self.get_by_source_and_website_id(source_id, dto.website_company_id)
        if existing is None:
            # Fallback natural key for sites that don't expose a stable
            # company ID separate from a slug that may itself change.
            existing = await self.get_by_source_and_name(source_id, dto.name)

        field_values = dict(
            website_company_id=dto.website_company_id,
            source_url=dto.source_url,
            name=dto.name,
            industry=dto.industry,
            description=dto.description,
            company_size=dto.company_size,
            founded_year=dto.founded_year,
            website=dto.website,
            phone=dto.phone,
            email=dto.email,
            address=dto.address,
            location_id=location_id,
            linkedin_url=dto.linkedin_url,
            instagram_url=dto.instagram_url,
            twitter_url=dto.twitter_url,
            benefits=dto.benefits or None,
            scraped_at=dto.scraped_at,
        )

        if existing is not None:
            for field, value in field_values.items():
                setattr(existing, field, value)
            await self.session.flush()
            return existing, False

        company = Company(source_id=source_id, **field_values)
        return await self.add(company), True
