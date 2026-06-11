import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from findleaks.config import get_settings


def _build_async_url(url: str) -> str:
    """Convert postgresql:// or postgresql+asyncpg:// to the async driver URL."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _engine_kwargs(url: str) -> dict:
    """Return engine kwargs appropriate for the driver."""
    if "sqlite" in url:
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {"statement_cache_size": 0},
    }


settings = get_settings()
_async_url = _build_async_url(settings.DATABASE_URL)

engine = create_async_engine(
    _async_url,
    echo=settings.LOG_LEVEL == "DEBUG",
    **_engine_kwargs(_async_url),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables on startup. Safe to call multiple times."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Cleanly close all connections on shutdown."""
    await engine.dispose()
