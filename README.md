# Iran Job Intelligence Platform

Modular data collection & knowledge extraction platform. Data Ingestion Layer
for a future AI-powered Interview Preparation Platform.

## Architecture

```
Spider → Downloader → HTML → Parser → DTO → Normalizer → Validator
       → Pipeline → Repository → Database → Export (JSON / Excel)
```

Layers are strictly separated:

| Layer | Responsibility | May touch DB? | May touch HTTP? |
|---|---|---|---|
| Spider | Navigate pages, yield raw HTML | No | Yes (via Downloader) |
| Parser | Extract raw values from HTML | No | No |
| Normalizer | Map raw values → standard platform values | No | No |
| Validator | Validate DTOs | No | No |
| Pipeline | Orchestrate dedup/update/persist/export | No (delegates) | No |
| Repository | **Only** layer allowed to speak SQLAlchemy | Yes | No |
| Exporter | Produce JSON/Excel from unified DTOs | No | No |

## Tech Stack

Python 3.12 · Playwright · BeautifulSoup4 · lxml · SQLAlchemy 2.0 (async) ·
Alembic · PostgreSQL · Pydantic v2 · Pandas · OpenPyXL · Loguru · Typer

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env   # then edit DATABASE_URL / DATABASE_URL_SYNC
```

PostgreSQL only — SQLite is intentionally rejected by `Settings` validation.

## Publishing to GitHub

```bash
cd job-scraper
git init
git add .
git commit -m "Commit 1-5: foundation through JobVision end-to-end"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

`.gitignore` already excludes `.env` (real secrets), `__pycache__/`,
`.pytest_cache/`, generated `output/json/*` and `output/excel/*` export
files, and `logs/*.log` — only `.env.example` (safe placeholder values)
and empty-directory `.gitkeep` markers are committed from those paths.
**Before pushing, double check `git status` does not show a real `.env`
file** — if it does, `.gitignore` was added after `.env` was already
tracked; run `git rm --cached .env` first.

## Commit Log

### Commit 1 — Foundation: Config, Logging, Exceptions, Database, Models

**Files added**
```
app/config/settings.py
app/core/logging.py
app/core/exceptions.py
app/database/base.py
app/database/mixins.py
app/database/session.py
app/models/enums.py
app/models/source.py
app/models/location.py
app/models/category.py
app/models/employment_type.py
app/models/skill.py          (Skill + JobSkill)
app/models/company.py
app/models/job.py
app/models/scrape_history.py
app/models/log.py
app/models/error.py
app/models/__init__.py
requirements.txt
.env.example
README.md
```

**Architectural decisions**

- **Config Singleton**: `Settings` (Pydantic v2 `BaseSettings`) is the *only*
  module allowed to read environment variables, exposed via
  `get_settings()` cached with `lru_cache(maxsize=1)`. Rejects any
  non-PostgreSQL `DATABASE_URL` at startup — fail fast, not at first query.
- **Database Session Singleton**: `get_engine()` / `get_sessionmaker()` are
  process-wide singletons (one connection pool per process), but
  `AsyncSession` instances themselves are created fresh per unit of work via
  `get_db_session()`, since `AsyncSession` is not safe to share across
  concurrent asyncio tasks. Repositories (Commit 2) receive a session via
  constructor injection — they never manage session lifecycle themselves.
- **Exception hierarchy** mirrors the pipeline stages 1:1
  (`CrawlError` → `ParsingError` → `NormalizationError` →
  `ValidationFailedError` → `RepositoryError` → `ExportError`), with
  `TransientCrawlError` vs `PermanentCrawlError` as the axis the retry
  system (Commit 3) branches on.
- **UUID surrogate keys everywhere** (`UUIDPrimaryKeyMixin`) — the
  website-specific ID is stored separately (`website_job_id`,
  `website_company_id`) so merging unlimited future sources never causes a
  primary-key collision.
- **`(source_id, website_job_id)` / `(source_id, website_company_id)`**
  unique constraints are the natural key duplicate detection (Commit 3)
  is built on — not fuzzy title/name matching.
- **Category self-reference** (`parent_id`) models category + sub-category
  with one table instead of two, and gives the future Knowledge Graph
  feature a tree to walk directly.
