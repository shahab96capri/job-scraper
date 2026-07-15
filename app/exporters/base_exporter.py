"""
`BaseExporter` — the abstract contract `JSONExporter`/`ExcelExporter`
implement. Both exports must use the unified `JobExportDTO`/
`CompanyExportDTO` objects (per spec), never read the ORM or database
directly — `main.py` is responsible for querying the Repository layer,
building export DTOs, and handing the same two lists to both exporters,
so JSON and Excel are always in sync with each other.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.dto.company_export_dto import CompanyExportDTO
from app.dto.job_export_dto import JobExportDTO


class BaseExporter(ABC):
    @abstractmethod
    def export(
        self,
        jobs: list[JobExportDTO],
        companies: list[CompanyExportDTO],
        *,
        source_code: str,
    ) -> Path:
        """Write `jobs`/`companies` to disk and return the output file path."""
