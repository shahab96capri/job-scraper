"""Aggregates DTOs for convenient imports elsewhere in the platform."""

from app.dto.base import PlatformBaseModel
from app.dto.company_dto import CompanyDTO
from app.dto.company_export_dto import CompanyExportDTO
from app.dto.job_dto import JobDTO
from app.dto.job_export_dto import JobExportDTO
from app.dto.raw_dto import RawCompanyDTO, RawJobDTO

__all__ = [
    "PlatformBaseModel",
    "CompanyDTO",
    "CompanyExportDTO",
    "JobDTO",
    "JobExportDTO",
    "RawCompanyDTO",
    "RawJobDTO",
]