- **`JobSkill` as an explicit association entity** (not a bare M2M table)
  because it already needs `is_required` / `proficiency_level` /
  `mention_count` — attributes an implicit relationship table can't hold.
- **`technologies` (raw) vs `skills` (normalized, via `JobSkill`)** are kept
  as two separate signals on `Job` so normalization logic can be improved
  and re-run later without having destroyed the original extracted values.
- **`Log` vs `Error`** are separate tables: `Log` is a small, curated set of
  lifecycle events (queryable via SQL for a future dashboard); `Error` is
  every failure that survived the retry system, scoped to a pipeline stage
  and usually a URL, with a `resolved` flag.

**Verification performed**
- All 11 tables register cleanly on `Base.metadata` (`categories`,
  `employment_types`, `locations`, `skills`, `sources`, `companies`,
  `errors`, `logs`, `scrape_history`, `jobs`, `job_skills`).
- `Settings`, `configure_logging()`, exception imports, and both database
  singletons (`get_engine`, `get_sessionmaker`) verified via smoke test —
  singleton identity confirmed (`get_engine() is get_engine() == True`).

**Not yet implemented (upcoming commits)**
- Commit 2: Alembic migration environment + initial migration; Pydantic
  DTOs (`app/dto/`); Repository layer (`app/repositories/`).
- Commit 3: `BaseSpider` (Playwright-driven downloader with retry/backoff,
  browser singleton), pipeline orchestration, incremental crawling logic.
- Commit 4: Per-site Parsers + Normalizers (JobVision, Jobinja, IranTalent,
  Ponisha) + Validators.
- Commit 5: Exporters (JSON/Excel from unified DTOs) + `main.py` (Typer CLI)
  wiring the full pipeline end-to-end.

Each commit builds strictly on top of this one; nothing above will be
redesigned unless a later commit surfaces a genuine defect in it.

### Commit 2 — Alembic Migrations, DTO Layer, Repository Layer

**Files added**
```
alembic.ini
migrations/env.py
migrations/script.py.mako
migrations/versions/f224cee79cb9_initial_schema.py
app/dto/base.py
app/dto/raw_dto.py            (RawJobDTO + RawCompanyDTO)
app/dto/job_dto.py
app/dto/company_dto.py
app/repositories/base_repository.py
app/repositories/source_repository.py
app/repositories/location_repository.py
app/repositories/category_repository.py
app/repositories/employment_type_repository.py
app/repositories/skill_repository.py
app/repositories/company_repository.py
app/repositories/job_repository.py
app/repositories/scrape_history_repository.py
app/repositories/log_repository.py
app/repositories/error_repository.py
app/repositories/__init__.py
tests/integration/test_repositories.py
pytest.ini
```

**Files modified**
```
app/models/company.py   — scraped_at was missing timezone=True, inconsistent
                           with Job.scraped_at; caused a real asyncpg
                           DataError on insert (see Verification below).
```

**Architectural decisions**

- **Alembic wired to the platform's own `Settings` singleton**
  (`migrations/env.py` calls `get_settings().database_url_sync`) instead of
  a URL duplicated in `alembic.ini` — `.env` stays the single source of
  truth. Migrations run over the **sync** driver (psycopg2); the async
  driver (asyncpg) is reserved for the running application, since
  Alembic's autogenerate machinery is built around sync connections and
  migrations are a one-shot CLI operation, not a concurrent request path.
- **Raw DTOs vs Domain DTOs**: `RawJobDTO`/`RawCompanyDTO` (`raw_dto.py`)
  are frozen, all-`Optional[str]` containers — the exact Parser output
  contract, enforcing "no conversion/cleaning/validation in the Parser" at
  the type level. `JobDTO`/`CompanyDTO` are the normalized, typed contract
  used from the Normalizer onward — real Enums (`WorkMode`, `Currency`,
  ...) plus structural validators (salary_min ≤ salary_max, expires_at ≥
  published_at), but deliberately **no foreign-key UUIDs** — the
  Normalizer has no DB access, so DTOs carry normalized *names*
  (`company_name`, `category_name`, `province`/`city`); resolving those to
  actual FK rows is the Repository/Pipeline's job.
