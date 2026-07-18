"""
`JobVisionParser` — verified against real, rendered HTML from
jobvision.ir (job detail x2, company profile x1, listing page x1;
provided by the user since this sandbox's `web_fetch`/`playwright` cannot
reach jobvision.ir — see Commit 4 notes in README).

**Key finding that shapes this whole parser**: JobVision is an Angular
Universal (SSR) app. Every job-detail and company-profile page embeds a
`<script id="ng-state" type="application/json">` block — Angular's
transfer-state cache of every API response the server made while
rendering the page. That JSON contains the *exact same structured data*
the page's own JavaScript renders into HTML (title, company, salary,
location, skills-with-proficiency, academic requirements, etc.), keyed by
the full API URL that produced it (e.g. `".../JobPost/Detail?jobPostId=
1409285"`).

Extracting that JSON is **far more robust than scraping the rendered
HTML**: it survives CSS/class-name redesigns entirely (a very common
scraper-breaking event) and gives typed, structured values (numeric
salary min/max, boolean `isRemote`, ISO datetimes) instead of formatted
Persian display strings that would need fragile regex parsing. This
parser therefore does not use BeautifulSoup CSS selectors at all for job/
company detail pages — only `extract_page_urls` (Commit 4's
`JobVisionSpider`, listing pages) uses selectors, because listing pages
were observed to NOT embed the full result set in `ng-state` (see that
module's docstring).

Per the architecture spec ("Parser only extracts raw values — no
conversion, no cleaning, no validation"), this class still returns only
`str`/`list[str]` fields on `RawJobDTO`/`RawCompanyDTO`: numeric/boolean
JSON values are converted to their *raw textual representation* (e.g.
`isRemote: true` -> `raw_work_mode="دورکاری"`) so the Normalizer's mapping
tables stay uniform across every site regardless of whether the raw
signal originally came from HTML text or a JSON boolean.
"""

from __future__ import annotations

import json
import re

from app.core.exceptions import ParsingError
from app.dto.raw_dto import RawCompanyDTO, RawJobDTO
from app.parsers.base_parser import BaseParser

_NG_STATE_RE = re.compile(
    r'<script id="ng-state" type="application/json">(.*?)</script>', re.DOTALL
)


def _extract_ng_state(html: str, *, source_url: str) -> dict:
    match = _NG_STATE_RE.search(html)
    if not match:
        raise ParsingError(
            f"No Angular <script id=\"ng-state\"> transfer-state block found on {source_url}. "
            f"Either the page didn't render fully (check Playwright wait conditions) or "
            f"JobVision has changed its rendering approach."
        )
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ParsingError(f"ng-state block on {source_url} is not valid JSON: {exc}") from exc


def _find_api_payload(state: dict, *, key_substring: str, source_url: str) -> dict:
    matching_keys = [k for k in state if key_substring in k]
    if not matching_keys:
        raise ParsingError(
            f"No ng-state entry containing {key_substring!r} found on {source_url}. "
            f"Available keys: {list(state.keys())}"
        )
    return state[matching_keys[0]]


def _titled(obj: dict | None) -> str | None:
    """Most JobVision lookup objects look like `{"titleFa": "...", ...}`."""
    if not obj:
        return None
    return obj.get("titleFa") or obj.get("title")


