"""
Integration tests for the Repository layer (Commit 2), exercised against a
real PostgreSQL database (never mocked/sqlite — repositories emit
Postgres-specific SQL such as ARRAY columns and native ENUM types, so a
mock or a different dialect would not catch real regressions).

Requires `DATABASE_URL` in `.env` to point at a running, migrated
(`alembic upgrade head`) PostgreSQL instance. Intended to run in CI against
a disposable database container.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.database.session import get_db_session
from app.dto.company_dto import CompanyDTO
from app.dto.job_dto import JobDTO
from app.models.enums import CompanySize, Currency, JobStatus, LogLevel, ScrapeStatus, WorkMode
from app.models.error import ErrorStageEnum
from app.models.skill import JobSkill
from app.repositories import (
    CategoryRepository,
    CompanyRepository,
    EmploymentTypeRepository,
    ErrorRepository,
    JobRepository,
    LocationRepository,
    LogRepository,
    ScrapeHistoryRepository,
    SkillRepository,
    SourceRepository,
)

pytestmark = pytest.mark.asyncio


async def test_full_ingestion_flow_against_real_postgres():
    # Unique per invocation: this test runs against a real, persistent
    # PostgreSQL database (not a throwaway per-test DB), so fixed natural
    # keys would only be truly "created" on the very first run and every
    # `created is True` assertion below would fail on the second.
    suffix = uuid.uuid4().hex[:8]
    source_code = f"jobvision_test_{suffix}"
    emp_type_code = f"FULL_TIME_TEST_{suffix}"

    async with get_db_session() as session:
        source_repo = SourceRepository(session)
        location_repo = LocationRepository(session)
        category_repo = CategoryRepository(session)
        emp_type_repo = EmploymentTypeRepository(session)
        skill_repo = SkillRepository(session)
        company_repo = CompanyRepository(session)
        job_repo = JobRepository(session)
        history_repo = ScrapeHistoryRepository(session)
        log_repo = LogRepository(session)
        error_repo = ErrorRepository(session)

        # --- Source registration is idempotent ---
        source = await source_repo.get_or_create(
            code=source_code, name="JobVision", base_url="https://jobvision.ir"
        )
        source_again = await source_repo.get_or_create(
            code=source_code, name="JobVision", base_url="https://jobvision.ir"
        )
        assert source.id == source_again.id

        # --- Incremental crawling bookkeeping ---
        run = await history_repo.start_run(source.id)
        assert run.status == ScrapeStatus.RUNNING

        # --- Lookup tables: get_or_create must not create duplicates ---
        location = await location_repo.get_or_create("تهران", "تهران")
        location_dup = await location_repo.get_or_create("تهران", "تهران")
        assert location.id == location_dup.id

        category = await category_repo.get_or_create("برنامه‌نویسی و توسعه نرم‌افزار")
        sub_category = await category_repo.get_or_create(
            "برنامه‌نویس بک‌اند", parent_id=category.id
        )
        emp_type = await emp_type_repo.get_or_create(
            code=emp_type_code, label_fa="تمام‌وقت", label_en="Full-time"
        )

        # --- Company upsert: create then update-in-place ---
        company_dto = CompanyDTO(
            source_code=source_code,
            website_company_id=f"4245_{suffix}",
            source_url="https://jobvision.ir/companies/4245/x",
            name="نواویژن",
            industry="فناوری اطلاعات",
            company_size=CompanySize.SIZE_11_50,
            founded_year=2018,
            scraped_at=datetime.now(timezone.utc),
        )
        company, created = await company_repo.upsert(
            company_dto, source_id=source.id, location_id=location.id
        )
        assert created is True

        company_v2, created_v2 = await company_repo.upsert(
            company_dto.model_copy(update={"industry": "هوش مصنوعی"}),
            source_id=source.id,
            location_id=location.id,
        )
        assert created_v2 is False
        assert company_v2.id == company.id
        assert company_v2.industry == "هوش مصنوعی"

        # --- Job upsert + skill sync (add then remove) ---
        job_dto = JobDTO(
            source_code=source_code,
            website_job_id=f"1094514_{suffix}",
            source_url="https://jobvision.ir/jobs/1094514/x",
            title="Full-Stack Developer",
            work_mode=WorkMode.REMOTE,
            currency=Currency.IRT,
            salary_min=450_000_000,
            salary_max=600_000_000,
            technologies=["Django", "React", "PostgreSQL"],
            skills=["Django", "React", "PostgreSQL"],
            status=JobStatus.ACTIVE,
            scraped_at=datetime.now(timezone.utc),
        )
        job, job_created = await job_repo.upsert(
            job_dto,
            source_id=source.id,
            company_id=company.id,
            location_id=location.id,
            category_id=category.id,
            sub_category_id=sub_category.id,
            employment_type_id=emp_type.id,
        )
        assert job_created is True

        skills = await skill_repo.get_or_create_many(job_dto.skills)
        assert len(skills) == 3
        await job_repo.sync_skills(job, [(s.id, True, None, 1) for s in skills])

        await job_repo.sync_skills(job, [(s.id, True, None, 1) for s in skills[:2]])
        remaining = await session.execute(
            select(JobSkill).where(JobSkill.job_id == job.id)
        )
        assert len(remaining.scalars().all()) == 2

        # --- Log / Error repositories ---
        await log_repo.create(
            level=LogLevel.INFO,
            component="tests.integration",
            message="integration test log entry",
            source_id=source.id,
        )
        err = await error_repo.create(
            stage=ErrorStageEnum.PARSE,
            error_type="ParsingError",
            message="integration test error entry",
            url="https://jobvision.ir/jobs/999/broken",
            source_id=source.id,
        )
        unresolved = await error_repo.get_unresolved()
        assert any(e.id == err.id for e in unresolved)
        await error_repo.mark_resolved(err)

        # --- Scrape history completion + incremental-crawl lookup ---
        await history_repo.finish_run(
            run,
            status=ScrapeStatus.SUCCESS,
            pages_crawled=1,
            jobs_found=1,
            jobs_created=1,
            companies_created=1,
        )
        last_success = await history_repo.get_last_successful_run(source.id)
        assert last_success is not None
        assert last_success.id == run.id