- **Repository layer is the only SQLAlchemy-aware layer.** `BaseRepository`
  is generic over `ModelType` and centralizes `get_by_id`/`add`/`delete`/
  `count`. Sessions are constructor-injected, never opened/closed by a
  repository — that stays `get_db_session()`'s responsibility, which is
  what lets a Pipeline compose several repositories into one atomic
  transaction later.
- **`get_or_create` on every lookup repository** (Source, Location,
  Category, EmploymentType, Skill) is the mechanism that lets the platform
  "support unlimited future websites": registering a new source, city, or
  skill is a data row, never a migration.
- **`upsert()` on Company/Job repositories** implements Duplicate Detection
  + Update Detection: looked up by the `(source_id, website_*_id)` natural
  key first (falling back to `(source_id, name)` for companies whose site
  doesn't expose a stable ID); if found, fields are updated in place — no
  duplicate row is ever created on re-crawl.
- **`JobRepository.sync_skills()`** reconciles `job_skills` against a
  desired set on every re-crawl, so a skill removed from a re-edited
  posting doesn't leave a stale `JobSkill` link behind.

**Verification performed (against a real, disposable PostgreSQL 16
instance — not mocked, not SQLite)**
- `alembic revision --autogenerate` correctly detected all 11 tables from
  `app.models`.
- Full `upgrade head` → `downgrade base` → `upgrade head` cycle tested and
  made idempotent: autogenerate's default downgrade does **not** drop
  PostgreSQL's named `ENUM` types when it drops the columns/tables that use
  them, so a second `upgrade` after `downgrade` failed with `type
  "company_size_enum" already exists`. Fixed by adding explicit
  `postgresql.ENUM(name=...).drop(bind, checkfirst=True)` calls for all 11
  enum types in the migration's `downgrade()`.
- `tests/integration/test_repositories.py` (real `pytest` run, not just
  imports) covers: idempotent `get_or_create` on Source/Location; Company
  upsert create-then-update-in-place (verifies no duplicate row); Job
  upsert create; `sync_skills` add-then-remove (verifies a dropped skill's
  `JobSkill` row is actually deleted, not left stale); Log/Error
  repositories; `ScrapeHistory.start_run`/`finish_run`/
  `get_last_successful_run` (the incremental-crawling read path).
- Found and fixed a real bug during this verification: `Company.scraped_at`
  was `DateTime()` (naive) while `Job.scraped_at` was
  `DateTime(timezone=True)` — inserting a timezone-aware Python `datetime`
  into the naive column raised `asyncpg.exceptions.DataError: can't
  subtract offset-naive and offset-aware datetimes`. Fixed in the model
  and regenerated the (still-unreleased) initial migration.

**Not yet implemented (upcoming commits)**
- Commit 3: `BaseSpider` (Playwright-driven downloader with retry/backoff,
  browser singleton), pipeline orchestration, incremental crawling logic.
- Commit 4: Per-site Parsers + Normalizers (JobVision, Jobinja, IranTalent,
  Ponisha) + Validators.
- Commit 5: Exporters (JSON/Excel from unified DTOs) + `main.py` (Typer CLI)
  wiring the full pipeline end-to-end.

### Commit 3 — BaseSpider, Downloader, Browser Singleton, Retry System, Pipeline Orchestration

**Files added**
```
app/core/browser.py
app/spiders/downloader.py
app/spiders/base_spider.py
app/parsers/base_parser.py
app/normalizers/base_normalizer.py
app/validators/job_validator.py
app/validators/company_validator.py
app/pipelines/job_pipeline.py
tests/conftest.py
tests/unit/test_downloader_retry.py
tests/integration/test_job_pipeline.py
```

**Files modified**
```
app/repositories/job_repository.py  — added list_website_job_ids_by_source()
                                       (Incremental Crawling read path)
app/spiders/downloader.py           — added retry_count property (surfaced
                                       into ScrapeHistory.retry_count)
app/spiders/base_spider.py          — added pages_fetched counter (surfaced
                                       into ScrapeHistory.pages_crawled)
```

**Architectural decisions**

- **Browser Singleton**: one Playwright `Browser` process per application
  process (`app/core/browser.py`), guarded by an `asyncio.Lock` for
  double-checked-locking-safe concurrent creation. Every spider run gets
  its own isolated `BrowserContext` from `new_context()` — the process is
  shared (expensive to launch), contexts are not (must not leak
  cookies/state between concurrent spiders).
- **Retry system lives in exactly one place**: `Downloader.fetch_html()`,
  used by every spider regardless of site. `tenacity.AsyncRetrying` is
  built per-call from `Settings` (not a static decorator) so retry count/
  backoff are runtime-configurable and trivially overridable in tests.
  Exception classification (`TransientCrawlError` vs `PermanentCrawlError`
  vs `RateLimitedError`) happens once, here, and only `Transient*` is
  retried — **the exact bug this project's Commit-1 scraper hit (HTTP 403
  on all four target sites with a bare `requests` client) is the reason a
  real, fingerprinted browser context exists at all**; whether that's
  sufficient against a given site's bot detection can only be confirmed
  by running this against the real sites outside this sandbox (see
  Verification below).
