from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class CMARTError(Exception):
    """Base exception for all application-level errors."""

    status_code: int = 500
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class AuthError(CMARTError):
    """Raised when a request cannot be authenticated or authorised."""

    status_code = 401
    default_message = "Authentication required."


class RateLimitError(CMARTError):
    """Raised when a caller exceeds the configured rate limit."""

    status_code = 429
    default_message = "Rate limit exceeded. Please retry after a moment."


class NotFoundError(CMARTError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    default_message = "The requested resource was not found."


class PipelineError(CMARTError):
    """Raised when the AI pipeline encounters an unrecoverable error."""

    status_code = 500
    default_message = "Pipeline processing failed."


# ---------------------------------------------------------------------------
# FastAPI exception handler functions
# ---------------------------------------------------------------------------


def _error_response(exc: CMARTError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "status_code": exc.status_code},
    )


async def cmart_error_handler(request: Request, exc: CMARTError) -> JSONResponse:
    return _error_response(exc)


async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    return _error_response(exc)


async def rate_limit_error_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    response = _error_response(exc)
    response.headers["Retry-After"] = "60"
    return response


async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return _error_response(exc)


async def pipeline_error_handler(request: Request, exc: PipelineError) -> JSONResponse:
    return _error_response(exc)
