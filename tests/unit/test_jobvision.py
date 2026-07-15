"""
Unit tests for the JobVision Parser/Normalizer/Spider (Commit 4), run
against **real, rendered HTML** captured from jobvision.ir by the user
(this sandbox cannot reach jobvision.ir directly — see README).

These are the strongest kind of test available for this layer: no fakes,
no fixtures invented from assumptions — the actual bytes JobVision served
for two job postings, one company profile, and one 30-result listing page.
If JobVision changes its embedded `ng-state` JSON schema or listing-page
CSS classes, these tests are exactly what would catch it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.models.enums import (
    CompanySize,
    Gender,
    JobStatus,
    MilitaryStatus,
    WorkMode,
)
from app.normalizers.jobvision_normalizer import JobVisionNormalizer
from app.parsers.jobvision_parser import JobVisionParser
from app.spiders.jobvision_spider import JobVisionSpider

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "jobvision"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestJobVisionParser:
    def test_parses_job_1_core_fields(self):
        html = _read_fixture("job_detail_1.html")
        parser = JobVisionParser()

        raw = parser.parse_job_page(
            html,
            source_url="https://jobvision.ir/jobs/1409285/some-slug",
        )

        assert raw.website_job_id == "1409285"
        assert raw.raw_title == "برنامه‌نویس - خانم"
        assert raw.raw_company_name == "فرا سامانه//همکاران سیستم"
        assert raw.raw_company_url == "https://jobvision.ir/companies/17161/استخدام-فرا-سامانه--همکاران-سیستم"
        assert raw.raw_employment_type == "تمام وقت"
        assert raw.raw_work_mode == "حضوری"  # isRemote was False
        assert raw.raw_gender == "فقط خانم"
        assert raw.raw_military_status == "غیرالزامی"  # shouldDoneMilitaryService False
        assert raw.raw_salary == "45 - 60 میلیون تومان"
        assert raw.raw_province == "تهران"
        assert raw.raw_status == "فعال"  # isExpired False
        assert raw.raw_published_at == "2026-06-22T12:42:42"
        assert "Angular" in (raw.raw_technologies or [])

    def test_parses_job_2_differs_correctly(self):
        html = _read_fixture("job_detail_2.html")
        parser = JobVisionParser()

        raw = parser.parse_job_page(
            html, source_url="https://jobvision.ir/jobs/1431022/other-slug"
        )

        assert raw.raw_title == "برنامه‌نویس فرانت‌اند (Front-end Developer)"
        assert raw.raw_gender == "ترجیحاً آقا"
        assert raw.raw_military_status == "الزامی"  # shouldDoneMilitaryService True
        assert raw.raw_salary is None  # negotiable, no salary object in source JSON
        assert "React" in (raw.raw_technologies or [])
        assert "VueJS" in (raw.raw_technologies or [])

    def test_parses_company_profile(self):
        html = _read_fixture("company_profile.html")
        parser = JobVisionParser()

        raw = parser.parse_company_page(
            html, source_url="https://jobvision.ir/companies/17161/x"
        )

        assert raw.website_company_id == "17161"
        assert raw.raw_name == "فرا سامانه//همکاران سیستم"
        assert raw.raw_company_size == "11 تا 50 نفر"
        assert raw.raw_founded_year == "1382"  # raw string, unconverted (Parser layer)
        assert raw.raw_province == "تهران"
        assert raw.raw_city == "تهران"


class TestJobVisionNormalizer:
    def test_normalizes_job_1_end_to_end(self):
        raw = JobVisionParser().parse_job_page(
            _read_fixture("job_detail_1.html"),
            source_url="https://jobvision.ir/jobs/1409285/x",
        )
        dto = JobVisionNormalizer().normalize_job(raw)

        assert dto.employment_type_code == "FULL_TIME"
        assert dto.work_mode == WorkMode.ON_SITE
        assert dto.gender == Gender.FEMALE
        assert dto.military_status == MilitaryStatus.NOT_REQUIRED
        assert dto.status == JobStatus.ACTIVE
        assert dto.salary_min == Decimal("45000000")
        assert dto.salary_max == Decimal("60000000")
        assert dto.published_at is not None
        assert dto.published_at.isoformat() == "2026-06-22"

    def test_normalizes_job_2_negotiable_salary_and_male_gender(self):
        raw = JobVisionParser().parse_job_page(
            _read_fixture("job_detail_2.html"),
            source_url="https://jobvision.ir/jobs/1431022/x",
        )
        dto = JobVisionNormalizer().normalize_job(raw)

        assert dto.salary_min is None
        assert dto.salary_max is None
        assert dto.gender == Gender.MALE  # "ترجیحاً آقا" contains "آقا", not "خانم"
        assert dto.military_status == MilitaryStatus.COMPLETED

    def test_normalizes_company_profile_jalali_year_converted(self):
        raw = JobVisionParser().parse_company_page(
            _read_fixture("company_profile.html"),
            source_url="https://jobvision.ir/companies/17161/x",
        )
        dto = JobVisionNormalizer().normalize_company(raw)

        assert dto.company_size == CompanySize.SIZE_11_50
        # 1382 (Jalali) + 621 offset = 2003 (Gregorian, approximate)
        assert dto.founded_year == 2003


class TestJobVisionSpiderListingExtraction:
    def test_build_listing_url_uses_verified_page_query_param(self):
        # Locks in the pagination format the user confirmed by hand on
        # 2026-07-14 (navigating ?page=1 vs ?page=2 in a real browser
        # returned different job listings) — regression guard against
        # accidentally reverting to an unverified guess.
        spider = JobVisionSpider(downloader=None, max_pages=1, keyword="برنامه نویس اندروید")

        assert spider.build_listing_url(1) == (
            "https://jobvision.ir/jobs/keyword/برنامه نویس اندروید?page=1"
        )
        assert spider.build_listing_url(2) == (
            "https://jobvision.ir/jobs/keyword/برنامه نویس اندروید?page=2"
        )

    def test_extracts_30_job_urls_from_real_listing_page(self):
        html = _read_fixture("listing_page.html")
        spider = JobVisionSpider(downloader=None, max_pages=1)  # downloader unused here

        result = spider.extract_page_urls(html)

        assert len(result.job_urls) == 30
        assert all(url.startswith("https://jobvision.ir/jobs/") for url in result.job_urls)
        # Tracking query params (row, searchId, score, ...) must be stripped.
        assert all("?" not in url for url in result.job_urls)

    def test_extracted_company_urls_are_absolute_and_deduplicated(self):
        html = _read_fixture("listing_page.html")
        spider = JobVisionSpider(downloader=None, max_pages=1)

        result = spider.extract_page_urls(html)

        assert len(result.company_urls) == len(set(result.company_urls))
        assert all(url.startswith("https://jobvision.ir/companies/") for url in result.company_urls)
