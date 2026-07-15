"""
`JSONExporter` — writes the full, structured export (jobs + companies) to
a single JSON file per run.

A single combined file (not `jobs.json` + `companies.json` separately) is
the deliberate choice here: this platform's stated purpose is to become
the Data Ingestion Layer for a future AI/LLM system, and a single file
with both entities plus a metadata header (`exported_at`, `source`,
counts) is easier to hand to a downstream consumer as one artifact than
two files that must be correlated by the caller.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.logging import logger
from app.dto.company_export_dto import CompanyExportDTO
from app.dto.job_export_dto import JobExportDTO
from app.exporters.base_exporter import BaseExporter


class JSONExporter(BaseExporter):
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        jobs: list[JobExportDTO],
        companies: list[CompanyExportDTO],
        *,
        source_code: str,
    ) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"{source_code}_{timestamp}.json"

        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": source_code,
            "job_count": len(jobs),
            "company_count": len(companies),
            "jobs": [job.model_dump(mode="json") for job in jobs],
            "companies": [company.model_dump(mode="json") for company in companies],
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.bind(component="exporters.json").info(
            f"Exported {len(jobs)} job(s) + {len(companies)} company(ies) -> {output_path}"
        )
        return output_path