- **`BaseSpider` never touches SQL, exports, or Playwright directly** — it
  only knows how to build a listing URL and extract links from listing
  HTML; everything else (pagination control flow, incremental stop logic)
  is handled once in the base class so no per-site spider duplicates it.
- **`BaseParser`/`BaseNormalizer` are abstractions, not implementations.**
  Commit 4 will subclass them per site. `JobIngestionPipeline` depends on
  these abstractions (Dependency Inversion) — proven by this commit's
  integration test, which runs the *real* pipeline against *fake*
  spider/parser/normalizer implementations and a *real* Postgres database.
- **`JobValidator`/`CompanyValidator` are concrete, not abstract** — unlike
  Parser/Normalizer, validation rules (title length, URL shape, salary
  sign, plausible dates) don't vary per source, so one implementation
  serves all four sites. They collect every violation before raising
  (`ValidationFailedError.field_errors`), and have no database access by
  design — DB-dependent checks belong to the Pipeline.
- **Per-job error isolation in the Pipeline**: a crawl/parse/normalize/
  validate/persist failure for *one* job is caught, classified by
  exception type into an `ErrorStageEnum`, written to the `Error` table,
  and the run continues — a single broken selector must not lose an
  entire run's worth of otherwise-good data. `ScrapeHistory.status`
  becomes `PARTIAL_SUCCESS` (not `FAILED`) when some jobs succeed despite
  errors, `FAILED` only if literally nothing was found and errors
  occurred.
- **Company resolution degrades gracefully**: the Pipeline prefers a full
  company-page crawl when the Parser found a company URL, but falls back
  to a name-only `Company` row (looked up by `(source_id, name)` to avoid
  duplicates) when it didn't — a job should never be dropped just because
  its company page couldn't be reached.

**Verification performed**
- **Unit tests** (`tests/unit/test_downloader_retry.py`, 8 tests, no real
  browser/network): exercise every branch of `Downloader`'s exception
  classification and retry logic against a minimal fake `BrowserContext`/
  `Page` — success-first-try, transient-5xx-then-succeeds, retries-
  exhausted, 404-never-retried, 429-retried-as-transient, Playwright
  timeout/network-error-retried, page-always-closed-on-failure.
- **Integration test** (`tests/integration/test_job_pipeline.py`, against
  real PostgreSQL): a fake `BaseSpider`/`BaseParser`/`BaseNormalizer`
  drives the real `JobIngestionPipeline` + real Repositories through a
  3-job fixture (2 valid, 1 deliberately invalid) — asserts correct
  `jobs_found`/`jobs_created`/`error_count`/`ScrapeStatus.PARTIAL_SUCCESS`,
  that the invalid job was never persisted, that a job with a company URL
  gets a fully-crawled `Company` while a job without one falls back to the
  *same* name-matched company row (no duplicate), and that re-running the
  pipeline against unchanged data is a pure update pass (0 created, 2
  updated) — proving Update/Duplicate Detection end to end.
