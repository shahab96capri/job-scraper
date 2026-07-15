"""Spider layer: navigates listing/detail pages and yields raw HTML. Never
touches SQL, never exports, never contains business logic."""

from app.spiders.base_spider import BaseSpider, CrawlPageResult
from app.spiders.downloader import Downloader
from app.spiders.jobvision_spider import JobVisionSpider

__all__ = ["BaseSpider", "CrawlPageResult", "Downloader", "JobVisionSpider"]
