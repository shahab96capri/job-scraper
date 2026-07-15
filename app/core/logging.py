"""
Centralized logging setup using Loguru.

Design decisions:
- A single `configure_logging()` call (invoked once from `main.py`) wires
  up every sink. All other modules simply `from loguru import logger` and
  use it — Loguru's underlying logger is already a process-wide singleton,
  so we don't need to build our own wrapper class around it.
- Three sinks are configured:
    1. stderr   -> human-readable, colorized, for local development.
    2. app.log  -> rotating file with ALL levels, for general operational
                   history (crawls, pipeline steps, exports).
    3. errors.log -> rotating file restricted to ERROR+ level only, so
                   on-call debugging never has to grep through noise.
- `enqueue=True` makes every sink process-safe / thread-safe, which matters
  because spiders run concurrently under asyncio and, later, potentially
  across multiple worker processes.
- `backtrace` / `diagnose` are disabled in non-debug environments to avoid
  leaking local variable values (which may include scraped PII such as
  company emails/phones) into log files.
"""

from __future__ import annotations

import sys

from loguru import logger

from app.config.settings import get_settings

_configured = False


def configure_logging() -> None:
    """Configure Loguru sinks exactly once per process."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    logger.remove()  # drop Loguru's default stderr sink so we control format

    logger.add(
        sys.stderr,
        level=settings.log_level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=settings.debug,
        diagnose=settings.debug,
        enqueue=True,
    )

    logger.add(
        settings.log_dir_path / "app.log",
        level=settings.log_level,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=settings.debug,
        diagnose=settings.debug,
    )

    logger.add(
        settings.log_dir_path / "errors.log",
        level="ERROR",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=settings.debug,
    )

    _configured = True
    logger.bind(component="core.logging").info(
        f"Logging configured | env={settings.app_env} | level={settings.log_level}"
    )


__all__ = ["configure_logging", "logger"]
