"""
`JobRepository` — manages the `jobs` table plus its owned `job_skills`
association rows.

`sync_skills()` lives here (not in a separate `JobSkillRepository`) because
`JobSkill` rows have no independent lifecycle outside their parent `Job` —
they are part of the Job aggregate. Treating them as a separate top-level
repository would let calling code create orphaned `JobSkill` rows without
going through `Job`, which the domain model does not allow (a job skill
link is meaningless without the job).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dto.job_dto import JobDTO
from app.models.job import Job
from app.models.skill import JobSkill
from app.repositories.base_repository import BaseRepository


class JobRepository(BaseRepository[Job]):
    model = Job

    async def list_by_source_with_relations(self, source_id: uuid.UUID) -> list[Job]:
        """Return every `Job` for `source_id` with every relationship the
        Exporter layer needs already eager-loaded — `company`, `location`,
        `category`, `sub_category`, `employment_type`, `source`, and
        `skill_links.skill`.

        Deliberately separate from `get_by_source_and_website_id` (which
        only loads `skill_links`, all the Pipeline needs): the Exporter
        needs the *names* behind every foreign key (company name, city,
        category name, ...) to produce a flat, human-readable JSON/Excel
        row, whereas the Pipeline only ever works with IDs. Loading all of
        this eagerly here (instead of lazily per-row) avoids an N+1 query
        per exported job.
        """
        stmt = (
            select(Job)
            .where(Job.source_id == source_id)
            .options(
                selectinload(Job.company),
                selectinload(Job.location),
                selectinload(Job.category),
                selectinload(Job.sub_category),
                selectinload(Job.employment_type),
                selectinload(Job.source),
                selectinload(Job.skill_links).selectinload(JobSkill.skill),
            )
            .order_by(Job.scraped_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_source_and_website_id(
        self, source_id: uuid.UUID, website_job_id: str
    ) -> Job | None:
        stmt = (
            select(Job)
            .where(Job.source_id == source_id, Job.website_job_id == website_job_id)
            .options(selectinload(Job.skill_links))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_website_job_ids_by_source(self, source_id: uuid.UUID) -> set[str]:
        """Return every `website_job_id` already stored for this source.

        This is the read side of Incremental Crawling: the pipeline loads
        this set once before a crawl run and passes it to the spider, which
        can then stop paginating once a listing page yields nothing but
        already-known IDs, instead of re-walking every page of a site that
        hasn't meaningfully changed since the last run.
        """
        stmt = select(Job.website_job_id).where(Job.source_id == source_id)
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def upsert(
        self,
        dto: JobDTO,
        *,
        source_id: uuid.UUID,
        company_id: uuid.UUID | None,
        location_id: uuid.UUID | None,
        category_id: uuid.UUID | None,
        sub_category_id: uuid.UUID | None,
        employment_type_id: uuid.UUID | None,
    ) -> tuple[Job, bool]:
        """Create the job if unseen, otherwise update it in place.

        Returns `(job, created)` — `created` drives
        `ScrapeHistory.jobs_created` vs `jobs_updated` in the pipeline.
        """
        existing = await self.get_by_source_and_website_id(source_id, dto.website_job_id)

        field_values = dict(
            source_url=dto.source_url,
            title=dto.title,
            company_id=company_id,
            category_id=category_id,
            sub_category_id=sub_category_id,
            employment_type_id=employment_type_id,
            work_mode=dto.work_mode,
            experience_level=dto.experience_level,
            education=dto.education,
            salary_min=dto.salary_min,
            salary_max=dto.salary_max,
            currency=dto.currency,
            location_id=location_id,
            gender=dto.gender,
            military_status=dto.military_status,
            description=dto.description,
            responsibilities=dto.responsibilities,
            requirements=dto.requirements,
            benefits=dto.benefits or None,
            technologies=dto.technologies or None,
            languages=dto.languages or None,
            published_at=dto.published_at,
            expires_at=dto.expires_at,
            status=dto.status,
            scraped_at=dto.scraped_at,
        )

        if existing is not None:
            for field, value in field_values.items():
                setattr(existing, field, value)
            await self.session.flush()
            return existing, False

        job = Job(source_id=source_id, website_job_id=dto.website_job_id, **field_values)
        return await self.add(job), True

    async def sync_skills(
        self,
        job: Job,
        skill_assignments: list[tuple[uuid.UUID, bool, str | None, int]],
    ) -> None:
        """Reconcile the job's `job_skills` rows against the desired set.

        `skill_assignments` is a list of
        `(skill_id, is_required, proficiency_level, mention_count)` tuples,
        already resolved by `SkillRepository.get_or_create_many()` in the
        pipeline. Existing links not present in the new set are removed
        (the job posting no longer mentions that skill on re-crawl);
        existing links present in both are updated in place; new ones are
        inserted.

        Deliberately queries `JobSkill` directly (`select(...).where(...)`)
        instead of reading `job.skill_links` — under `AsyncSession`, an
        unloaded relationship attribute cannot be lazily accessed without
        an explicit `await session.refresh(...)` first; querying directly
        is simpler and keeps this repository's async behavior explicit.
        """
        existing_stmt = select(JobSkill).where(JobSkill.job_id == job.id)
        existing_result = await self.session.execute(existing_stmt)
        existing_by_skill_id = {link.skill_id: link for link in existing_result.scalars().all()}
        desired_skill_ids: set[uuid.UUID] = set()

        for skill_id, is_required, proficiency_level, mention_count in skill_assignments:
            desired_skill_ids.add(skill_id)
            link = existing_by_skill_id.get(skill_id)
            if link is not None:
                link.is_required = is_required
                link.proficiency_level = proficiency_level
                link.mention_count = mention_count
            else:
                self.session.add(
                    JobSkill(
                        job_id=job.id,
                        skill_id=skill_id,
                        is_required=is_required,
                        proficiency_level=proficiency_level,
                        mention_count=mention_count,
                    )
                )

        for skill_id, link in existing_by_skill_id.items():
            if skill_id not in desired_skill_ids:
                await self.session.delete(link)

        await self.session.flush()
