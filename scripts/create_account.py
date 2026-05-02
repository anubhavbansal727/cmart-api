"""CLI script to provision a new account with an API key.

Usage:
    python scripts/create_account.py --name "Acme Corp" --key "sk-acme-test-123"
    python scripts/create_account.py --name "Design Partner 1"  # auto-generates key
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import AsyncSession

from cmart.db.engine import AsyncSessionLocal, engine
from cmart.db.models import Base
from cmart.db.repositories.account import create_account, get_by_api_key


async def provision(name: str, api_key: str) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            existing = await get_by_api_key(db, api_key)
            if existing:
                print(f"[error] API key already in use by account: {existing.name}")
                return

            account = await create_account(db, name=name, api_key=api_key)

    print(f"[ok] Account created")
    print(f"     Name:    {account.name}")
    print(f"     ID:      {account.id}")
    print(f"     API key: {api_key}")
    print(f"\n     Authorization header:")
    print(f"     Bearer {api_key}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a CMART account + API key")
    parser.add_argument("--name", required=True, help="Account name (e.g. company name)")
    parser.add_argument(
        "--key",
        default=None,
        help="API key to assign. Auto-generated (32-byte hex) if not provided.",
    )
    args = parser.parse_args()

    api_key = args.key or f"sk-{secrets.token_hex(24)}"

    await provision(name=args.name, api_key=api_key)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
