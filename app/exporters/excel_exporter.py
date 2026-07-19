"""
`ExcelExporter` — writes jobs + companies to a single `.xlsx` workbook,
one sheet per entity, using the same `JobExportDTO`/`CompanyExportDTO`
input as `JSONExporter` (never re-reads the database).

Excel cells cannot hold Python lists (`benefits`, `skills`,
`technologies`, `languages` are `list[str]` on the DTOs) — `_flatten_row`
joins them with `" | "` before handing rows to pandas. This is presentation
flattening for spreadsheet consumption only; the JSON export keeps the
real list structure intact for programmatic (AI/LLM) consumers, matching
the platform's stated purpose.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.utils import get_column_letter

from app.core.logging import logger
from app.dto.company_export_dto import CompanyExportDTO
from app.dto.job_export_dto import JobExportDTO
from app.exporters.base_exporter import BaseExporter

_LIST_JOIN_SEPARATOR = " | "


def _flatten_row(dto_dict: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in dto_dict.items():
        if isinstance(value, list):
            flat[key] = _LIST_JOIN_SEPARATOR.join(str(v) for v in value) if value else ""
        else:
            flat[key] = value
    return flat


class ExcelExporter(BaseExporter):
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
        output_path = self.output_dir / f"{source_code}_{timestamp}.xlsx"

        jobs_rows = [_flatten_row(job.model_dump(mode="json")) for job in jobs]
        companies_rows = [_flatten_row(c.model_dump(mode="json")) for c in companies]

        jobs_df = pd.DataFrame(jobs_rows)
        companies_df = pd.DataFrame(companies_rows)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            jobs_df.to_excel(writer, index=False, sheet_name="Jobs")
            companies_df.to_excel(writer, index=False, sheet_name="Companies")
            for sheet_name, df in (("Jobs", jobs_df), ("Companies", companies_df)):
                worksheet = writer.sheets[sheet_name]
                worksheet.sheet_view.rightToLeft = True
                worksheet.freeze_panes = "A2"
                for i, col in enumerate(df.columns, start=1):
                    max_len = max(
                        [len(str(col))] + [len(str(v)) for v in df[col].astype(str)]
                    )
                    column_letter = get_column_letter(i)
                    worksheet.column_dimensions[column_letter].width = min(max_len + 2, 60)

        logger.bind(component="exporters.excel").info(
            f"Exported {len(jobs)} job(s) + {len(companies)} company(ies) -> {output_path}"
        )
        return output_path
