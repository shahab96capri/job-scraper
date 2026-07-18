"""
`JobVisionSpider` — verified against a real, rendered listing page
(`jobvision.ir/jobs/keyword/برنامه نویس`, 30 results, `pageSize=30`,
provided by the user).

**Listing page finding**: unlike job-detail/company-profile pages (see
`JobVisionParser`'s docstring), the listing page's embedded `ng-state`
JSON does NOT contain the full 30-job result set — only a single job's
detail (whichever is shown in the desktop split-view detail pane). The
job list itself is rendered from `<job-card>` custom elements, each
wrapping an `<a class="... desktop-job-card" href="/jobs/{id}/{slug}?
...">`. `extract_page_urls` therefore uses BeautifulSoup against that
verified structure, not JSON extraction.

**Pagination — VERIFIED by the user directly** (2026-07-14): navigating to
`.../jobs/keyword/{keyword}?page=1` vs `...?page=2` in a real browser
produces different result sets; the URL bar genuinely updates, confirming
this is real server-aware pagination and not purely client-side routing
(the pagination *control itself* still renders `href=""` with a `(click)`
handler in the static HTML — Angular intercepts the click and pushes a new
URL via its router, which the server also honors on direct navigation/
reload). An optional `sort=1` query parameter was also observed
alongside `page` in the confirmed URL; not yet understood (default sort
order vs an explicit one) and left unset here — safe to add later if a
specific sort order becomes important.
"""

from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.spiders.base_spider import BaseSpider, CrawlPageResult

BASE_URL = "https://jobvision.ir"
JOB_CARD_SELECTOR = "a.desktop-job-card"
COMPANY_LINK_SELECTOR = 'a[href^="/companies/"]'

DEFAULT_KEYWORD = "برنامه نویس"

# The full set of job categories as they appear in JobVision's own search
# filter UI (copied verbatim by the user from the live site, 2026-07-18).
# One category name's `titleFa` was independently cross-checked against a
# real captured job page's `jobCategories` field
# (`tests/fixtures/jobvision/job_detail_1.html`, category id 30 ==
# "توسعه نرم افزار و برنامه نویسی") and matched exactly, confirming these
# are the platform's real, current category labels rather than stale/
# guessed ones.
#
# We deliberately crawl these via the *keyword* search endpoint (already
# verified working — see this module's docstring) rather than guessing at
# `/jobs/category/{slug}` URLs: a handful of category slugs were found via
# web search (`developer`, `civil`, `content`, `insurance`, `sales`,
# `labourer`), but nothing confirms those slugs map 1:1 onto this ID-based
# category list, and getting that mapping wrong would silently under-crawl
# entire categories. Full-text keyword search against each category's own
# display name is a safe, already-proven mechanism, at the cost of being a
# best-effort sweep rather than a guaranteed-exact category filter for
# every edge case.
ALL_CATEGORIES: list[str] = [
    "فروش و بازاریابی - سطوح کارشناسی و مدیریتی",
    "فروش و بازاریابی - فروشنده / بازاریاب و ویزیتور / صندوقدار",
    "مدیر فروشگاه / مدیر رستوران",
    "خدمات و پشتیبانی مشتریان",
    "نماینده علمی / مدرپ",
    "مدیریت بیمه",
    "دیجیتال مارکتینگ و سئو",
    "ترجمه / تولید محتوا / نویسندگی و ویراستاری",
    "توسعه نرم افزار و برنامه نویسی",
    "تست نرم افزار",
    "شبکه / DevOps / پشتیبانی سخت افزاری و نرم افزاری",
    "علوم داده / هوش مصنوعی",
    "طراحی بازی",
    "طراحی گرافیک / طراحی انیمیشن و موشن گرافیک",
    "طراحی لباس / طراحی طلا و جواهر",
    "طراحی صنعتی / نقشه کشی صنعتی",
    "عکاسی",
    "مشاغل حوزه فیلم و سینما",
    "طراحی موسیقی و صدا",
    "طراحی رابط و تجربه کاربری (UI/UX)",
    "مدیر محصول / مالک محصول",
    "تحلیل و توسعه کسب و کار / استراتژی / برنامه ریزی",
    "مهندسی صنایع / مدیریت تولید / مدیریت پروژه / مدیریت عملیات",
    "خرید / تدارکات",
    "بازرگانی / تجارت",
    "لجستیک / حمل و نقل / انبارداری",
    "راننده / مسئول توزیع / پیک موتوری",
    "مالی و حسابداری",
    "معامله گر و تحلیل گر بازارهای مالی",
    "تحصیل دار / کارپرداز",
    "مسئول دفتر / کارمند اداری و ثبت اطلاعات / تایپیست",
    "منابع انسانی",
    "مدیر اجرایی / مدیر داخلی",
    "مدیرعامل / مدیر کارخانه",
    "مهندسی برق",
    "مهندسی پزشکی",
    "مهندسی مکانیک / مهندسی هوا و فضا",
    "مهندسی صنایع غذایی",
    "مهندسی شیمی / مهندسی نفت و گاز",
    "مهندسی انرژی / مهندسی هسته ای",
    "بهداشت، ایمنی و محیط زیست (HSE)",
    "مهندسی عمران",
    "مهندسی معماری و شهرسازی",
    "مهندسی معدن / زمین شناسی",
    "مهندسی مواد و متالورژی",
    "مهندسی نساجی",
    "مهندسی پلیمر",
    "مهندسی کشاورزی / علوم دامی",
    "زیست شناسی / علوم زیستی / علوم آزمایشگاهی",
    "داروسازی / بیوشیمی / شیمی",
    "پزشک / دندانپزشک / دامپزشک",
    "پرستار و بهیار / تکنسین حوزه سلامت و درمان / دستیار پزشک",
    "پرستار سالمند / پرستار کودک",
    "روانشناسی / مشاوره / علوم اجتماعی",
    "حقوقی",
    "روابط عمومی",
    "خبرنگار / روزنامه نگار",
    "آموزش / تدریس",
    "پژوهش",
    "نگهبان",
    "کارگر ساده / نیروی خدماتی",
    "تکنسین فنی / تعمیرکار / کارگر ماهر",
    "تخصص های ساختمانی (بنّا / گچ کار / کاشی کار و ...)",
    "نجار / MDF کار / کابینت کار / مبل ساز / رنگ کار چوب",
    "آرایشگر",
    "قناد و شیرینی پز",
    "بافنده فرش (قالی باف)",
    "نانوا",
    "قفل و کلیدساز",
    "قصاب",
    "کفاش",
    "خیاط",
    "آشپز",
    "باریستا / کافی من / گارسون",
    "راهنمای تور / مهماندار",
    "ورزش / تربیت بدنی / تغذیه",
    "تاریخ / جغرافیا / باستان شناسی",
]


