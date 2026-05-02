from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.db.models import QueryLog


async def insert_log(db: AsyncSession, **kwargs: Any) -> QueryLog:
    """Create and persist a QueryLog row.

    Caller supplies all column values as keyword arguments. The id and
    created_at columns are populated by the model defaults if omitted.
    """
    log = QueryLog(**kwargs)
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def get_by_id(db: AsyncSession, log_id: uuid.UUID) -> QueryLog | None:
    """Return a single QueryLog by primary key, or None."""
    result = await db.execute(select(QueryLog).where(QueryLog.id == log_id))
    return result.scalar_one_or_none()


async def get_logs_by_account(
    db: AsyncSession,
    account_id: uuid.UUID,
    limit: int = 50,
) -> list[QueryLog]:
    """Return the most recent *limit* QueryLog rows for an account."""
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.account_id == account_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
