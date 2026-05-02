from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

# Windows terminals default to cp1252; force UTF-8 so structured logs don't crash on
# non-ASCII characters in external API error messages.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from cmart.api.middleware import RequestContextMiddleware
from cmart.api.routes import feedback, ingest, query
from cmart.config import get_settings
from cmart.db.engine import AsyncSessionLocal, engine
from cmart.utils.errors import (
    AuthError,
    CMARTError,
    NotFoundError,
    PipelineError,
    RateLimitError,
    auth_error_handler,
    cmart_error_handler,
    not_found_error_handler,
    pipeline_error_handler,
    rate_limit_error_handler,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of shared resources."""
    settings = get_settings()

    # --- Startup ---
    logger.info("startup.begin", app_env=settings.app_env)

    # Verify DB connectivity by opening a connection from the pool
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("startup.db_pool_ready")
        app.state.db_ok = True
    except Exception as exc:
        logger.error("startup.db_pool_failed", error=str(exc))
        app.state.db_ok = False

    # Initialise Redis connection
    import redis.asyncio as aioredis

    try:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("startup.redis_ready")
        app.state.redis_ok = True
    except Exception as exc:
        logger.error("startup.redis_failed", error=str(exc))
        app.state.redis = None
        app.state.redis_ok = False

    logger.info("startup.complete")
    yield

    # --- Shutdown ---
    logger.info("shutdown.begin")

    if app.state.redis is not None:
        await app.state.redis.aclose()
        logger.info("shutdown.redis_closed")

    await engine.dispose()
    logger.info("shutdown.db_pool_closed")

    logger.info("shutdown.complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CMART AI Support Agent",
        version="0.1.0",
        description="API-first AI support agent",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestContextMiddleware)

    # Routers
    app.include_router(query.router, prefix="/query", tags=["query"])
    app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
    app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])

    # Exception handlers
    app.add_exception_handler(AuthError, auth_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitError, rate_limit_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(NotFoundError, not_found_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(PipelineError, pipeline_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(CMARTError, cmart_error_handler)  # type: ignore[arg-type]

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "status_code": 500},
        )

    # Inline health endpoint — live pings so load balancers detect post-startup failures
    @app.get("/health", tags=["meta"])
    async def health(request: Request) -> dict[str, Any]:
        db_ok = False
        redis_ok = False

        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            pass

        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            try:
                await redis.ping()
                redis_ok = True
            except Exception:
                pass

        status = "ok" if (db_ok and redis_ok) else "degraded"
        return {"status": status, "db": db_ok, "redis": redis_ok}

    return app


app = create_app()
