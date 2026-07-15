"""
Raw DTOs — the exact output contract of the Parser layer.

Design decision: these are deliberately "dumb" containers. Every field is
`str | None` (or `list[str] | None`), holding text exactly as extracted
from HTML. NO type conversion (e.g. parsing "15,000,000 تومان" into a
`Decimal`), NO cleaning (trimming whitespace, fixing encoding), and NO
validation happens here — that is the Normalizer's and Validator's job
respectively. This enforces the spec's "Parser only extracts raw values"
rule at the type-system level: a Parser physically cannot return a
`Decimal` or an `Enum` member here, only strings.

Using `pydantic.BaseModel` (not a plain `dataclass`) even for the raw
layer gives us:
- immutability (`frozen=True`) — a parser output, once produced, is never
  mutated; the Normalizer produces a *new* DTO instead.
- free structural validation that the parser at least returned the right
  *shape* (e.g. `raw_technologies` really is a list of strings, even
  though the strings themselves are unvalidated).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RawJobDTO(BaseModel):
    """Exact output of `BaseParser.parse_job_page()` for one job posting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Source linkage (parser fills these from the URL/page, verbatim) ---
    source_code: str
    website_job_id: str | None = None
    source_url: str

    # --- Core content, raw strings exactly as found in the DOM ---
    raw_title: str | None = None
    raw_company_name: str | None = None
    raw_company_url: str | None = None

    raw_category: str | None = None
    raw_sub_category: str | None = None
    raw_employment_type: str | None = None
    raw_work_mode: str | None = None
    raw_experience_level: str | None = None
    raw_education: str | None = None

    raw_salary: str | None = None
    """Entire salary text blob, e.g. 'از ۱۵,۰۰۰,۰۰۰ تا ۲۵,۰۰۰,۰۰۰ تومان' or
    'حقوق توافقی' — splitting/parsing this happens in the Normalizer."""

    raw_province: str | None = None
    raw_city: str | None = None

    raw_gender: str | None = None
    raw_military_status: str | None = None

    raw_description: str | None = None
    raw_responsibilities: str | None = None
    raw_requirements: str | None = None
    raw_benefits: list[str] | None = None

    raw_technologies: list[str] | None = None
    raw_skills: list[str] | None = None
    raw_languages: list[str] | None = None

    raw_published_at: str | None = None
    raw_expires_at: str | None = None
    raw_status: str | None = None


class RawCompanyDTO(BaseModel):
    """Exact output of `BaseParser.parse_company_page()` for one company."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_code: str
    website_company_id: str | None = None
    source_url: str

    raw_name: str | None = None
    raw_industry: str | None = None
    raw_description: str | None = None
    raw_company_size: str | None = None
    raw_founded_year: str | None = None

    raw_website: str | None = None
    raw_phone: str | None = None
    raw_email: str | None = None
    raw_address: str | None = None
    raw_province: str | None = None
    raw_city: str | None = None

    raw_linkedin_url: str | None = None
    raw_instagram_url: str | None = None
    raw_twitter_url: str | None = None
    raw_benefits: list[str] | None = None
