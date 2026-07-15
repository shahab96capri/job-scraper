"""
`JobValidator` — business-rule validation for `JobDTO`, on top of the
structural/type validation Pydantic already performs at construction
(required fields, enum membership, salary_min <= salary_max, etc.).

Deliberately source-agnostic: unlike Parser/Normalizer, validation rules
here don't depend on which site the job came from, so a single concrete
class serves all four sites (no `BaseValidator` ABC / per-site subclass
needed, unlike Parser/Normalizer).

Deliberately has NO database access — checks like "does this
`employment_type_code` exist in the `employment_types` table" require a
repository and therefore belong to the Pipeline (which has DB access via
injected repositories), not here. This class only checks what can be
determined from the DTO's own fields.

Collects every violation before raising (rather than failing on the
first) so a single `ValidationFailedError.field_errors` list tells the
caller everything wrong with one job in one shot — useful both for the
`Error` table and for a human debugging a broken selector.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.exceptions import ValidationFailedError
from app.dto.job_dto import JobDTO

MIN_TITLE_LENGTH = 2
MAX_PUBLISH_DATE_FUTURE_SLACK_DAYS = 2
"""A publish date more than this far in the future is almost certainly a
parsing/normalization bug (e.g. a Persian calendar date converted wrong),
not a legitimately future-dated posting."""


class JobValidator:
    def validate(self, dto: JobDTO) -> JobDTO:
        errors: list[str] = []

        if len(dto.title.strip()) < MIN_TITLE_LENGTH:
            errors.append(f"title is too short: {dto.title!r}")

        if not dto.source_url.startswith("http"):
            errors.append(f"source_url is not an absolute URL: {dto.source_url!r}")

        if not dto.website_job_id.strip():
            errors.append("website_job_id is empty")

        if dto.salary_min is not None and dto.salary_min < 0:
            errors.append(f"salary_min is negative: {dto.salary_min}")
        if dto.salary_max is not None and dto.salary_max < 0:
            errors.append(f"salary_max is negative: {dto.salary_max}")

        if dto.published_at is not None:
            latest_plausible = date.today() + timedelta(days=MAX_PUBLISH_DATE_FUTURE_SLACK_DAYS)
            if dto.published_at > latest_plausible:
                errors.append(
                    f"published_at is implausibly far in the future: {dto.published_at}"
                )

        if errors:
            raise ValidationFailedError(
                f"JobDTO failed validation ({dto.source_code}:{dto.website_job_id}): "
                f"{len(errors)} error(s)",
                field_errors=errors,
            )

        return dto
