"""BreachLens error types and FastAPI exception handlers."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class AppError(Exception):
    """Base application error. Subclass for specific HTTP statuses."""

    status_code: int = 500
    code: str = "internal"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class ValidationError(AppError):
    status_code = 422
    code = "validation"


class PathNotAllowedError(AppError):
    status_code = 403
    code = "path_not_allowed"


class RegexRejectedError(AppError):
    status_code = 422
    code = "regex_rejected"


class IndexingError(AppError):
    status_code = 500
    code = "indexing"


class SearchError(AppError):
    status_code = 500
    code = "search"


class DatabaseError(AppError):
    status_code = 500
    code = "database"


class ErrorResponse(BaseModel):
    error: str
    message: str


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "internal", "message": str(exc)},
    )
