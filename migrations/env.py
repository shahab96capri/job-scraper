"""
Alembic environment script.

Design decisions:
- The database URL is read from `app.config.settings.get_settings()`
  (the platform's single Config Singleton) rather than duplicated in
  `alembic.ini`, so `.env` remains the one source of truth.
- Migrations run over the **sync** driver (`database_url_sync`,
  psycopg2), even though the application runs on the async driver
  (asyncpg) at runtime. Alembic's autogenerate/offline machinery is
  built around sync `Connection` objects; running migrations async adds
  real complexity for no benefit, since migrations are a one-shot CLI
  operation, not a concurrent request path.
- `target_metadata = Base.metadata` is sourced from `app.models`, which
  imports every model module — this is what makes `alembic revision
  --autogenerate` able to see the full schema.
- `compare_type=True` / `compare_server_default=True` are enabled so
  autogenerate reliably detects column type/default drift, not just
  added/removed tables/columns.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config.settings import get_settings
from app.models import Base  # noqa: F401  (imports register all models)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits raw SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
