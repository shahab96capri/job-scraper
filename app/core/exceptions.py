"""
Application-wide exception hierarchy.

Design decisions:
- Every layer raises a specific subclass of `PlatformError` instead of
  bare `Exception` / `ValueError`. This lets `main.py` and pipeline
  orchestration code catch failures at the right granularity (e.g. retry
  on `TransientCrawlError`, but fail fast on `ConfigurationError`).
- Splitting by layer (Crawl / Parsing / Normalization / Validation /
  Repository / Export) mirrors the Spider -> Parser -> Normalizer ->
  Validator -> Pipeline -> Repository -> Export pipeline itself, so a
  stack trace's exception type alone tells you which layer failed.
- `TransientCrawlError` vs `PermanentCrawlError` distinction drives the
  retry system (Commit 3): transient errors (timeouts, 5xx, network
  resets) are retried with backoff; permanent errors (404, robots
  disallow, structural parse failure after retries) are not.
"""

from __future__ import annotations


class PlatformError(Exception):
    """Base class for every exception raised by the platform."""


# --- Configuration layer ---


class ConfigurationError(PlatformError):
    """Raised when application configuration is missing or invalid."""


# --- Crawl layer (spiders / downloader) ---


class CrawlError(PlatformError):
    """Base class for errors raised while fetching a page."""


class TransientCrawlError(CrawlError):
    """A crawl failure that is expected to succeed on retry.

    Examples: network timeout, connection reset, HTTP 429/5xx,
    Playwright navigation timeout.
    """


class PermanentCrawlError(CrawlError):
    """A crawl failure that will not resolve itself on retry.

    Examples: HTTP 404, robots.txt disallow, authentication wall.
    """


class RateLimitedError(TransientCrawlError):
    """Raised when the target site returns HTTP 429 or a bot-challenge page."""


# --- Parsing layer ---


class ParsingError(PlatformError):
    """Raised when a parser cannot extract the expected raw structure
    from an HTML document (e.g. a selector the site relies on is missing).
    """


# --- Normalization layer ---


class NormalizationError(PlatformError):
    """Raised when a raw value cannot be mapped to a standard platform value."""


# --- Validation layer ---


class ValidationFailedError(PlatformError):
    """Raised when a DTO fails validation rules.

    Carries the list of individual field errors so the pipeline can log
    and persist them to the `Errors` table without re-deriving them.
    """

    def __init__(self, message: str, field_errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or []


# --- Repository / persistence layer ---


class RepositoryError(PlatformError):
    """Base class for persistence-layer failures."""


class EntityNotFoundError(RepositoryError):
    """Raised when a lookup by unique key returns no row and the caller
    required one to exist.
    """


class DuplicateEntityError(RepositoryError):
    """Raised when an insert would violate a uniqueness constraint that
    the caller did not expect (i.e. duplicate detection upstream failed).
    """


# --- Export layer ---


class ExportError(PlatformError):
    """Raised when JSON/Excel export fails (e.g. disk full, permission error)."""
