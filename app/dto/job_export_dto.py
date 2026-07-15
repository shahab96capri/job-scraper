"""
`JobExportDTO` — the flat, human-readable shape every exported job takes
in both JSON and Excel output.

Deliberately a separate DTO from `JobDTO` (the Normalizer/Validator/
Repository-stage contract): `JobDTO` carries plain strings for
`company_name`/`category_name`/etc. *before* they're resolved to FK rows.
`JobExportDTO` carries the same conceptual fields but is built *after*
persistence, from the ORM `Job` plus its eager-loaded relationships
(`job.company.name`, `job.category.name`, ...) — the authoritative,
already-deduplicated values actually stored in the database, not
whatever a single job posting's normalization happened to produce. Two
job postings from the same company with slightly different raw company
name spellings resolve to the *same* `Company` row; exporting from the
DTO layer would show the spelling variance, exporting from the ORM (via
this class) shows the single canonical name every time.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.dto.base import PlatformBaseModel
from app.models.enums import (
    Currency,
    EducationLevel,
    ExperienceLevel,
    Gender,
    JobStatus,
    MilitaryStatus,
    WorkMode,
)


class JobExportDTO(PlatformBaseModel):
    id: uuid.UUID
    source: str
    website_job_id: str
    source_url: str

    title: str
    company_name: str | None = None
    category_name: str | None = None
    sub_category_name: str | None = None
    employment_type: str | None = None

    work_mode: WorkMode
    experience_level: ExperienceLevel
    education: EducationLevel

    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    currency: Currency

    province: str | None = None
    city: str | None = None

    gender: Gender
    military_status: MilitaryStatus

    description: str | None = None
    responsibilities: str | None = None
    requirements: str | None = None
    benefits: list[str] | None = None

    technologies: list[str] | None = None
    skills: list[str] | None = None
    languages: list[str] | None = None

    published_at: date | None = None
    expires_at: date | None = None
    status: JobStatus

    scraped_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_job(cls, job) -> "JobExportDTO":
        """Build an export row from a `Job` ORM instance.

        Requires `company`, `category`, `sub_category`, `employment_type`,
        `location`, `source`, and `skill_links.skill` to already be
        eager-loaded (see `JobRepository.list_by_source_with_relations`) —
        this deliberately does not lazy-load, since `AsyncSession` cannot
        lazily resolve relationships outside its original await context.
        """
        return cls(
            id=job.id,
            source=job.source.code,
            website_job_id=job.website_job_id,
            source_url=job.source_url,
            title=job.title,
            company_name=job.company.name if job.company else None,
            category_name=job.category.name if job.category else None,
            sub_category_name=job.sub_category.name if job.sub_category else None,
            employment_type=job.employment_type.code if job.employment_type else None,
            work_mode=job.work_mode,
            experience_level=job.experience_level,
            education=job.education,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            currency=job.currency,
            province=job.location.province if job.location else None,
            city=job.location.city if job.location else None,
            gender=job.gender,
            military_status=job.military_status,
            description=job.description,
            responsibilities=job.responsibilities,
            requirements=job.requirements,
            benefits=job.benefits,
            technologies=job.technologies,
            skills=[link.skill.name for link in job.skill_links] or None,
            languages=job.languages,
            published_at=job.published_at,
            expires_at=job.expires_at,
            status=job.status,
            scraped_at=job.scraped_at,
            updated_at=job.updated_at,
        )
