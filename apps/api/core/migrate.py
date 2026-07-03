"""
⚠ DEPRECATED — Use Alembic instead.

This file was the original bootstrap migration that runs raw SQL via exec_sql RPC.
It is no longer the canonical schema source.

The canonical schema source is:
    alembic/versions/001_initial_schema.py

To run migrations:
    alembic upgrade head

This module is kept only as a fallback for local development environments
where Alembic has not been run. It will be removed in a future release.
"""

import logging

logger = logging.getLogger(__name__)

DEPRECATION_WARNING = (
    "core/migrate.py is deprecated. Use 'alembic upgrade head' instead. "
    "This module will be removed in a future release."
)


def run_migrations() -> None:
    logger.warning(DEPRECATION_WARNING)
    logger.warning(
        "Run 'alembic upgrade head' to apply schema migrations. "
        "The three-schema-source pattern (migrate.py + supabase_schema.sql + alembic) "
        "has been consolidated to Alembic only."
    )
