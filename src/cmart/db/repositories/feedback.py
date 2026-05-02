from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.db.models import Feedback


async def insert_feedback(db: AsyncSession, **kwargs: Any) -> Feedback:
    """Create and persist a Feedback row.

    Caller supplies all column values as keyword arguments.
    """
    feedback = Feedback(**kwargs)
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)
    return feedback


async def get_by_query_id(db: AsyncSession, query_id: uuid.UUID) -> Feedback | None:
    """Return the Feedback row for the given query_id, or None."""
    result = await db.execute(
        select(Feedback).where(Feedback.query_id == query_id)
    )
    return result.scalar_one_or_none()