class JobVisionParser(BaseParser):
    SITE_CODE = "jobvision"

    def parse_job_page(self, html: str, *, source_url: str) -> RawJobDTO:
        state = _extract_ng_state(html, source_url=source_url)
        detail = _find_api_payload(state, key_substring="JobPost/Detail", source_url=source_url)

        company = detail.get("company") or {}
        location = detail.get("location") or {}
        salary = detail.get("salary")
        job_categories = detail.get("jobCategories") or []
        academic = detail.get("academicRequirements") or []
        software_reqs = detail.get("softwareRequirements") or []
        language_reqs = detail.get("languageRequirements") or []
        benefits = detail.get("benefits") or []

        company_link = company.get("companyLink")
        raw_company_url = f"https://jobvision.ir{company_link}" if company_link else None

        technologies = [
            _titled(req.get("software"))
            for req in software_reqs
            if _titled(req.get("software"))
        ]
        languages = [
            f"{_titled(req.get('language'))}-{_titled(req.get('skill'))}"
            for req in language_reqs
            if _titled(req.get("language"))
        ]

        return RawJobDTO(
            source_code=self.SITE_CODE,
            website_job_id=str(detail["id"]) if detail.get("id") is not None else None,
            source_url=source_url,
            raw_title=detail.get("title"),
            raw_company_name=_titled(company.get("brand")) or _titled(company.get("name")),
            raw_company_url=raw_company_url,
            raw_category=_titled(job_categories[0]) if job_categories else None,
            raw_sub_category=None,  # JobVision exposes only one flat category level
            raw_employment_type=_titled(detail.get("workType")),
            raw_work_mode="دورکاری" if detail.get("isRemote") else "حضوری",
            raw_experience_level=_titled(detail.get("seniorityLevel")),
            raw_education=_titled(academic[0].get("degreeLevel")) if academic else None,
            raw_salary=_titled(salary) if salary else None,
            raw_province=_titled(location.get("province")),
            raw_city=_titled(location.get("city")),
            raw_gender=_titled(detail.get("gender")),
            raw_military_status=(
                "الزامی" if detail.get("shouldDoneMilitaryService") else "غیرالزامی"
            ),
            raw_description=detail.get("description"),
            raw_responsibilities=None,  # bundled into description; see module docstring
            raw_requirements=None,
            raw_benefits=[b.get("titleFa") for b in benefits if b.get("titleFa")] or None,
            raw_technologies=technologies or None,
            raw_skills=technologies or None,
            raw_languages=languages or None,
            raw_published_at=(detail.get("activationTime") or {}).get("date"),
            raw_expires_at=(detail.get("expireTime") or {}).get("date"),
            raw_status="منقضی" if detail.get("isExpired") else "فعال",
        )

    def parse_company_page(self, html: str, *, source_url: str) -> RawCompanyDTO:
        state = _extract_ng_state(html, source_url=source_url)
        detail = _find_api_payload(state, key_substring="Company/Details", source_url=source_url)

        company_ref = detail.get("company") or {}
        industries = detail.get("industries") or []
        benefits = detail.get("benefits") or []

        return RawCompanyDTO(
            source_code=self.SITE_CODE,
            website_company_id=(
                str(company_ref["id"]) if company_ref.get("id") is not None else None
            ),
            source_url=source_url,
            raw_name=detail.get("brandsFa") or _titled(company_ref),
            raw_industry=_titled(industries[0]) if industries else None,
            raw_description=detail.get("descriptionFa"),
            raw_company_size=_titled(detail.get("companySize")),
            raw_founded_year=detail.get("establishmentYear"),
            raw_website=detail.get("websiteAddress"),
            raw_phone=None,  # not exposed by JobVision's public company payload
            raw_email=None,
            raw_address=None,
            raw_province=detail.get("provinceFa"),
            raw_city=detail.get("cityFa"),
            raw_linkedin_url=None,
            raw_instagram_url=None,
            raw_twitter_url=None,
            raw_benefits=[b.get("titleFa") for b in benefits if b.get("titleFa")] or None,
        )

    def parse_company_job_posts(self, html: str, *, source_url: str) -> list[RawJobDTO]:
        """Bonus source of job data: every company page embeds its own
        `JobPost/GetListOfCompanyJobPosts` payload — a flat list (capped at
        10 by the API, most-recent-first) of that company's job posts,
        **active and expired both**, each carrying an explicit
        `expireTime.isExpired` flag. This is the only place expired
        postings are discoverable at all, since the normal keyword/
        category search only ever returns active ones.

        Since we already download this exact page for company-profile
        data, this costs zero extra requests.

        Returned DTOs are intentionally partial: this summary payload
        does not include description/requirements/technologies/
        languages/education/military-status (those only exist on the
        job's own detail page). The Pipeline treats these as a fallback
        to use only if fetching the job's own detail page fails (common
        for expired postings) — see `JobIngestionPipeline`.
        """
        state = _extract_ng_state(html, source_url=source_url)
        matching_keys = [k for k in state if "JobPost/GetListOfCompanyJobPosts" in k]
        if not matching_keys:
            return []
        jobs = state[matching_keys[0]] or []

        results: list[RawJobDTO] = []
        for job in jobs:
            company = job.get("company") or {}
            location = job.get("location") or {}
            salary = job.get("salary")
            job_categories = job.get("jobCategories") or []
            benefits = job.get("benefits") or []
            properties = job.get("properties") or {}
            expire = job.get("expireTime") or {}
            activation = job.get("activationTime") or {}

            company_page_url = company.get("pageUrl")
            raw_company_url = f"https://jobvision.ir{company_page_url}" if company_page_url else None

            if job.get("id") is None:
                continue  # can't build a stable identity without this

            results.append(
                RawJobDTO(
                    source_code=self.SITE_CODE,
                    website_job_id=str(job["id"]),
                    source_url=source_url,  # placeholder — the Pipeline
                    # overwrites this with the job's own detail-page URL
                    # (or keeps this placeholder if that page never
                    # loads) before persisting.
                    raw_title=job.get("title"),
                    raw_company_name=company.get("nameFa") or company.get("nameEn"),
                    raw_company_url=raw_company_url,
                    raw_category=_titled(job_categories[0]) if job_categories else None,
                    raw_sub_category=None,
                    raw_employment_type=_titled(job.get("workType")),
                    raw_work_mode="دورکاری" if properties.get("isRemote") else "حضوری",
                    raw_experience_level=_titled(job.get("seniorityLevel")),
                    raw_education=None,  # not present in this summary payload
                    raw_salary=_titled(salary) if salary else None,
                    raw_province=_titled(location.get("province")),
                    raw_city=_titled(location.get("city")),
                    raw_gender=_titled(job.get("gender")),
                    raw_military_status=None,  # not present in this summary payload
                    raw_description=None,  # only on the job's own detail page
                    raw_responsibilities=None,
                    raw_requirements=None,
                    raw_benefits=[b.get("titleFa") for b in benefits if b.get("titleFa")] or None,
                    raw_technologies=None,  # only on the job's own detail page
                    raw_skills=None,
                    raw_languages=None,
                    raw_published_at=activation.get("date"),
                    raw_expires_at=expire.get("date"),
                    raw_status="منقضی" if expire.get("isExpired") else "فعال",
                )
            )
        return results
