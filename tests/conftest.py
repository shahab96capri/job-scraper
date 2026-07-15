"""
Shared pytest fixtures.

`get_engine()` / `get_sessionmaker()` (`app/database/session.py`) are
process-wide singletons by design (Commit 1) — correct for the
application's real lifecycle (one process, one event loop, from `main.py`
start to shutdown). Under pytest, each test function may run on its own
event loop depending on `pytest-asyncio` configuration; an `AsyncEngine` /
asyncpg connection created against one loop cannot be used from another
("Task ... attached to a different loop" / "Event loop is closed").

This fixture clears the `lru_cache` singletons before every test (so each
test builds its own engine against whichever loop it actually runs on)
and disposes + clears again afterward (so no pooled connection survives
into the next test's potentially-different loop). Production code never
does this — `main.py` (Commit 5) creates the engine once and disposes it
once, in the same long-lived loop, by design.
"""

from __future__ import annotations

import pytest_asyncio

from app.database.session import dispose_engine, get_engine, get_sessionmaker


@pytest_asyncio.fixture(autouse=True)
async def _isolated_engine_per_test():
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    yield
    await dispose_engine()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
