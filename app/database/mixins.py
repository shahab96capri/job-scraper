"""
Reusable ORM mixins shared by every model.

Design decisions:
- Every entity in this platform uses a UUID surrogate primary key
  (`UUIDPrimaryKeyMixin`), independent from the website-specific job/company
  ID (which is stored separately as `website_job_id` / `website_company_id`
  on the relevant models). This lets us merge data from unlimited future
  sources without primary-key collisions.
- `TimestampMixin` standardizes `created_at` / `updated_at` handling with
  database-side defaults (`server_default=func.now()`), so timestamps are
  correct even for rows inserted outside the application (bulk imports,
  manual SQL fixes) and are not subject to clock drift between app servers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """Adds a UUID v4 surrogate primary key column named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Adds `created_at` and `updated_at` columns with DB-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
