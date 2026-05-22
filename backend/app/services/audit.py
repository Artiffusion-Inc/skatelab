"""Auth event audit logging helper."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.models.auth_audit_log import AuthAuditLog

if TYPE_CHECKING:
    from litestar import Request
    from sqlalchemy.ext.asyncio import AsyncSession


async def log_auth_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: str | None = None,
    request: Request | None = None,
    **metadata: Any,
) -> None:
    """Record an auth event. Flushes immediately to persist on read-only endpoints."""
    ua = request.headers.get("user-agent", "")[:512] if request else None
    ip = request.client.host if request and request.client else "unknown"
    entry = AuthAuditLog(
        id=str(uuid4()),
        user_id=user_id,
        event_type=event_type,
        ip_address=ip,
        user_agent=ua,
        metadata_=metadata or None,
    )
    db.add(entry)
    await db.flush()
