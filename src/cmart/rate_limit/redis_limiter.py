from __future__ import annotations

import time
from typing import Any

from cmart.config import get_settings
from cmart.utils.errors import RateLimitError


class RedisRateLimiter:
    """Sliding-window rate limiter: N req/min per account_id, enforced in Redis.

    Key pattern: rate:{account_id}:{window_minute}, TTL = 120s.
    The 2-minute TTL ensures the key outlives the window it counts.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._limit = get_settings().rate_limit_per_minute

    async def check(self, account_id: str) -> None:
        window = int(time.time()) // 60
        key = f"rate:{account_id}:{window}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 120)
        if count > self._limit:
            raise RateLimitError()