def _strip_query(url: str) -> str:
    """Drop tracking/query params (`row`, `searchId`, `score`, ...) so the
    same job always yields the same canonical `source_url` across crawls,
    independent of its position in that particular search result."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query="", fragment=""))


class JobVisionSpider(BaseSpider):
    SITE_CODE = "jobvision"
    SITE_NAME = "JobVision"
    BASE_URL = BASE_URL

    def __init__(
        self,
        downloader,
        *,
        max_pages: int,
        keyword: str | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        super().__init__(downloader, max_pages=max_pages)
        if keywords:
            self.keywords = list(keywords)
        elif keyword:
            self.keywords = [keyword]
        else:
            self.keywords = [DEFAULT_KEYWORD]
        # `build_listing_url` reads this single attribute — `crawl_job_urls`
        # below rotates it through `self.keywords` one at a time so the
        # inherited pagination/incremental-stop logic in `BaseSpider`
        # doesn't need to know anything changed.
        self.keyword = self.keywords[0]

    def build_listing_url(self, page: int) -> str:
        # VERIFIED (2026-07-14): confirmed by direct browser navigation —
        # `?page=1` vs `?page=2` on this exact URL shape returns different
        # job listings. `keyword` matches the sample fixture's own
        # canonical URL structure (`/jobs/keyword/{keyword}`).
        return f"{BASE_URL}/jobs/keyword/{self.keyword}?page={page}"

    async def crawl_job_urls(
        self, known_website_job_ids: set[str] | None = None
    ) -> AsyncIterator[str]:
        """Like `BaseSpider.crawl_job_urls`, but sweeps every entry in
        `self.keywords` (one search per category) instead of just one,
        de-duplicating job URLs seen under more than one category within
        this same run (a job can legitimately show up under multiple
        category searches). Each category still respects `max_pages` and
        the incremental-stop rule independently."""
        seen_this_run: set[str] = set()
        for kw in self.keywords:
            self.keyword = kw
            self._logger.info(f"Crawling category/keyword: {kw!r}")
            async for job_url in super().crawl_job_urls(known_website_job_ids):
                website_job_id = self.website_job_id_from_url(job_url)
                if website_job_id in seen_this_run:
                    continue
                seen_this_run.add(website_job_id)
                yield job_url

    def extract_page_urls(self, listing_html: str) -> CrawlPageResult:
        soup = BeautifulSoup(listing_html, "html.parser")

        job_urls: list[str] = []
        for anchor in soup.select(JOB_CARD_SELECTOR):
            href = anchor.get("href")
            if not href:
                continue
            job_urls.append(_strip_query(urljoin(BASE_URL, href)))

        company_urls: list[str] = []
        for anchor in soup.select(COMPANY_LINK_SELECTOR):
            href = anchor.get("href")
            if not href:
                continue
            company_urls.append(_strip_query(urljoin(BASE_URL, href)))

        # Preserve order, drop duplicates (a company can appear on
        # multiple job cards within the same listing page).
        job_urls = list(dict.fromkeys(job_urls))
        company_urls = list(dict.fromkeys(company_urls))

        return CrawlPageResult(job_urls=job_urls, company_urls=company_urls)

    def job_url_from_id(self, job_id: str) -> str:
        """Best-effort job detail URL built from just an ID (no slug).

        Needed for jobs discovered via a company's bonus job list (see
        `JobVisionParser.parse_company_job_posts`), which only gives us an
        ID — not the full `/jobs/{id}/{slug}` URL a listing page's `<a>`
        tag has. Assumes JobVision's router keys off the numeric ID
        segment only and treats the slug as decorative/SEO (same
        convention as e.g. Stack Overflow's `/questions/{id}/{slug}`).
        This is UNVERIFIED against the live site — the Pipeline treats a
        failure to load this URL as expected/non-fatal for expired
        postings and falls back to the summary data already in hand
        rather than treating it as a real crawl error.
        """
        return f"{BASE_URL}/jobs/{job_id}"
