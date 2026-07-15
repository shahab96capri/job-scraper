"""`CompanyValidator` — business-rule validation for `CompanyDTO`. See
`app/validators/job_validator.py` for the design rationale (source-
agnostic, no DB access, collects all violations before raising)."""

from __future__ import annotations

import re

from app.core.exceptions import ValidationFailedError
from app.dto.company_dto import CompanyDTO

MIN_NAME_LENGTH = 2
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CompanyValidator:
    def validate(self, dto: CompanyDTO) -> CompanyDTO:
        errors: list[str] = []

        if len(dto.name.strip()) < MIN_NAME_LENGTH:
            errors.append(f"name is too short: {dto.name!r}")

        if not dto.source_url.startswith("http"):
            errors.append(f"source_url is not an absolute URL: {dto.source_url!r}")

        if dto.email is not None and not _EMAIL_RE.match(dto.email):
            errors.append(f"email does not look valid: {dto.email!r}")

        if dto.website is not None and not dto.website.startswith("http"):
            errors.append(f"website is not an absolute URL: {dto.website!r}")

        if errors:
            raise ValidationFailedError(
                f"CompanyDTO failed validation ({dto.source_code}:{dto.name}): "
                f"{len(errors)} error(s)",
                field_errors=errors,
            )

        return dto
