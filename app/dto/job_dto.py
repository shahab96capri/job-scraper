"""
`JobDTO` is the unified, normalized representation of a job posting —
the output of the Normalizer layer, the input to the Validator, and the
object every downstream layer (Pipeline, Repository, Exporter) agrees on.

Deliberately does NOT carry foreign-key UUIDs (`company_id`,
`category_id`, etc.). The Normalizer has no database access — it only
maps raw strings to standard values — so `JobDTO` carries normalized
*names/codes* (`company_name`, `category_name`, `employment_type_code`,
`province`, `city`). Resolving those to actual FK UUIDs (get-or-create
against `companies`, `categories`, `employment_types`, `locations`) is
the Repository/Pipeline's job (Commit 3), which is the only layer that
touches the database.

`skills` vs `technologies`: `technologies` is carried over from the raw
DTO's `technologies_raw` after cleaning (trimming, deduplication) but
without matching against the `skills` taxonomy. `skills` is the
Normalizer's best-effort mapping of those (plus mentions in the
description) onto canonical skill names — the list that will ultimately
populate the `JobSkill` association table.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import model_validator

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


class JobDTO(PlatformBaseModel):
    # --- Source linkage ---
    source_code: str
    website_job_id: str
    source_url: str

    # --- Core content ---
    title: str
    company_name: str | None = None

    category_name: str | None = None
    sub_category_name: str | None = None
    employment_type_code: str | None = None
    """Must match an `EmploymentType.code` value, e.g. FULL_TIME, PART_TIME,
    CONTRACT, INTERNSHIP, PROJECT_BASED, FREELANCE — enforced by the
    Validator layer against the live lookup table, not here."""

    work_mode: WorkMode = WorkMode.UNKNOWN
    experience_level: ExperienceLevel = ExperienceLevel.UNKNOWN
    education: EducationLevel = EducationLevel.UNKNOWN

    # --- Compensation ---
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    currency: Currency = Currency.IRT

    # --- Location ---
    province: str | None = None
    city: str | None = None

    # --- Candidate requirements ---
    gender: Gender = Gender.UNKNOWN
    military_status: MilitaryStatus = MilitaryStatus.UNKNOWN

    # --- Free text ---
    description: str | None = None
    responsibilities: str | None = None
    requirements: str | None = None
    benefits: list[str] | None = None

    # --- Extracted signals ---
    technologies: list[str] | None = None
    skills: list[str] | None = None
    languages: list[str] | None = None

    # --- Lifecycle ---
    published_at: date | None = None
    expires_at: date | None = None
    status: JobStatus = JobStatus.ACTIVE
    scraped_at: datetime

    @model_validator(mode="after")
    def _check_salary_range(self) -> "JobDTO":
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError(
                    f"salary_min ({self.salary_min}) cannot exceed "
                    f"salary_max ({self.salary_max})"
                )
        return self

    @model_validator(mode="after")
    def _check_date_range(self) -> "JobDTO":
        if self.published_at and self.expires_at:
            if self.expires_at < self.published_at:
                raise ValueError(
                    f"expires_at ({self.expires_at}) is before "
                    f"published_at ({self.published_at})"
                )
        return self
