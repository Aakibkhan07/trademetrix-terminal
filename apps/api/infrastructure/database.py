import logging
from typing import AsyncGenerator

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_async_engine = None
_async_session_maker = None


def _build_async_dsn() -> str:
    dsn = settings.supabase_db_url or ""
    if not dsn:
        logger.warning("No supabase_db_url configured, SQLAlchemy disabled")
        return ""
    return dsn.replace("postgresql://", "postgresql+asyncpg://")


async def init_db():
    global _async_engine, _async_session_maker
    dsn = _build_async_dsn()
    if not dsn:
        return
    _async_engine = create_async_engine(dsn, pool_size=5, max_overflow=10, echo=False, connect_args={"prepared_statement_cache_size": 0, "statement_cache_size": 0})
    _async_session_maker = async_sessionmaker(_async_engine, expire_on_commit=False)
    logger.info("SQLAlchemy async engine initialized")


async def close_db():
    global _async_engine, _async_session_maker
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_maker = None
        logger.info("SQLAlchemy async engine disposed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if not _async_session_maker:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session_direct() -> AsyncSession:
    if not _async_session_maker:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _async_session_maker()
