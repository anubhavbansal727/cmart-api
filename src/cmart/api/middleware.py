from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that:

    1. Generates a unique X-Request-ID for every inbound request.
    2. Measures total request latency and attaches it as X-Response-Time (ms).
    3. Emits a structured log line per request including method, path, status,
       and latency so that every request is traceable without extra tooling.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_ns = time.perf_counter_ns()

        # Bind request-scoped context so all downstream log calls carry it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)

        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"

        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=round(elapsed_ms, 2),
            request_id=request_id,
        )

        return response
