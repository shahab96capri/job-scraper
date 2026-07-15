"""
`BaseNormalizer` — the abstract contract every site-specific normalizer
(Commit 4) implements: mapping a site's raw extracted text onto the
platform's standard values (enums, cleaned strings, parsed numbers/dates).

Example: Jobinja's raw work-mode text "دورکاری" and JobVision's
"کار از راه دور" both normalize to `WorkMode.REMOTE`. That per-site mapping
table lives in the concrete subclass; this base class only fixes the
input/output contract (`RawJobDTO` -> `JobDTO`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.dto.job_dto import JobDTO
from app.dto.company_dto import CompanyDTO
from app.dto.raw_dto import RawCompanyDTO, RawJobDTO


class BaseNormalizer(ABC):
    SITE_CODE: str

    @abstractmethod
    def normalize_job(self, raw: RawJobDTO) -> JobDTO:
        """Map a `RawJobDTO` onto the platform's standard `JobDTO`."""

    @abstractmethod
    def normalize_company(self, raw: RawCompanyDTO) -> CompanyDTO:
        """Map a `RawCompanyDTO` onto the platform's standard `CompanyDTO`."""
