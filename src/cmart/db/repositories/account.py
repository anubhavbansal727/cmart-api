from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.db.models import Account


async def get_by_api_key(db: AsyncSession, key: str) -> Account | None:
    """Return the Account matching *key*, or None if not found."""
    result = await db.execute(
        select(Account).where(Account.api_key == key, Account.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def create_account(db: AsyncSession, name: str, api_key: str) -> Account:
    """Insert a new Account row and return the persisted instance."""
    account = Account(name=name, api_key=api_key)
    db.add(account)
    await db.flush()  # Flush to get the generated PK without committing
    await db.refresh(account)
    return account
