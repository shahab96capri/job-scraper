"""
Declarative base for all ORM models.

Kept as its own module (separate from `session.py` and `mixins.py`) so that
`app/models/*.py` can import `Base` without triggering engine/session
creation as a side effect — model modules should be importable in contexts
that never touch a real database (e.g. Alembic autogeneration, unit tests
that only check model metadata).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class every ORM model inherits from."""
