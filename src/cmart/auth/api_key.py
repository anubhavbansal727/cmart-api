from __future__ import annotations

import hmac

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.db.models import Account
from cmart.db.repositories.account import get_by_api_key
from cmart.utils.errors import AuthError

_SCHEME = "Bearer"


async def authenticate(request: Request, db: AsyncSession) -> Account:
    """Extract and validate the API key from the Authorization header.

    Expected header format: ``Authorization: Bearer <key>``

    Uses hmac.compare_digest for constant-time comparison to prevent
    timing-based key enumeration attacks.

    Raises AuthError for any of:
    - Missing Authorization header
    - Header that does not start with "Bearer "
    - Key not found in the database or belonging to an inactive account
    """
    authorization: str | None = request.headers.get("Authorization")

    if not authorization:
        raise AuthError("Authorization header is missing.")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != _SCHEME:
        raise AuthError("Authorization header must use the Bearer scheme.")

    provided_key = parts[1].strip()
    if not provided_key:
        raise AuthError("API key must not be empty.")

    account = await get_by_api_key(db, provided_key)
    if account is None:
        raise AuthError("Invalid or inactive API key.")

    # Constant-time comparison guards against timing attacks even though we
    # already did the DB lookup; this is a defence-in-depth measure.
    if not hmac.compare_digest(account.api_key, provided_key):
        raise AuthError("Invalid or inactive API key.")

    return account
