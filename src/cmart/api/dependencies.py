from __future__ import annotations

from typing import Any, AsyncGenerator

import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.auth import api_key as auth
from cmart.db.engine import AsyncSessionLocal
from cmart.db.models import Account

logger = structlog.get_logger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession and guarantee it is closed after the request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_redis(request: Request) -> Any:
    """Yield the shared Redis client stored on app state."""
    return request.app.state.redis


async def get_current_account(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """Authenticate the request and return the active Account.

    Extracts the API key from the Authorization: Bearer <key> header,
    verifies it against the database, and returns the matching Account ORM
    object.  Raises AuthError (→ 401) for any authentication failure.
    """
    return await auth.authenticate(request, db)
