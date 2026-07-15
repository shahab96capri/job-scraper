"""
`JobVisionNormalizer` — maps `JobVisionParser`'s raw output onto the
platform's standard `JobDTO`/`CompanyDTO`.

Mapping-table confidence levels (important — see README Commit 4 section
for the full breakdown): values with a real, observed example in the two
job pages + one company page the user provided are marked VERIFIED in the
comments below. Values not observed in the sample data are my best-effort
inference from common Iranian job-site vocabulary and JobVision's own
public category filters (e.g. `/jobs/keyword/x/type/part-time` seen in the
listing page's own navigation links) — marked INFERRED. Every mapping
table falls back to a safe `*_UNKNOWN`/`None` value rather than raising,
so an unmapped raw value degrades gracefully instead of failing the whole
job (`JobValidator` doesn't reject `UNKNOWN` enum members).
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.core.logging import logger
from app.dto.company_dto import CompanyDTO
from app.dto.job_dto import JobDTO
from app.dto.raw_dto import RawCompanyDTO, RawJobDTO
from app.models.enums import (
    Currency,
    EducationLevel,
    ExperienceLevel,
    Gender,
    JobStatus,
    MilitaryStatus,
    WorkMode,
)
from app.models.enums import CompanySize
from app.normalizers.base_normalizer import BaseNormalizer

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_TRANSLATION = str.maketrans(
    _PERSIAN_DIGITS + _ARABIC_DIGITS, "0123456789" + "0123456789"
)

# VERIFIED: "تمام وقت" -> observed on both sample jobs.
# INFERRED: the rest, from JobVision's own listing-page filter links
# (".../jobs/keyword/x/type/part-time" etc. seen in the listing page HTML)
# and standard Iranian job-site vocabulary.
_EMPLOYMENT_TYPE_MAP = {
    "تمام وقت": "FULL_TIME",
    "پاره وقت": "PART_TIME",
    "پروژه ای": "PROJECT_BASED",
    "پروژه‌ای": "PROJECT_BASED",
    "کارآموزی": "INTERNSHIP",
    "فریلنسری": "FREELANCE",
    "قراردادی": "CONTRACT",
}

# VERIFIED: both "حضوری"/"دورکاری" values are synthesized by
# JobVisionParser itself from the typed `isRemote` boolean, so this
# mapping is exhaustive and 100% reliable by construction (not a guess
# about site vocabulary).
_WORK_MODE_MAP = {
    "دورکاری": WorkMode.REMOTE,
    "حضوری": WorkMode.ON_SITE,
}

# VERIFIED: "کارشناس" observed on both sample jobs.
# INFERRED: the rest, standard JobVision seniority ladder terminology.
_EXPERIENCE_LEVEL_MAP = {
    "کارآموز": ExperienceLevel.INTERNSHIP,
    "تازه کار": ExperienceLevel.JUNIOR,
    "کارشناس": ExperienceLevel.MID,
    "کارشناس ارشد": ExperienceLevel.SENIOR,
    "سرپرست": ExperienceLevel.SENIOR,
    "مدیر": ExperienceLevel.LEAD,
}

# VERIFIED: "کارشناسی" observed.
# INFERRED: the rest, standard Iranian academic degree names.
_EDUCATION_MAP = {
    "دیپلم": EducationLevel.DIPLOMA,
    "کاردانی": EducationLevel.ASSOCIATE,
    "کارشناسی": EducationLevel.BACHELOR,
    "کارشناسی ارشد": EducationLevel.MASTER,
    "دکترا": EducationLevel.PHD,
    "دکتری": EducationLevel.PHD,
}

# VERIFIED: "الزامی"/"غیرالزامی" are synthesized by JobVisionParser from
# the typed `shouldDoneMilitaryService` boolean — reliable by construction.
_MILITARY_STATUS_MAP = {
    "الزامی": MilitaryStatus.COMPLETED,
    "غیرالزامی": MilitaryStatus.NOT_REQUIRED,
}

# VERIFIED: "فعال"/"منقضی" synthesized by JobVisionParser from the typed
# `isExpired` boolean — reliable by construction.
_STATUS_MAP = {
    "فعال": JobStatus.ACTIVE,
    "منقضی": JobStatus.EXPIRED,
}

# VERIFIED: "11 تا 50 نفر" observed on the sample company.
# INFERRED: the rest, standard JobVision company-size buckets.
_COMPANY_SIZE_MAP = {
    "1 تا 10": CompanySize.SIZE_1_10,
    "11 تا 50": CompanySize.SIZE_11_50,
    "51 تا 200": CompanySize.SIZE_51_200,
    "201 تا 500": CompanySize.SIZE_201_500,
    "500": CompanySize.SIZE_500_PLUS,
}

_SALARY_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
_MILLION_TOMAN = 1_000_000

# Jalali (Iranian solar Hijri) -> Gregorian year offset. Approximate at the
# year level only (off by at most one year around the March new-year
# boundary) — acceptable here because `Company.founded_year` is a plain
# int with no day/month precision requirement. A day-accurate conversion
# would need the `jdatetime` package, deliberately not added as a
# dependency for a single approximate field.
_JALALI_TO_GREGORIAN_YEAR_OFFSET = 621


def _normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_TRANSLATION)


def _map_gender(raw: str | None) -> Gender:
    if not raw:
        return Gender.UNKNOWN
    has_female = "خانم" in raw or "زن" in raw
    has_male = "آقا" in raw or "مرد" in raw
    if has_female and has_male:
        return Gender.ANY
    if has_female:
        return Gender.FEMALE
    if has_male:
        return Gender.MALE
    return Gender.UNKNOWN


def _parse_salary(raw_salary: str | None) -> tuple[float | None, float | None]:
    """Parse JobVision's `salary.titleFa` text (already Toman, in
    millions) into `(min, max)` actual-Toman values. Returns `(None,
    None)` for negotiable/missing salary — VERIFIED against
    "45 - 60 میلیون تومان" (range) and `None` (negotiable, job 2)."""
    if not raw_salary:
        return None, None
    normalized = _normalize_digits(raw_salary)
    numbers = [float(n) for n in _SALARY_NUMBER_RE.findall(normalized)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        value = numbers[0] * _MILLION_TOMAN
        return value, value
    return numbers[0] * _MILLION_TOMAN, numbers[1] * _MILLION_TOMAN


def _parse_iso_datetime_to_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        logger.bind(component="normalizers.jobvision").warning(
            f"Could not parse ISO datetime: {raw!r}"
        )
        return None


def _map_company_size(raw: str | None) -> CompanySize:
    if not raw:
        return CompanySize.UNKNOWN
    normalized = _normalize_digits(raw)
    for prefix, size in _COMPANY_SIZE_MAP.items():
        if prefix in normalized:
            return size
    return CompanySize.UNKNOWN


def _jalali_year_to_gregorian(raw_year) -> int | None:
    if raw_year in (None, ""):
        return None
    try:
        jalali_year = int(_normalize_digits(str(raw_year)))
    except ValueError:
        return None
    return jalali_year + _JALALI_TO_GREGORIAN_YEAR_OFFSET


class JobVisionNormalizer(BaseNormalizer):
    SITE_CODE = "jobvision"

    def normalize_job(self, raw: RawJobDTO) -> JobDTO:
        salary_min, salary_max = _parse_salary(raw.raw_salary)

        return JobDTO(
            source_code=raw.source_code,
            website_job_id=raw.website_job_id or "",
            source_url=raw.source_url,
            title=(raw.raw_title or "").strip(),
            company_name=raw.raw_company_name,
            category_name=raw.raw_category,
            sub_category_name=raw.raw_sub_category,
            employment_type_code=_EMPLOYMENT_TYPE_MAP.get(raw.raw_employment_type or ""),
            work_mode=_WORK_MODE_MAP.get(raw.raw_work_mode or "", WorkMode.UNKNOWN),
            experience_level=_EXPERIENCE_LEVEL_MAP.get(
                raw.raw_experience_level or "", ExperienceLevel.UNKNOWN
            ),
            education=_EDUCATION_MAP.get(raw.raw_education or "", EducationLevel.UNKNOWN),
            salary_min=salary_min,
            salary_max=salary_max,
            currency=Currency.IRT,
            province=raw.raw_province,
            city=raw.raw_city,
            gender=_map_gender(raw.raw_gender),
            military_status=_MILITARY_STATUS_MAP.get(
                raw.raw_military_status or "", MilitaryStatus.UNKNOWN
            ),
            description=raw.raw_description,
            responsibilities=raw.raw_responsibilities,
            requirements=raw.raw_requirements,
            benefits=raw.raw_benefits,
            technologies=raw.raw_technologies,
            skills=raw.raw_skills,
            languages=raw.raw_languages,
            published_at=_parse_iso_datetime_to_date(raw.raw_published_at),
            expires_at=_parse_iso_datetime_to_date(raw.raw_expires_at),
            status=_STATUS_MAP.get(raw.raw_status or "", JobStatus.UNKNOWN),
            scraped_at=datetime.now().astimezone(),
        )

    def normalize_company(self, raw: RawCompanyDTO) -> CompanyDTO:
        return CompanyDTO(
            source_code=raw.source_code,
            website_company_id=raw.website_company_id,
            source_url=raw.source_url,
            name=(raw.raw_name or "").strip(),
            industry=raw.raw_industry,
            description=raw.raw_description,
            company_size=_map_company_size(raw.raw_company_size),
            founded_year=_jalali_year_to_gregorian(raw.raw_founded_year),
            website=raw.raw_website,
            phone=raw.raw_phone,
            email=raw.raw_email,
            address=raw.raw_address,
            province=raw.raw_province,
            city=raw.raw_city,
            linkedin_url=raw.raw_linkedin_url,
            instagram_url=raw.raw_instagram_url,
            twitter_url=raw.raw_twitter_url,
            benefits=raw.raw_benefits,
            scraped_at=datetime.now().astimezone(),
        )