- Found and fixed two real bugs during this verification:
  1. `AsyncRetrying` had no `retry=` predicate, so it retried on **every**
     exception including `PermanentCrawlError` (e.g. HTTP 404) — a 404
     was retried `max_retries` times before failing instead of failing
     immediately. Fixed with
     `retry=retry_if_exception_type(TransientCrawlError)`.
  2. Running the full test suite together (not just one file at a time)
     surfaced two cross-test issues against the shared, persistent
     Postgres instance: (a) the process-wide engine singleton bound to one
     test's event loop broke a later test's asyncpg connections
     ("attached to a different loop"); (b) hardcoded natural keys
     (`source_code`, `website_job_id`, etc.) meant a second run of the
     *same* test against the *same* persistent database observed
     leftover rows from the first run and asserted the wrong `created`
     flags. Fixed respectively with an autouse `conftest.py` fixture that
     rebuilds the engine singleton fresh per test function, and by
     deriving every natural key in both integration tests from a
     `uuid.uuid4()` suffix generated at test-call time. Verified by
     running the full suite twice in a row with no database reset between
     runs — both runs pass identically.
- **What was explicitly NOT verified in this sandbox**: real navigation
  against JobVision/Jobinja/IranTalent/Ponisha. This project's Playwright
  Chromium binary could not be downloaded here (network egress is
  restricted to package registries; Playwright's browser CDN is not
  allow-listed), so live-site behavior — including whether the
  fingerprinted browser context actually gets past the HTTP 403 seen in
  Commit 1 — can only be confirmed by running `playwright install
  chromium` and a real spider (Commit 4) outside this sandbox.

**Not yet implemented (upcoming commits)**
- Commit 4: Per-site Parsers + Normalizers (JobVision, Jobinja, IranTalent,
  Ponisha) implementing `BaseParser`/`BaseNormalizer` against each site's
  real HTML — this is where live-site verification (403 handling
  included) finally happens.
- Commit 5: Exporters (JSON/Excel from unified DTOs) + `main.py` (Typer CLI)
  wiring the full pipeline end-to-end.

### Commit 4 — JobVision Parser, Normalizer, Spider (real-HTML verified)

**Files added**
```
app/parsers/jobvision_parser.py
app/normalizers/jobvision_normalizer.py
app/spiders/jobvision_spider.py
tests/fixtures/jobvision/job_detail_1.html      (real HTML, provided by user)
tests/fixtures/jobvision/job_detail_2.html      (real HTML, provided by user)
tests/fixtures/jobvision/company_profile.html   (real HTML, provided by user)
tests/fixtures/jobvision/listing_page.html      (real HTML, provided by user)
tests/unit/test_jobvision.py                    (8 tests against the above)
```

**Why this commit looks different from Commits 1–3**: this sandbox cannot
reach jobvision.ir (robots.txt blocks even individual job-detail URLs, not
just listing pages — confirmed by direct `web_fetch` attempts before this
commit) and cannot download a Chromium binary (network egress restricted
to package registries). So instead of guessing selectors, the user
fetched four real pages directly from their own browser (View Source /
Copy outerHTML) and provided them. Every selector and JSON key below is
verified against those real files, not inferred.

**The key architectural finding: JobVision embeds structured JSON, so this
parser does not scrape CSS classes for job/company detail pages at all.**
JobVision is an Angular Universal (SSR) app. Every job-detail and
company-profile page includes a `<script id="ng-state" type=
"application/json">` block — Angular's transfer-state cache of the exact
API responses (`.../JobPost/Detail?jobPostId=...`, `.../Company/Details?
companyId=...`) used to render the page. `JobVisionParser` extracts that
JSON directly instead of walking the rendered DOM. This is a strictly
better strategy than CSS scraping: it's immune to visual redesigns, and it
hands over already-typed values (numeric salary min/max, boolean
`isRemote`, ISO datetimes, a controlled-vocabulary skills list with
proficiency levels) instead of formatted Persian strings that would need
fragile regex parsing. The **listing page** does not embed the full result
set this way (only the single job shown in the desktop detail pane), so
`JobVisionSpider.extract_page_urls` does use BeautifulSoup against the
verified `a.desktop-job-card` structure for that one page type.

