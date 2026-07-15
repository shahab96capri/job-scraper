"""
Database engine + session management.

Design decisions:
- `get_engine()` builds exactly one `AsyncEngine` per process (the
  "Database Session Singleton" requirement) using `lru_cache`. SQLAlchemy's
  `AsyncEngine` already owns an internal connection pool, so creating it
  more than once would defeat pooling entirely and exhaust Postgres
  connections under load.
- `get_sessionmaker()` builds one `async_sessionmaker` bound to that engine.
  We deliberately do NOT expose a single shared `AsyncSession` instance —
  `AsyncSession` is NOT safe to share across concurrent asyncio tasks
  (each spider/pipeline run needs its own session/transaction). The
  singleton is the *factory*, not the session.
- `get_db_session()` is an async context manager that:
    1. yields a fresh session per call site,
    2. commits on clean exit,
    3. rolls back and re-raises on any exception,
    4. always closes the session.
  This is the only sanctioned way application code obtains a session —
  repositories receive a session via constructor injection (Commit 2),
  they never call `get_db_session()` themselves, keeping session lifecycle
  management out of the repository layer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import get_settings
from app.core.logging import logger


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide AsyncEngine singleton."""
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # detect stale connections before using them
    )
    logger.bind(component="database.session").info(
        f"AsyncEngine created | pool_size={settings.db_pool_size} "
        f"max_overflow={settings.db_max_overflow}"
    )
    return engine


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory singleton."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide a transactional session scope.

    Usage:
        async with get_db_session() as session:
            repo = JobRepository(session)
            await repo.create(...)
    """
    session_factory = get_sessionmaker()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Dispose the engine's connection pool. Call on graceful shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        logger.bind(component="database.session").info("AsyncEngine disposed")
