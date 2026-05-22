# Phase 1b: Auth/Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden auth system with httpOnly cookie auth, email verification gate, User-Agent binding, audit logging, JWT secret check, and token cleanup.

**Architecture:** Progressive migration — cookie middleware as optional layer alongside header auth. Backend sets httpOnly cookies; frontend migrates from localStorage to `credentials: "include"`. Audit log writes to DB table with flush. Token cleanup via arq cron.

**Tech Stack:** Litestar, SQLAlchemy async, Alembic, Valkey (redis.asyncio), arq, Next.js/TypeScript

**Spec:** `docs/specs/2026-05-22-auth-security-hardening-design.md`
**Review:** `docs/specs/2026-05-22-auth-security-hardening-review.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/middleware/cookie_auth.py` | Create | CookieToHeaderMiddleware |
| `backend/app/services/audit.py` | Create | Audit log helper |
| `backend/app/models/auth_audit_log.py` | Create | Audit log ORM model |
| `backend/app/crud/auth_audit_log.py` | Create | Audit log CRUD |
| `backend/app/models/refresh_token.py` | Modify | Add `user_agent_hash` column |
| `backend/app/routes/auth.py` | Modify | Cookie set/clear; email verify gate; UA check; audit logging; refresh dual-input |
| `backend/app/main.py` | Modify | Wire CookieToHeaderMiddleware; reject default JWT secret |
| `backend/app/config.py` | Modify | Cookie config; JWT secret validation |
| `backend/app/schemas.py` | Modify | `RefreshRequest.refresh_token` optional |
| `backend/app/middleware/__init__.py` | Modify | Export CookieToHeaderMiddleware |
| `backend/app/worker.py` | Modify | Add cleanup cron job to FastWorkerSettings |
| `backend/app/crud/refresh_token.py` | Modify | Add UA hash on create; cleanup_expired |
| `backend/app/crud/password_reset_token.py` | Modify | cleanup_expired |
| `frontend/src/lib/api-client.ts` | Modify | Remove localStorage; add `credentials: "include"`; keep silentRefresh |
| `frontend/src/lib/auth.ts` | Modify | Remove token helpers; cookie-based auth |
| `frontend/src/components/auth-provider.tsx` | Modify | Remove token refresh logic; sb_auth cookie check |
| `frontend/src/lib/api/choreography.ts` | Modify | Replace hardcoded URL; `xhr.withCredentials`; remove getAccessToken |
| `frontend/src/app/(app)/choreography/new/page.tsx` | Modify | Remove getAccessToken import |

---

## Wave 1: Independent Backend Foundations (Parallel-Safe)

Tasks 1-5 touch disjoint files. Can run in parallel with separate agents.

---

### Task 1: Cookie Config + Middleware + Wiring

**Files:**

- Create: `backend/app/middleware/cookie_auth.py`
- Modify: `backend/app/middleware/__init__.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Add cookie config to config.py**

In `backend/app/config.py`, add to `AppConfig` class (after `skip_auth`):

```python
cookie_secure: bool = False
cookie_samesite: str = "lax"
```

- [ ] **Step 2: Create cookie_auth.py middleware**

```python
# backend/app/middleware/cookie_auth.py
"""ASGI middleware: reads access_token httpOnly cookie and injects Authorization header."""

from __future__ import annotations

from urllib.parse import unquote

from litestar.datastructures import MutableScopeHeaders
from litestar.types import ASGIApp, Receive, Scope, Send