**Architectural decisions**

- **Parser stays "dumb" even when the source is already-structured JSON.**
  Numeric/boolean JSON values (`isRemote: true`, `shouldDoneMilitaryService:
  false`) are converted to their *raw textual* Persian representation
  (`"دورکاری"`, `"غیرالزامی"`) before being placed on `RawJobDTO`, rather
  than passed through as Python `bool`/`int`. This keeps the Parser/
  Normalizer boundary meaningful (Parser: zero interpretation, even of
  typed data; Normalizer: all interpretation) and keeps the Normalizer's
  mapping-table shape identical whether the raw signal originated from
  HTML text (future sites) or a JSON boolean (JobVision) — one mental
  model for every site's Normalizer.
- **`founded_year` is Jalali, not Gregorian.** JobVision reports
  `establishmentYear` in the Iranian solar Hijri calendar (`"1382"`).
  `JobVisionNormalizer` converts it with a documented approximate `+621`
  year offset (exact to within one year around the Persian new-year
  boundary); a day-accurate conversion would require adding the
  `jdatetime` dependency for a field that only needs a plausible integer
  year.
- **Mapping-table confidence is documented per entry, not just per file.**
  `jobvision_normalizer.py`'s comments mark each Persian phrase→enum
  mapping as VERIFIED (present in the actual sample data) or INFERRED
  (educated guess from JobVision's own filter-link vocabulary / standard
  Iranian job-site terminology, not seen in the samples). Every table
  falls back to a safe `UNKNOWN` enum member rather than raising, so an
  unmapped (INFERRED-and-wrong) value degrades gracefully instead of
  failing the job.
- **Description is stored as one HTML blob, not split into
  responsibilities/requirements.** The two real sample job postings
  structured their `description` HTML completely differently (one used
  plain `<div>` section headers, the other `<strong>` tags) — there is no
  reliable, general pattern to auto-split by section here. `raw_
  responsibilities`/`raw_requirements` are left `None` for JobVision
  rather than guessed at with a fragile regex.

