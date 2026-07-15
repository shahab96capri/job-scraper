"""`CompanyExportDTO` — the flat export shape for companies. See
`app/dto/job_export_dto.py` for the rationale (built from the persisted
ORM `Company` + eager-loaded relationships, not from `CompanyDTO`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.dto.base import PlatformBaseModel
from app.models.enums import CompanySize


class CompanyExportDTO(PlatformBaseModel):
    id: uuid.UUID
    source: str
    website_company_id: str | None = None
    source_url: str

    name: str
    industry: str | None = None
    description: str | None = None
    company_size: CompanySize
    founded_year: int | None = None

    website: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    province: str | None = None
    city: str | None = None

    linkedin_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None
    benefits: list[str] | None = None

    scraped_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_company(cls, company) -> "CompanyExportDTO":
        """Build an export row from a `Company` ORM instance. Requires
        `location` and `source` to already be eager-loaded (see
        `CompanyRepository.list_by_source_with_relations`)."""
        return cls(
            id=company.id,
            source=company.source.code,
            website_company_id=company.website_company_id,
            source_url=company.source_url,
            name=company.name,
            industry=company.industry,
            description=company.description,
            company_size=company.company_size,
            founded_year=company.founded_year,
            website=company.website,
            phone=company.phone,
            email=company.email,
            address=company.address,
            province=company.location.province if company.location else None,
            city=company.location.city if company.location else None,
            linkedin_url=company.linkedin_url,
            instagram_url=company.instagram_url,
            twitter_url=company.twitter_url,
            benefits=company.benefits,
            scraped_at=company.scraped_at,
            updated_at=company.updated_at,
        )
