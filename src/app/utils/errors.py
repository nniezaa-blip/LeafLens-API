"""Custom exceptions and error handlers."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class LextariError(Exception):
    """Base error for all app-specific exceptions."""

    status_code: int = 500
    detail: str = "Internal server error"


class DeviceNotFoundError(LextariError):
    status_code = 404
    detail = "Device not found"


class ThingsBoardError(LextariError):
    status_code = 502
    detail = "ThingsBoard service unavailable"


class AuthError(LextariError):
    status_code = 401
    detail = "Authentication failed"


async def lextari_error_handler(request: Request, exc: LextariError) -> JSONResponse:
    """Handle LextariError subclasses and return structured JSON."""
    logger.error(
        "LextariError: %s — %s",
        exc.__class__.__name__,
        exc.detail,
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "type": exc.__class__.__name__,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
