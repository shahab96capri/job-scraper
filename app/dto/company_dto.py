"""
`CompanyDTO` — the normalized, unified representation of a company,
analogous to `JobDTO`. See `app/dto/job.py` for the rationale on why FK
UUIDs are not carried here (only `province`/`city`, resolved to a
`Location` row by the Repository layer).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from app.dto.base import PlatformBaseModel
from app.models.enums import CompanySize

CURRENT_YEAR_UPPER_BOUND = 2100
FOUNDED_YEAR_LOWER_BOUND = 1900


class CompanyDTO(PlatformBaseModel):
    # --- Source linkage ---
    source_code: str
    website_company_id: str | None = None
    source_url: str

    # --- Core identity ---
    name: str
    industry: str | None = None
    description: str | None = None
    company_size: CompanySize = CompanySize.UNKNOWN
    founded_year: int | None = None

    # --- Contact ---
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None

    # --- Location ---
    province: str | None = None
    city: str | None = None

    # --- Social ---
    linkedin_url: str | None = None
    instagram_url: str | None = None
    twitter_url: str | None = None

    benefits: list[str] | None = None

    scraped_at: datetime

    @field_validator("founded_year")
    @classmethod
    def _validate_founded_year(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if not (FOUNDED_YEAR_LOWER_BOUND <= value <= CURRENT_YEAR_UPPER_BOUND):
            raise ValueError(
                f"founded_year {value} is out of plausible range "
                f"[{FOUNDED_YEAR_LOWER_BOUND}, {CURRENT_YEAR_UPPER_BOUND}]"
            )
        return value
