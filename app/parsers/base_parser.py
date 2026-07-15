"""
`BaseParser` — the abstract contract every site-specific parser
(Commit 4) implements.

Defined now (Commit 3) so `JobIngestionPipeline` can depend on this
*abstraction* rather than a concrete per-site parser (Dependency
Inversion) — the pipeline is fully wired and testable before a single
real site's HTML structure is implemented against.

Per the spec: "Parser only extracts raw values. No conversion. No
cleaning. No validation." — enforced at the type level by returning
`RawJobDTO`/`RawCompanyDTO`, whose fields are all raw, optional strings.

Method names (`parse_job_page` / `parse_company_page`) intentionally spell
out "page" to make it unambiguous these operate on a single rendered
HTML document, not a listing page (that's `BaseSpider.extract_page_urls`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.dto.raw_dto import RawCompanyDTO, RawJobDTO


class BaseParser(ABC):
    SITE_CODE: str

    @abstractmethod
    def parse_job_page(self, html: str, *, source_url: str) -> RawJobDTO:
        """Extract raw (uncleaned, unconverted) field values from a job
        detail page's HTML. `website_job_id` should be filled from the
        page itself when possible (more authoritative than a URL guess);
        the Pipeline falls back to a URL-derived ID if left `None`."""

    @abstractmethod
    def parse_company_page(self, html: str, *, source_url: str) -> RawCompanyDTO:
        """Extract raw field values from a company profile page's HTML."""
