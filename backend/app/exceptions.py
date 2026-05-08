"""App-level exception handlers for Litestar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.response import Response

from app.schemas import ErrorResponse

if TYPE_CHECKING:
    from litestar import Request as LitestarRequest
    from litestar.exceptions import HTTPException


def http_exception_handler(request: LitestarRequest, exc: HTTPException) -> Response:
    """Map Litestar HTTPException to structured ErrorResponse."""
    detail_str = str(exc.detail)
    body = ErrorResponse(
        error=detail_str,
        message=detail_str,
        path=str(request.url.path),
    )
    return Response(
        content=body.model_dump(),
        status_code=exc.status_code,
        media_type="application/json",
    )
