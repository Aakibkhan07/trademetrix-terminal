import logging

from core.db import async_supabase, get_supabase

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


async def async_safe_single(query_builder):
    try:
        result = await async_supabase(lambda: query_builder.maybe_single().execute())
        return result.data
    except Exception as e:
        logger.debug("async_safe_single query failed: %s", e)
        return None


async def async_safe_execute(query_builder):
    try:
        result = await async_supabase(lambda: query_builder.execute())
        return result.data or []
    except Exception as e:
        logger.debug("async_safe_execute query failed: %s", e)
        return []


async def async_safe_insert(table: str, data: dict) -> dict | None:
    try:
        result = await async_supabase(lambda: get_supabase().table(table).insert(data).execute())
        return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("async_safe_insert into %s failed: %s", table, e)
        return None


async def async_safe_update(table: str, data: dict, match_field: str, match_value: str, match_field2: str | None = None, match_value2: str | None = None) -> dict | None:
    try:
        query = get_supabase().table(table).update(data).eq(match_field, match_value)
        if match_field2 and match_value2:
            query = query.eq(match_field2, match_value2)
        result = await async_supabase(lambda: query.execute())
        return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("async_safe_update of %s failed: %s", table, e)
        return None


def safe_update(table: str, data: dict, match_field: str, match_value: str, match_field2: str | None = None, match_value2: str | None = None) -> dict | None:
    try:
        query = get_supabase().table(table).update(data).eq(match_field, match_value)
        if match_field2 and match_value2:
            query = query.eq(match_field2, match_value2)
        result = query.execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("safe_update of %s failed: %s", table, e)
        return None


def safe_insert(table: str, data: dict) -> dict | None:
    try:
        result = get_supabase().table(table).insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("safe_insert into %s failed: %s", table, e)
        return None


async def async_paginated_query(
    query_builder,
    limit: int = 50,
    offset: int = 0,
    max_limit: int = 200,
):
    clamped_limit = min(max(1, limit), max_limit)
    clamped_offset = max(0, offset)
    try:
        result = await async_supabase(lambda: query_builder.limit(clamped_limit).offset(clamped_offset).execute())
        return result.data or []
    except Exception as e:
        logger.debug("async_paginated_query failed: %s", e)
        return []