**Verification performed (against real JobVision HTML, not fixtures
invented from assumptions)**
- **Pagination confirmed by the user directly** (2026-07-14, after this
  commit's initial draft): navigating to `.../jobs/keyword/{keyword}
  ?page=1` vs `?page=2` in a real browser returns genuinely different
  job listings — the `?page=N` query parameter `JobVisionSpider.
  build_listing_url` uses is real, server-honored pagination, not a
  guess. Locked in by
  `test_build_listing_url_uses_verified_page_query_param`. An optional
  `sort=1` parameter was also observed alongside `page`; not yet
  understood and left unset (safe to add once its meaning is confirmed).
- 8 unit tests in `tests/unit/test_jobvision.py`, all passing:
  - Parser: job 1's title/company/employment-type/work-mode/gender/
    military-status/salary-text/province/status/publish-date/technologies
    all match the real embedded JSON exactly; job 2 (different gender,
    negotiable/absent salary, different tech stack) confirmed the parser
    isn't accidentally hardcoded to job 1's shape; company profile's id/
    name/size/founded-year/province/city all match.
  - Normalizer: job 1's salary text `"45 - 60 میلیون تومان"` correctly
    parses to `salary_min=Decimal("45000000")`, `salary_max=
    Decimal("60000000")`; job 2's absent salary correctly normalizes to
    `(None, None)` rather than crashing; gender substring-matching
    correctly distinguishes `"فقط خانم"` (FEMALE) from `"ترجیحاً آقا"`
    (MALE); the Jalali year `1382` converts to Gregorian `2003`.
  - Spider: `extract_page_urls` against the real 30-result listing page
    extracts exactly 30 job URLs (matching the page's own `pageSize=30`),
    all absolute and with tracking query params stripped; company URLs
    extracted, absolute, and deduplicated.
- Full existing suite (all 19 tests across Commits 1–4) re-run and still
  passing after wiring the new modules into `app/parsers/__init__.py` /
  `app/normalizers/__init__.py` / `app/spiders/__init__.py`.

**What was explicitly NOT verified, and needs action before real crawling
(see "What you need to do" below)**
- **Listing pages for keyword/category combinations other than
  `"برنامه نویس"` / `"برنامه نویس اندروید"`** — other categories may have
  a different card layout (low risk, but unconfirmed).
- **Whether Playwright's browser can reach jobvision.ir at all past the
  HTTP 403 seen in Commit 1.** Everything in this commit was verified
  against static HTML/URLs the user fetched from their own browser — not
  through this project's own `Downloader`/Browser Singleton. That
  remains unverified until run outside this sandbox.
- **Jobinja, IranTalent, Ponisha** — no real HTML obtained yet for any of
  the other three target sites; their Parsers/Normalizers/Spiders don't
  exist yet.

**Not yet implemented (upcoming commits)**
- Commit 4 (continued): Jobinja, IranTalent, Ponisha Parsers/Normalizers/
  Spiders — blocked on the user providing real HTML for each, the same way
  as JobVision above.
- Commit 5: Exporters (JSON/Excel from unified DTOs) + `main.py` (Typer CLI)
  wiring the full pipeline end-to-end.

### Commit 5 — Exporters, `main.py`, first fully-operational site (JobVision)

**Files added**
```
main.py                              (Typer CLI: `crawl`, `sites` commands)
app/exporters/base_exporter.py
app/exporters/json_exporter.py
app/exporters/excel_exporter.py
app/dto/job_export_dto.py
app/dto/company_export_dto.py
tests/integration/test_jobvision_full_pipeline.py
```

**Files modified**
```
app/repositories/job_repository.py       — added list_by_source_with_relations()
app/repositories/company_repository.py   — added list_by_source_with_relations()
requirements.txt                         — typer 0.13.0 -> 0.26.8 (real bug, see below)
```

**What "fully operational for one site" means as of this commit**: running
`python main.py crawl --site jobvision` now genuinely exercises the
*entire* architecture end to end — Spider → Downloader → Parser →
Normalizer → Validator → Pipeline → Repository → PostgreSQL → JSON export
→ Excel export — for JobVision specifically. This is the first commit
where the project is a runnable product rather than a set of individually-
tested layers.

**Architectural decisions**

- **Export DTOs are separate from the Normalizer-stage DTOs.** `JobDTO`/
  `CompanyDTO` (Commit 2) carry plain strings for `company_name`/
  `category_name`/etc. because they exist *before* those strings are
  resolved to FK rows. `JobExportDTO`/`CompanyExportDTO` are built via
  `.from_orm_job()`/`.from_orm_company()` *after* persistence, from the
  actual `Job`/`Company` ORM rows plus their eager-loaded relationships —
  so two job postings that normalized to slightly different company-name
  spellings but deduplicated to the *same* `Company` row export with the
  identical canonical name, not whatever a single posting's raw text
  happened to say.
- **`list_by_source_with_relations()` eager-loads everything the Exporter
  needs in one query** (`selectinload` on `company`, `location`,
  `category`, `sub_category`, `employment_type`, `source`, and
  `skill_links.skill`) rather than lazily resolving each relationship per
  row — avoids an N+1 query pattern across potentially thousands of
  exported jobs, and is required anyway since `AsyncSession` cannot
  lazy-load outside its original `await` context.
- **`main.py` re-queries the database for export, rather than exporting
  the in-memory DTOs the Pipeline just processed.** After
  `JobIngestionPipeline.run()` persists everything, the export step reads
  back *every* job/company currently stored for that source — so JSON/
  Excel always reflect the complete current dataset, not just what this
  particular incremental run touched. Both reads happen inside the same
  `get_db_session()` transaction as the crawl itself, so they see this
  run's own writes without a second round trip.
- **`SITE_REGISTRY` in `main.py` is the single extension point** for
  adding Jobinja/IranTalent/Ponisha later — a `SiteConfig(spider_factory,
  parser_factory, normalizer_factory)` entry per site; nothing else in
  the file changes, because the CLI, Pipeline, and export step all depend
  only on the `BaseSpider`/`BaseParser`/`BaseNormalizer` abstractions.
- **Excel flattens list fields, JSON does not.** `benefits`/`skills`/
  `technologies`/`languages` are `list[str]` on the export DTOs; Excel
  cells can't hold a list, so `ExcelExporter` joins them with `" | "`
  before handing rows to pandas. `JSONExporter` keeps the real list
  structure — matching the platform's stated purpose of being an AI/LLM
  ingestion source, where structured lists are more useful than
  delimiter-joined strings.

**A real bug found and fixed: `typer`/`click` version incompatibility.**
`requirements.txt` pinned `typer==0.13.0` (Commit 1), which — combined
with whatever `click` version pip resolves today — crashed on **every**
command, including `--help`, with `TypeError: Parameter.make_metavar()
missing 1 required positional argument: 'ctx'`. This is a real
breaking change in `click`'s `Parameter.make_metavar()` signature that
`typer==0.13.0`'s Rich-based help formatter doesn't account for. Fixed by
upgrading to `typer==0.26.8`. **Lesson for this project**: `requirements.txt`
pins exact versions for reproducibility, but "exact version from Commit 1"
and "still compatible with everything else pip resolves today" are not
the same guarantee — this is worth re-checking (`pip install -r
requirements.txt` in a clean venv, then `python main.py --help`) after any
dependency changes, not just trusted blindly.

**Verification performed**
- `python main.py --help` / `crawl --help` / `sites` all run correctly
  after the typer upgrade.
- **`tests/integration/test_jobvision_full_pipeline.py`** — the strongest
  test in the project so far: the *real* `JobVisionSpider`, *real*
  `JobVisionParser`, *real* `JobVisionNormalizer`, *real*
  `JobIngestionPipeline`, *real* Repositories, a *real* PostgreSQL
  database, and *real* `JSONExporter`/`ExcelExporter` are all exercised
  together — only the HTTP/browser transport is faked (serving the same
  captured JobVision HTML `test_jobvision.py` already unit-tests in
  isolation). It deliberately drives two different real jobs through two
  different code paths: job 1409285's company page fixture exists (full
  company-crawl path through `_resolve_company`); job 1434775's company
  (id 572) has no fixture, so the fake downloader raises
  `TransientCrawlError` for it, exercising the graceful name-only-company
  fallback for real. Assertions include: correct `jobs_found`/
  `jobs_created`/`ScrapeStatus.SUCCESS`; both jobs' real Persian titles
  persisted correctly; company 17161 has `industry` populated (full
  crawl) while the fallback company does not (name-only); the exported
  JSON file is valid, contains the real job titles, and reports the
  correct `job_count`; the exported `.xlsx` opens with `openpyxl` and has
  the expected `Jobs`/`Companies` sheets with the correct row counts.
- Found and fixed a **test-isolation bug** (the same category as Commit
  3's): this new test initially hardcoded the real `"jobvision"` source
  code, which passed in isolation but failed when run after
  `test_job_pipeline.py` in the same suite — jobs persisted by an earlier
  run of this same test (against the same persistent Postgres instance)
  were found as "already known," turning `jobs_created` into
  `jobs_updated` on the second run. Fixed the same way as Commit 3's
  equivalent bug: `JobVisionSpider.SITE_CODE` is overridden per-test-
  invocation with a `uuid4()`-suffixed value (the Parser's `raw.
  source_code` field staying `"jobvision"` doesn't matter for this — it's
  informational only, not part of any dedup key). Verified by running the
  full 20-test suite three times in a row with no database reset between
  runs — all three runs pass identically.

**What was explicitly NOT verified**
- Same as Commit 4: no real Playwright browser was launched against
  jobvision.ir. `main.py crawl --site jobvision` should be run by the user
  outside this sandbox to find out whether it actually gets past the HTTP
  403 seen in Commit 1 — see "What you need to do" for exactly how.
- The `?sort=1` query parameter observed alongside JobVision's `?page=N`
  pagination (Commit 4) is still unused/unexplained.

**Not yet implemented (upcoming commits)**
- Jobinja, IranTalent, Ponisha Parsers/Normalizers/Spiders, and their
  registration in `main.py`'s `SITE_REGISTRY` — blocked on the user
  providing real HTML for each site, the same way as JobVision.
