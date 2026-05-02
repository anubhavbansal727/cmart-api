from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from cmart.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    # Pool settings tuned for typical async web service workloads
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=_settings.app_env == "development",
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass
