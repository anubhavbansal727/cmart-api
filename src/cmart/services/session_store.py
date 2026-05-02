from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import redis.asyncio as aioredis

from cmart.config import get_settings


@dataclass
class SessionState:
    session_id: str
    account_id: str
    user_id: str
    original_query: str
    clarify_rounds: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


class SessionStore:
    """Redis-backed session store for multi-round clarification loops.

    Key: session:{session_id} — JSON blob, TTL = session_ttl_seconds.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._ttl = get_settings().session_ttl_seconds

    async def create(
        self, account_id: str, user_id: str, original_query: str
    ) -> SessionState:
        state = SessionState(
            session_id=str(uuid.uuid4()),
            account_id=account_id,
            user_id=user_id,
            original_query=original_query,
        )
        await self._redis.setex(
            f"session:{state.session_id}",
            self._ttl,
            json.dumps(asdict(state)),
        )
        return state

    async def get(self, session_id: str) -> SessionState | None:
        raw = await self._redis.get(f"session:{session_id}")
        if raw is None:
            return None
        return SessionState(**json.loads(raw))

    async def increment_round(self, session_id: str) -> int:
        """Increment clarify_rounds and return the new count. Returns 0 if session not found."""
        state = await self.get(session_id)
        if state is None:
            return 0
        state.clarify_rounds += 1
        await self._redis.setex(
            f"session:{session_id}",
            self._ttl,
            json.dumps(asdict(state)),
        )
        return state.clarify_rounds

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(f"session:{session_id}")