class CookieToHeaderMiddleware:
    """If no Authorization header present, map access_token cookie to Bearer header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            has_auth = any(k == b"authorization" for k, _ in scope.get("headers", []))
            if not has_auth:
                cookie_value = None
                for k, v in scope.get("headers", []):
                    if k == b"cookie":
                        cookie_value = v.decode("latin-1")
                        break
                if cookie_value:
                    for part in cookie_value.split(";"):
                        part = part.strip()
                        if "=" in part:
                            name, value = part.split("=", 1)
                            if name.strip() == "access_token":
                                headers = MutableScopeHeaders(scope=scope)
                                headers["authorization"] = f"Bearer {unquote(value.strip())}"
                                break
        await self.app(scope, receive, send)
```

- [ ] **Step 3: Update middleware/__init__.py**

```python
# backend/app/middleware/__init__.py
"""Middleware exports."""

from app.middleware.rate_limit import check_rate_limit
from app.middleware.cookie_auth import CookieToHeaderMiddleware

__all__ = ["check_rate_limit", "CookieToHeaderMiddleware"]
```

- [ ] **Step 4: Wire middleware in main.py**

In `backend/app/main.py`, add imports:

```python
from litestar.middleware.base import DefineMiddleware
from app.middleware import CookieToHeaderMiddleware
```

In `create_app()`, change the `middleware` list (currently `middleware=[rate_limit_config.middleware]` at line 140):

```python
middleware=[
    rate_limit_config.middleware,
    DefineMiddleware(CookieToHeaderMiddleware),
],
```

Execution order: RateLimitMiddleware → CookieToHeaderMiddleware → JWTAuth (via `on_app_init`).

- [ ] **Step 5: Write middleware tests**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_cookie_middleware_injects_header(client, db_session):
    """CookieToHeaderMiddleware injects Authorization from access_token cookie."""
    from app.models.user import User
    from app.auth.security import hash_password, create_access_token

    user = User(id="cookie-test", email="cookie@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user_id="cookie-test")
    resp = await client.get("/api/v1/users/me", cookies={"access_token": token})
    assert resp.status_code == 200


async def test_cookie_middleware_does_not_override_header(client, db_session):
    """If Authorization header present, cookie is ignored."""
    from app.models.user import User
    from app.auth.security import hash_password, create_access_token

    user = User(id="header-test", email="header@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user_id="header-test")
    # Send both header and cookie — header wins
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        cookies={"access_token": "invalid-token-value"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 6: Run tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py::test_cookie_middleware_injects_header backend/tests/test_auth_routes.py::test_cookie_middleware_does_not_override_header -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/middleware/cookie_auth.py backend/app/middleware/__init__.py backend/app/config.py backend/app/main.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): CookieToHeaderMiddleware + cookie config + wiring"
```

---

### Task 2: Audit Log Model + CRUD + Helper

**Files:**

- Create: `backend/app/models/auth_audit_log.py`
- Create: `backend/app/crud/auth_audit_log.py`
- Create: `backend/app/services/audit.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Create audit log model**

```python
# backend/app/models/auth_audit_log.py
"""Auth audit log ORM model."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AuthAuditLog(TimestampMixin, Base):
    __tablename__ = "auth_audit_log"
    __table_args__ = (
        Index("ix_auth_audit_log_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
```

- [ ] **Step 2: Add to models/__init__.py**

Add import of `AuthAuditLog` to `backend/app/models/__init__.py` so Alembic can detect it.

- [ ] **Step 3: Create Alembic migration**

Run: `cd /home/michael/Github/skating-biomechanics-ml/backend && uv run alembic revision --autogenerate -m "create_auth_audit_log_table"`

Verify the migration creates `auth_audit_log` table with columns: `id`, `user_id`, `event_type`, `ip_address`, `user_agent`, `metadata`, `created_at`, `updated_at` and indexes on `user_id`, `event_type`, and `(user_id, created_at)`.

Apply: `uv run alembic upgrade head`

- [ ] **Step 4: Create audit log CRUD**

```python
# backend/app/crud/auth_audit_log.py
"""Auth audit log CRUD — insert-only in this phase."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.auth_audit_log import AuthAuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
```

(No read operations in this phase — insert is handled by `services/audit.py`.)

- [ ] **Step 5: Create audit helper service**

```python
# backend/app/services/audit.py
"""Auth event audit logging helper."""

from __future__ import annotations

from uuid import uuid4

from litestar import Request

from app.models.auth_audit_log import AuthAuditLog

if TYPE_CHECKING:
    from typing import Any
    from sqlalchemy.ext.asyncio import AsyncSession

import TYPE_CHECKING


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
```

- [ ] **Step 6: Write audit helper test**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_audit_log_records_login(client, db_session):
    """Successful login creates audit entry."""
    from app.models.user import User
    from app.auth.security import hash_password
    from app.models.auth_audit_log import AuthAuditLog
    from sqlalchemy import select

    user = User(email="audit-login@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "audit-login@example.com", "password": "pass"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuthAuditLog).where(AuthAuditLog.event_type == "login")
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.user_id == user.id
```

- [ ] **Step 7: Run test**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py::test_audit_log_records_login -v`
Expected: FAIL (audit logging not wired yet — will pass after Task 6)

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/auth_audit_log.py backend/app/models/__init__.py backend/app/crud/auth_audit_log.py backend/app/services/audit.py backend/alembic/versions/ backend/tests/test_auth_routes.py
git commit -m "feat(auth): audit log model + CRUD + helper service"
```

---

### Task 3: Refresh Token Model + CRUD (UA Hash + Cleanup)

**Files:**

- Modify: `backend/app/models/refresh_token.py`
- Modify: `backend/app/crud/refresh_token.py`
- Modify: `backend/app/crud/password_reset_token.py`
- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Add user_agent_hash column to model**

In `backend/app/models/refresh_token.py`, add after `last_used_at` (line 31):

```python
user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 2: Create Alembic migration**

Run: `cd /home/michael/Github/skating-biomechanics-ml/backend && uv run alembic revision --autogenerate -m "add_user_agent_hash_to_refresh_tokens"`

Edit the generated migration to add batched backfill after the column add:

```python
def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("user_agent_hash", sa.String(64), nullable=True))

    # Batched backfill to avoid row-level lock contention
    conn = op.get_bind()
    while True:
        result = conn.execute(
            sa.text("UPDATE refresh_tokens SET user_agent_hash = 'legacy' "
                    "WHERE user_agent_hash IS NULL LIMIT 1000")
        )
        if result.rowcount == 0:
            break
```

Apply: `uv run alembic upgrade head`

- [ ] **Step 3: Add cleanup_expired to crud/refresh_token.py**

In `backend/app/crud/refresh_token.py`, append:

```python
async def cleanup_expired(db: AsyncSession, batch_size: int = 500) -> int:
    """Delete expired refresh tokens."""
    from datetime import UTC, datetime

    result = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC)).limit(batch_size)
    )
    await db.flush()
    return result.rowcount
```

Add `delete` import at top: `from sqlalchemy import delete`

- [ ] **Step 4: Add cleanup_expired to crud/password_reset_token.py**

If `delete_expired` already exists (line 54), verify it works correctly. If not, add:

```python
async def cleanup_expired(db: AsyncSession, batch_size: int = 500) -> int:
    """Delete expired password reset tokens."""
    from datetime import UTC, datetime

    result = await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.expires_at < datetime.now(UTC)).limit(batch_size)
    )
    await db.flush()
    return result.rowcount
```

- [ ] **Step 5: Write cleanup test**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_cleanup_expired_refresh_tokens(db_session):
    """cleanup_expired deletes expired refresh tokens."""
    from app.crud.refresh_token import cleanup_expired, create
    from datetime import UTC, datetime, timedelta
    from app.auth.security import hash_token
    import secrets

    # Create an already-expired token
    raw = secrets.token_urlsafe(32)
    token = await create(
        db_session,
        user_id="test-user",
        token_hash=hash_token(raw),
        family_id="family-1",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await db_session.commit()

    deleted = await cleanup_expired(db_session, batch_size=100)
    assert deleted >= 1
```

- [ ] **Step 6: Run test**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py::test_cleanup_expired_refresh_tokens -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/refresh_token.py backend/app/crud/refresh_token.py backend/app/crud/password_reset_token.py backend/alembic/versions/ backend/tests/test_auth_routes.py
git commit -m "feat(auth): user_agent_hash column + cleanup_expired CRUD"
```

---

### Task 4: RefreshRequest Schema + Email Verification Migration

**Files:**

- Modify: `backend/app/schemas.py`
- Modify: Alembic migration (new)
- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Make RefreshRequest.refresh_token optional**

In `backend/app/schemas.py`, change line 47-48:

```python
class RefreshRequest(BaseModel):
    refresh_token: str | None = None
```

- [ ] **Step 2: Create Alembic migration for email verified backfill**

Run: `cd /home/michael/Github/skating-biomechanics-ml/backend && uv run alembic revision -m "set_existing_users_email_verified"`

Edit the migration:

```python
def upgrade() -> None:
    op.execute("UPDATE users SET is_verified = TRUE WHERE is_verified = FALSE")

def downgrade() -> None:
    pass  # No-op downgrade — cannot un-verify users
```

Apply: `uv run alembic upgrade head`

- [ ] **Step 3: Write test for optional RefreshRequest**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_refresh_with_no_body_uses_cookie(client, db_session):
    """Refresh with no body reads refresh_token from cookie."""
    from app.models.user import User
    from app.auth.security import hash_password

    user = User(email="cookie-refresh@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    # Login to get cookies
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookie-refresh@example.com", "password": "pass"},
    )
    assert login_resp.status_code == 200

    # Refresh using only cookies (no body)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={},  # empty body — refresh_token from cookie
    )
    # Will pass once refresh dual-input is wired (Task 6)
    assert resp.status_code == 200
```

- [ ] **Step 4: Run test**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py::test_refresh_with_no_body_uses_cookie -v`
Expected: FAIL (refresh dual-input not wired yet — will pass after Task 6)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/alembic/versions/ backend/tests/test_auth_routes.py
git commit -m "feat(auth): optional RefreshRequest + email verified backfill migration"
```

---

### Task 5: JWT Secret Hardening

**Files:**

- Modify: `backend/app/main.py`
- Test: `backend/tests/test_main.py`

- [ ] **Step 1: Add JWT secret check to main.py**

In `backend/app/main.py`, in `create_app()`, before `return Litestar(...)`:

```python
from os import environ

if environ.get("SKIP_JWT_SECRET_CHECK") != "true" and settings.jwt.secret_key.get_secret_value() == "change-me-to-a-random-secret":
    raise RuntimeError(
        "JWT secret key is using the default value. "
        "Set JWT_SECRET_KEY environment variable to a secure random string. "
        "Set SKIP_JWT_SECRET_CHECK=true to bypass (dev only)."
    )
```

- [ ] **Step 2: Write test**

In `backend/tests/test_main.py`, append:

```python
from unittest.mock import MagicMock, patch
import pytest


def test_default_jwt_secret_rejected():
    """App fails to start with default JWT secret unless SKIP_JWT_SECRET_CHECK=true."""
    from app.main import create_app

    mock_settings = MagicMock()
    mock_settings.jwt.secret_key.get_secret_value.return_value = "change-me-to-a-random-secret"
    mock_settings.app.log_level = "INFO"

    with patch("app.main.get_settings", return_value=mock_settings):
        with pytest.raises(RuntimeError, match="default value"):
            create_app()


def test_skip_jwt_secret_check_allows_default():
    """SKIP_JWT_SECRET_CHECK=true bypasses the secret check."""
    import os
    from app.main import create_app

    mock_settings = MagicMock()
    mock_settings.jwt.secret_key.get_secret_value.return_value = "change-me-to-a-random-secret"
    mock_settings.app.log_level = "INFO"
    mock_settings.cors.origins = []
    mock_settings.app.skip_auth = False

    with patch("app.main.get_settings", return_value=mock_settings):
        with patch.dict(os.environ, {"SKIP_JWT_SECRET_CHECK": "true"}):
            # Should not raise
            app = create_app()
            assert app is not None
```

- [ ] **Step 3: Run tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_main.py::test_default_jwt_secret_rejected backend/tests/test_main.py::test_skip_jwt_secret_check_allows_default -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/tests/test_main.py
git commit -m "feat(auth): reject default JWT secret unconditionally with SKIP override"
```

---

## Wave 2: Auth Routes (Sequential — Single Agent Only)

All tasks modify `backend/app/routes/auth.py`. Must be sequential.

---

### Task 6: Cookie Management in Auth Routes

**Files:**

- Modify: `backend/app/routes/auth.py`
- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Add imports to auth.py**

At top of `backend/app/routes/auth.py`, add:

```python
from litestar import Response
from litestar.datastructures import Cookie
from litestar.status_code import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT
from app.config import get_settings
```

- [ ] **Step 2: Add cookie helper methods to AuthController**

Add to `AuthController` class, after `_issue_token_pair`:

```python
def _set_auth_cookies(self, response: Response, access: str, refresh: str) -> Response:
    settings = get_settings()
    response.cookies.append(Cookie(
        key="access_token", value=access, httponly=True,
        secure=settings.app.cookie_secure, samesite=settings.app.cookie_samesite,
        max_age=settings.jwt.access_token_expire_minutes * 60, path="/",
    ))
    response.cookies.append(Cookie(
        key="refresh_token", value=refresh, httponly=True,
        secure=settings.app.cookie_secure, samesite=settings.app.cookie_samesite,
        max_age=settings.jwt.refresh_token_expire_days * 86400, path="/api/v1/auth",
    ))
    response.cookies.append(Cookie(
        key="sb_auth", value="1", httponly=False,
        secure=settings.app.cookie_secure, samesite=settings.app.cookie_samesite,
        max_age=settings.jwt.refresh_token_expire_days * 86400, path="/",
    ))
    return response

def _clear_auth_cookies(self, response: Response) -> Response:
    response.cookies.append(Cookie(key="access_token", value="", max_age=0, path="/"))
    response.cookies.append(Cookie(key="refresh_token", value="", max_age=0, path="/api/v1/auth"))
    response.cookies.append(Cookie(key="sb_auth", value="", max_age=0, path="/"))
    return response
```

- [ ] **Step 3: Update register to set cookies**

Change `register` return type to `Response[TokenResponse]` and wrap in cookie response:

```python
@post("/register", status_code=HTTP_201_CREATED)
async def register(
    self, request: Request, db: DbDep, data: RegisterRequest
) -> Response[TokenResponse]:
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"register_ip:{ip}", max_requests=5, window_seconds=60)
    await check_rate_limit(f"register_email:{data.email}", max_requests=3, window_seconds=3600)

    existing = await get_by_email(db, data.email)
    if existing:
        raise ClientException(status_code=409, detail="Email already registered")

    user = await create_user(
        db,
        email=data.email,
        hashed_password=hash_password(data.password),
        display_name=data.display_name,
    )
    tokens = await self._issue_token_pair(db, user.id)
    response = Response(content=tokens, status_code=HTTP_201_CREATED)
    return self._set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
```

- [ ] **Step 4: Update login to set cookies**

Change `login` return type to `Response[TokenResponse]`:

```python
@post("/login", status_code=HTTP_200_OK)
async def login(
    self, request: Request, db: DbDep, data: LoginRequest
) -> Response[TokenResponse]:
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"login_ip:{ip}", max_requests=10, window_seconds=60)
    await check_rate_limit(f"login_email:{data.email}", max_requests=5, window_seconds=300)

    user = await get_by_email(db, data.email)
    if not user or not verify_password(data.password, user.hashed_password):
        raise ClientException(status_code=401, detail="Invalid email or password")

    if not user.is_verified:
        raise ClientException(
            status_code=403,
            detail="Email not verified. Check your inbox.",
        )

    tokens = await self._issue_token_pair(db, user.id)
    response = Response(content=tokens, status_code=HTTP_200_OK)
    return self._set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
```

- [ ] **Step 5: Update refresh to dual-input + cookies**

Change `refresh` return type to `Response[TokenResponse]`:

```python
@post("/refresh", status_code=HTTP_200_OK)
async def refresh(
    self, request: Request, db: DbDep, data: RefreshRequest
) -> Response[TokenResponse]:
    ip = request.client.host if request.client else "unknown"
    await check_rate_limit(f"refresh_ip:{ip}", max_requests=20, window_seconds=60)

    # Dual-input: cookie first, body fallback
    refresh_from_cookie = request.cookies.get("refresh_token")
    token = refresh_from_cookie or data.refresh_token
    if not token:
        raise ClientException(status_code=401, detail="Refresh token required")

    token_hash = hash_token(token)
    existing = await get_active_by_hash(db, token_hash)
    if not existing:
        raise ClientException(status_code=401, detail="Invalid or expired refresh token")

    # Reuse detection
    if existing.last_used_at is not None:
        await revoke_family(db, existing.family_id)
        raise ClientException(status_code=401, detail="Token reuse detected. All sessions revoked.")

    # UA binding check
    import hashlib
    current_ua_hash = hashlib.sha256(
        (request.headers.get("user-agent") or "").encode()
    ).hexdigest()
    if existing.user_agent_hash and existing.user_agent_hash != current_ua_hash:
        await revoke_family(db, existing.family_id)
        raise ClientException(
            status_code=401,
            detail="Session terminated. Token used from different device.",
        )

    await mark_used(db, existing)
    tokens = await self._issue_token_pair(db, existing.user_id, family_id=existing.family_id)
    response = Response(content=tokens, status_code=HTTP_200_OK)
    return self._set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
```

- [ ] **Step 6: Update _issue_token_pair to store UA hash**

Modify `_issue_token_pair` to accept and store `user_agent_hash`:

```python
async def _issue_token_pair(
    self, db: AsyncSession, user_id: str, family_id: str | None = None, *, request: Request | None = None
) -> TokenResponse:
    import hashlib
    settings = get_settings()
    access = create_access_token(user_id=user_id)
    refresh = secrets.token_urlsafe(32)
    ua_hash = hashlib.sha256(
        (request.headers.get("user-agent") or "").encode()
    ).hexdigest() if request else None

    token_record = await create_refresh_token(
        db,
        user_id=user_id,
        token_hash=hash_token(refresh),
        family_id=family_id or str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt.refresh_token_expire_days),
    )
    # Update UA hash after creation
    if ua_hash:
        token_record.user_agent_hash = ua_hash
        db.add(token_record)
        await db.flush()

    return TokenResponse(access_token=access, refresh_token=refresh)
```

Update all callers of `_issue_token_pair` to pass `request=request`:
- In `register`: `tokens = await self._issue_token_pair(db, user.id, request=request)`
- In `login`: `tokens = await self._issue_token_pair(db, user.id, request=request)`
- In `refresh`: `tokens = await self._issue_token_pair(db, existing.user_id, family_id=existing.family_id, request=request)`

- [ ] **Step 7: Update logout to clear cookies**

```python
@post("/logout", status_code=HTTP_204_NO_CONTENT)
async def logout(self, request: Request, db: DbDep, data: RefreshRequest) -> Response[None]:
    refresh_from_cookie = request.cookies.get("refresh_token")
    token = refresh_from_cookie or data.refresh_token
    if token:
        token_hash = hash_token(token)
        existing = await get_active_by_hash(db, token_hash)
        if existing:
            await revoke(db, existing)
    response = Response(content=None, status_code=HTTP_204_NO_CONTENT)
    return self._clear_auth_cookies(response)
```

- [ ] **Step 8: Write cookie tests**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_login_sets_cookies(client, db_session):
    """Login sets access_token, refresh_token, and sb_auth cookies."""
    from app.models.user import User
    from app.auth.security import hash_password

    user = User(email="cookies@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookies@example.com", "password": "pass"},
    )
    assert resp.status_code == 200
    cookies = {c.name: c for c in resp.cookies.jar}
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    assert "sb_auth" in cookies
    assert cookies["access_token"]["httponly"] is True
    assert cookies["refresh_token"]["httponly"] is True
    assert cookies["sb_auth"]["httponly"] is False


async def test_logout_clears_cookies(client, db_session):
    """Logout clears all auth cookies."""
    from app.models.user import User
    from app.auth.security import hash_password

    user = User(email="logout-cookies@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout-cookies@example.com", "password": "pass"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 204
    # All cookies should be cleared (max_age=0)
    for cookie in resp.cookies.jar:
        assert cookie.value == "" or cookie.get("max-age") == 0
```

- [ ] **Step 9: Run tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py -v -k "cookie or logout_clears"`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add backend/app/routes/auth.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): cookie management + email verify gate + UA binding + refresh dual-input"
```

---

### Task 7: Audit Logging in Auth Routes

**Files:**

- Modify: `backend/app/routes/auth.py`
- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Add audit import to auth.py**

At top of `backend/app/routes/auth.py`:

```python
from app.services.audit import log_auth_event
```

- [ ] **Step 2: Add audit calls to each auth method**

In `register`, after user creation (before return):

```python
await log_auth_event(db, "login", user_id=user.id, request=request)
```

In `login`, after successful password check (before cookie set):

```python
await log_auth_event(db, "login", user_id=user.id, request=request)
```

In `login`, after failed password check (before raising exception):

```python
await log_auth_event(db, "login_failed", user_id=user.id if user else None, request=request)
```

In `refresh`, after reuse detection:

```python
await log_auth_event(db, "reuse_detected", user_id=existing.user_id, request=request, family_id=existing.family_id)
```

In `refresh`, after UA mismatch:

```python
await log_auth_event(db, "ua_mismatch", user_id=existing.user_id, request=request, family_id=existing.family_id)
```

In `forgot_password`, after creating reset token:

```python
await log_auth_event(db, "password_reset_request", user_id=user.id if user else None, request=request)
```

In `reset_password`, after successful reset:

```python
await log_auth_event(db, "password_reset_complete", user_id=user.id, request=request)
```

In `logout`, after revoking:

```python
await log_auth_event(db, "logout", user_id=None, request=request)
```

In `verify_email`, after successful verification:

```python
await log_auth_event(db, "email_verify", user_id=user.id, request=request)
```

- [ ] **Step 3: Write audit logging tests**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_audit_login_failed(client, db_session):
    """Failed login creates login_failed audit entry."""
    from app.models.auth_audit_log import AuthAuditLog
    from sqlalchemy import select

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401

    result = await db_session.execute(
        select(AuthAuditLog).where(AuthAuditLog.event_type == "login_failed")
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.ip_address is not None


async def test_audit_logout(client, db_session):
    """Logout creates audit entry."""
    from app.models.user import User
    from app.auth.security import hash_password
    from app.models.auth_audit_log import AuthAuditLog
    from sqlalchemy import select

    user = User(email="audit-logout@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "audit-logout@example.com", "password": "pass"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    result = await db_session.execute(
        select(AuthAuditLog).where(AuthAuditLog.event_type == "logout")
    )
    entry = result.scalar_one_or_none()
    assert entry is not None
```

- [ ] **Step 4: Run all auth tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/auth.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): audit logging across all auth endpoints"
```

---

### Task 8: Email Verification Gate + UA Binding Tests

**Files:**

- Test: `backend/tests/test_auth_routes.py`

- [ ] **Step 1: Write email verification gate test**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_login_unverified_email(client, db_session):
    """Login with unverified email returns 403."""
    from app.models.user import User
    from app.auth.security import hash_password

    user = User(email="unverified@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=False)
    db_session.add(user)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": "pass"},
    )
    assert resp.status_code == 403
    assert "not verified" in resp.json()["detail"].lower() or "not verified" in str(resp.json()).lower()
```

- [ ] **Step 2: Write UA binding test**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_ua_mismatch_revokes_family(client, db_session):
    """Refresh with different User-Agent revokes entire family."""
    from app.models.user import User
    from app.auth.security import hash_password

    user = User(email="ua-test@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    # Login with UA "Original/1.0"
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ua-test@example.com", "password": "pass"},
        headers={"User-Agent": "Original/1.0"},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Refresh with same UA — should succeed
    resp1 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"User-Agent": "Original/1.0"},
    )
    assert resp1.status_code == 200
    new_refresh = resp1.json()["refresh_token"]

    # Refresh new token with DIFFERENT UA — should fail and revoke family
    resp2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
        headers={"User-Agent": "Attacker/1.0"},
    )
    assert resp2.status_code == 401
    assert "different device" in resp2.json()["detail"].lower() or "terminated" in resp2.json()["detail"].lower()


async def test_legacy_token_skips_ua_check(client, db_session):
    """Legacy refresh tokens (user_agent_hash='legacy') skip UA check."""
    from app.models.user import User
    from app.models.refresh_token import RefreshToken
    from app.auth.security import hash_password, hash_token
    from datetime import UTC, datetime, timedelta
    import secrets

    user = User(email="legacy-ua@example.com", hashed_password=hash_password("pass"), is_active=True, is_verified=True)
    db_session.add(user)
    await db_session.flush()

    # Create a token with legacy UA hash directly
    raw = secrets.token_urlsafe(32)
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        family_id="legacy-family",
        is_revoked=False,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        user_agent_hash="legacy",
    )
    db_session.add(token)
    await db_session.flush()

    # Refresh with any UA — should succeed (legacy token)
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw},
        headers={"User-Agent": "AnyBrowser/1.0"},
    )
    assert resp.status_code == 200
```

- [ ] **Step 3: Run tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py -v -k "unverified or ua_mismatch or legacy_token"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_auth_routes.py
git commit -m "test(auth): email verify gate + UA binding tests"
```

---

## Wave 3: Frontend Cookie Migration (Sequential — Single Agent)

---

### Task 9: Frontend api-client.ts Migration

**Files:**

- Modify: `frontend/src/lib/api-client.ts`

- [ ] **Step 1: Remove localStorage token helpers**

Remove or stub the following from `frontend/src/lib/api-client.ts`:
- `TOKEN_KEY`, `REFRESH_KEY` constants
- `getAccessToken()`, `getRefreshToken()` — replace with no-op stubs returning `null`
- `setTokens()` — replace with no-op stub
- `authHeaders()` — remove entirely

Keep `clearTokens()` but change it to only clear `sb_auth`:

```typescript
export function clearTokens(): void {
  document.cookie = "sb_auth=; path=/; max-age=0"
}
```

Keep `setTokens` as a no-op stub for rollback safety:

```typescript
export function setTokens(_access: string, _refresh: string): void {
  // No-op: cookies set by backend. Stub kept for rollback compat.
}
```

- [ ] **Step 2: Add credentials: "include" to apiFetch**

In the `apiFetch` function, add `credentials: "include"` to the `fetch` call:

```typescript
res = await fetch(`${API_BASE}${path}`, {
  ...rest,
  credentials: "include",
  headers: { ...headers },
})
```

- [ ] **Step 3: Add credentials: "include" to authFetch**

In the `authFetch` function, add `credentials: "include"` to the `fetch` call.

- [ ] **Step 4: Add credentials: "include" to apiDelete**

In the `apiDelete` function, add `credentials: "include"` to the `fetch` call.

- [ ] **Step 5: Update silentRefresh to not store tokens**

In the `silentRefresh` mechanism (or equivalent 401 retry logic), remove `setTokens(data.access_token, data.refresh_token)`. The backend sets new cookies via `Set-Cookie` headers. The frontend just retries the original request.

```typescript
// In the 401 retry handler:
const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
})
if (refreshRes.ok) {
  // Cookies auto-updated by Set-Cookie headers. Just retry.
  // Remove any setTokens() call here.
}
```

- [ ] **Step 6: Run type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api-client.ts
git commit -m "feat(auth): migrate api-client to cookie auth + credentials:include"
```

---

### Task 10: Frontend auth.ts + auth-provider.tsx Migration

**Files:**

- Modify: `frontend/src/lib/auth.ts`
- Modify: `frontend/src/components/auth-provider.tsx`

- [ ] **Step 1: Update auth.ts**

Remove all re-exports of `getAccessToken`, `getRefreshToken`. Update functions:

```typescript
export async function login(data: LoginRequest): Promise<UserResponse> {
  return apiFetch("/auth/login", UserResponseSchema, {
    method: "POST",
    auth: false,
    headers: JSON_POST,
    body: JSON.stringify(data),
  })
}

export async function register(data: RegisterRequest): Promise<UserResponse> {
  return apiFetch("/auth/register", UserResponseSchema, {
    method: "POST",
    auth: false,
    headers: JSON_POST,
    body: JSON.stringify(data),
  })
}

export async function refreshToken(): Promise<void> {
  await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: JSON_POST,
  }).catch(() => {
    redirect("/login")
  })
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: JSON_POST,
    body: JSON.stringify({}),
  }).catch(() => {})
  clearTokens()
}
```

- [ ] **Step 2: Update auth-provider.tsx**

Replace `getAccessToken() || getRefreshToken()` mount check with `sb_auth` cookie check:

```typescript
useMountEffect(() => {
  if (devMockAuth && isDevelopment) {
    // ... dev mock unchanged ...
    return
  }

  const hasSession = typeof document !== "undefined" && document.cookie.includes("sb_auth=1")
  if (!hasSession) {
    setIsLoading(false)
    return
  }

  auth
    .fetchMe()
    .then(setUser)
    .catch(async () => {
      try {
        await auth.refreshToken()
        const u = await auth.fetchMe()
        setUser(u)
      } catch {
        router.push("/login")
      }
    })
    .finally(() => setIsLoading(false))
})
```

Remove any `setTokens` calls from login/register handlers.

- [ ] **Step 3: Run type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/auth.ts frontend/src/components/auth-provider.tsx
git commit -m "feat(auth): migrate auth.ts + auth-provider to cookie auth"
```

---

### Task 11: Frontend Choreography XHR Fix

**Files:**

- Modify: `frontend/src/lib/api/choreography.ts`
- Modify: `frontend/src/app/(app)/choreography/new/page.tsx`

- [ ] **Step 1: Fix uploadMusicFile in choreography.ts**

Replace hardcoded URL and manual Authorization with cookie auth:

```typescript
export async function uploadMusicFile(
  file: File,
  onProgress?: (progress: number) => void,
): Promise<UploadMusicResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_BASE}/choreography/music/upload`)
    xhr.withCredentials = true  // Send cookies
    xhr.setRequestHeader("Accept", "application/json")

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error("Upload failed"))

    const form = new FormData()
    form.append("file", file)
    xhr.send(form)
  })
}
```

Remove `getAccessToken` import from this file. Update the function signature to remove the `token` parameter.

- [ ] **Step 2: Update choreography/new/page.tsx**

Remove `getAccessToken` import. Update all calls to `uploadMusicFile` to remove the token argument:

```typescript
// Before: uploadMusicFile(file, token, onProgress)
// After:  uploadMusicFile(file, onProgress)
```

- [ ] **Step 3: Run type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/choreography.ts frontend/src/app/\(app\)/choreography/new/page.tsx
git commit -m "fix(auth): choreography XHR cookie auth + remove hardcoded localhost"
```

---

## Wave 4: Worker + Integration

---

### Task 12: Token Cleanup Cron Job

**Files:**

- Modify: `backend/app/worker.py`

- [ ] **Step 1: Add cleanup cron to FastWorkerSettings**

In `backend/app/worker.py`, add the cleanup function and register it:

```python
from arq import cron


async def cleanup_expired_tokens(ctx: dict) -> int:
    """Delete expired refresh tokens and password reset tokens."""
    from app.crud.refresh_token import cleanup_expired as cleanup_refresh
    from app.crud.password_reset_token import cleanup_expired as cleanup_reset
    from app.database import async_session_factory

    async with async_session_factory() as db:
        n1 = await cleanup_refresh(db, batch_size=500)
        n2 = await cleanup_reset(db, batch_size=500)
        await db.commit()
        return n1 + n2
```

In `FastWorkerSettings`, change `cron_jobs = []` to:

```python
cron_jobs = [
    cron(cleanup_expired_tokens, hour="*", minute=7),
]
```

- [ ] **Step 2: Write cron test**

In `backend/tests/test_auth_routes.py`, append:

```python
async def test_cleanup_cron_deletes_expired(db_session):
    """cleanup_expired_tokens task deletes expired tokens."""
    from app.crud.refresh_token import create, cleanup_expired
    from app.auth.security import hash_token
    from datetime import UTC, datetime, timedelta
    import secrets

    # Create expired token
    raw = secrets.token_urlsafe(32)
    await create(
        db_session,
        user_id="cron-user",
        token_hash=hash_token(raw),
        family_id="cron-family",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await db_session.commit()

    deleted = await cleanup_expired(db_session, batch_size=100)
    assert deleted >= 1
```

- [ ] **Step 3: Run test**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py::test_cleanup_cron_deletes_expired -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/worker.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): token cleanup cron job in FastWorkerSettings"
```

---

### Task 13: Full Integration Test Run

**Files:**

- Run: `backend/tests/`
- Run: `frontend/` type check

- [ ] **Step 1: Run backend auth tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/test_auth_routes.py backend/tests/test_main.py -v`
Expected: All PASS

- [ ] **Step 2: Run full backend test suite**

Run: `cd /home/michael/Github/skating-biomechanics-ml && uv run pytest backend/tests/ -v --timeout=120`
Expected: All PASS

- [ ] **Step 3: Frontend type check**

Run: `cd /home/michael/Github/skating-biomechanics-ml/frontend && bunx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "test(auth): integration tests green for Phase 1b auth hardening"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Requirement | Task |
|---|---|
| CookieToHeaderMiddleware | Task 1 |
| Cookie management (set/clear) | Task 6 |
| Cookie config (secure, samesite) | Task 1 |
| Frontend api-client migration | Task 9 |
| Frontend auth.ts migration | Task 10 |
| Frontend auth-provider.tsx migration | Task 10 |
| Choreography XHR fix | Task 11 |
| Email verification gate | Task 6 |
| User-Agent binding | Task 6, Task 8 |
| Audit log model + CRUD + helper | Task 2 |
| Audit logging in routes | Task 7 |
| RefreshRequest optional | Task 4 |
| JWT secret hardening | Task 5 |
| Token cleanup (arq cron) | Task 3, Task 12 |
| Alembic migrations | Task 2, Task 3, Task 4 |

### 2. Placeholder Scan

- No TBD/TODO found
- No "add appropriate error handling"
- No "write tests for the above" without code
- No "similar to Task N"
- All code steps contain actual code

### 3. Type Consistency

- `CookieToHeaderMiddleware` defined in Task 1, exported in `__init__.py` same task, wired in `main.py` same task — consistent
- `_set_auth_cookies` / `_clear_auth_cookies` defined in Task 6, used in Task 6 — consistent
- `log_auth_event(db, event_type, *, user_id, request, **metadata)` defined in Task 2, called with same signature in Task 7 — consistent
- `RefreshRequest.refresh_token: str | None = None` set in Task 4, used in Task 6 `data.refresh_token` — consistent
- `user_agent_hash` column added in Task 3, set in Task 6 `_issue_token_pair`, checked in Task 6 `refresh` — consistent
- `cleanup_expired(db, batch_size=500)` defined in Task 3, called in Task 12 — consistent
- `is_verified` used in Task 6 (not `is_email_verified`) — matches actual DB column
- Frontend: `uploadMusicFile(file, onProgress)` signature in Task 11 matches call in `choreography/new/page.tsx` same task — consistent
