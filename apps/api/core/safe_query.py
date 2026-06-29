import logging

from core.db import get_supabase

logger = logging.getLogger(__name__)


def safe_single(query):
    try:
        result = query.maybe_single().execute()
        return result.data
    except Exception as e:
        logger.debug("safe_single query failed: %s", e)
        return None


def safe_execute(query):
    try:
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.debug("safe_execute query failed: %s", e)
        return []


def safe_insert(table: str, data: dict) -> dict | None:
    try:
        result = get_supabase().table(table).insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("safe_insert into %s failed: %s", table, e)
        return None


def safe_update(table: str, data: dict, match_field: str, match_value: str) -> dict | None:
    try:
        result = get_supabase().table(table).update(data).eq(match_field, match_value).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("safe_update of %s failed: %s", table, e)
        return None
