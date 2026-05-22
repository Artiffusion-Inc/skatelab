# Phase 1b: Auth/Security Hardening

**Date:** 2026-05-22
**Status:** Draft
**Depends on:** Phase 1a (connection pooling) — merged

## Problem

1. **XSS token theft** — JWT stored in `localStorage`, accessible to any injected script. Moving to httpOnly cookies eliminates this attack vector.
2. **No email verification gate** — users can login without verifying email. Enables spam accounts and credential stuffing with unverified identities.
3. **No token binding** — refresh tokens are fully portable. A stolen token works from any device/browser without detection.
4. **Default JWT secret in production** — `JWT_SECRET_KEY` defaults to `"change-me-to-a-random-secret"`. Production deployments can accidentally run with this.
5. **No audit trail** — auth events (login, logout, token revoke, password reset) are not recorded. Impossible to investigate security incidents.
6. **Expired tokens accumulate** — `refresh_tokens` and `password_reset_tokens` grow indefinitely. No cleanup mechanism.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth migration | Progressive — cookie as optional layer, header still works | Zero-downtime, rollback-safe, gradual frontend migration |
| Cookie SameSite | Lax | Blocks cross-site POST/DELETE; sufficient for API-only backend; doesn't break email links |
| Email verification | Required before login | Prevents spam accounts; migration backfills existing users as verified |
| Token binding | User-Agent hash only (no IP) | IP changes on mobile networks cause false positives; UA is stable per session |
| Audit log | DB table, fire-and-forget | Persistent history; structured queries later; no external dependency |
| Token cleanup | Lazy probabilistic + optional arq cron | No per-request overhead; cron handles batch cleanup hourly |
| JWT secret | Reject default in non-DEBUG mode | Prevents accidental production deployment with insecure secret |
| Account lockout | Not implemented | Per-endpoint rate limiting already sufficient; lockout adds UX pain |

## Changes

### 1. Cookie Auth — `middleware/cookie_auth.py` (Create)

ASGI middleware: reads `access_token` httpOnly cookie and injects `Authorization: Bearer <token>` header if no `Authorization` header present.

```python
class CookieToHeaderMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = MutableScopeHeaders(scope=scope)
            if "authorization" not in headers:
                cookie_header = headers.get("cookie", "")
                for part in cookie_header.split(";"):
                    part = part.strip()
                    if "=" in part:
                        name, value = part.split("=", 1)
                        if name.strip() == "access_token":
                            headers["authorization"] = f"Bearer {unquote(value.strip())}"
                            break
        await self.app(scope, receive, send)
```

Wire in `main.py` via `DefineMiddleware(CookieToHeaderMiddleware)` before rate limit middleware.

### 2. Cookie Management — `routes/auth.py` (Modify)

Backend sets 3 cookies on login/register/refresh:

| Cookie | httpOnly | SameSite | Path | Max-Age |
|--------|----------|----------|------|---------|
| `access_token` | yes | Lax | `/` | `access_token_expire_minutes * 60` |
| `refresh_token` | yes | Lax | `/api/v1/auth` | `refresh_token_expire_days * 86400` |
| `sb_auth` | no | Lax | `/` | `refresh_token_expire_days * 86400` |

`sb_auth` is a non-httpOnly flag cookie for SSR: `document.cookie` readable, signals session exists without JWT decode.

Logout: set `max_age=0` on all 3 cookies + revoke refresh token.

Helper methods on `AuthController`:

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
    for name in ("access_token", "refresh_token", "sb_auth"):
        response.cookies.append(Cookie(key=name, value="", max_age=0, path="/"))
    return response
```

Return type changes from `TokenResponse` to `Response[TokenResponse]` for login/register/refresh/logout.

### 3. Cookie Config — `config.py` (Modify)

Add to `AppConfig`:

```python
cookie_secure: bool = False
cookie_samesite: str = "lax"
```

`cookie_secure` defaults to `False` for local dev. Production sets `APP_COOKIE_SECURE=true`.

### 4. Frontend Cookie Migration

**`api-client.ts`:**
- Remove `TOKEN_KEY`, `REFRESH_KEY`, `getAccessToken`, `getRefreshToken`, `setTokens`, `clearTokens`, `authHeaders()`
- Add `credentials: "include"` to all `fetch()` calls
- `clearTokens()` only clears `sb_auth` client-side (backend handles httpOnly cookies)

**`auth.ts`:**
- Remove all localStorage token helpers
- `login()`/`register()` — no token storage, cookies set automatically by backend
- `refreshToken()` — POST `/auth/refresh` with `credentials: "include"`, no body. Backend reads `refresh_token` from cookie first, falls back to `data.refresh_token` from body for backward compat
- `logout()` — POST `/auth/logout`, clear `sb_auth`

**`auth-provider.tsx`:**
- Remove manual token refresh logic
- Check `sb_auth` cookie for session existence
- On 401 → redirect to login

### 5. Email Verification Gate — `routes/auth.py` (Modify)

In `AuthController.login`, after password verification:

```python
if not user.is_email_verified:
    raise ClientException(
        status_code=403,
        detail="Email not verified. Check your inbox.",
    )
```

Response includes hint for frontend to show "resend verification" link.

Migration backfill: `UPDATE users SET is_email_verified = TRUE WHERE is_email_verified IS NULL` — existing users not locked out.

### 6. User-Agent Binding — `models/refresh_token.py` + `routes/auth.py`

New column: `user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)`

On refresh token creation: `user_agent_hash = sha256(request.headers["user-agent"]).hexdigest()`

On refresh: compare current UA hash with stored. Mismatch → revoke entire family + raise 401.

```python
current_ua_hash = hashlib.sha256(
    (request.headers.get("user-agent") or "").encode()
).hexdigest()

if existing.user_agent_hash and existing.user_agent_hash != current_ua_hash:
    await revoke_family(db, existing.family_id)
    await log_auth_event(db, "ua_mismatch", user_id=existing.user_id, request=request, family_id=existing.family_id)
    raise ClientException(
        status_code=401,
        detail="Session terminated. Token used from different device.",
    )
```

Migration: `UPDATE refresh_tokens SET user_agent_hash = 'legacy' WHERE user_agent_hash IS NULL` — legacy tokens skip UA check.

### 7. Audit Log — `models/auth_audit_log.py` + `services/audit.py` + `crud/auth_audit_log.py`

**Model:**

```python
class AuthAuditLog(TimestampMixin, Base):
    __tablename__ = "auth_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    metadata_: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

**Events:**

| Event type | When |
|------------|------|
| `login` | Successful login |
| `login_failed` | Failed login |
| `logout` | Logout |
| `refresh` | Successful refresh |
| `reuse_detected` | Refresh token reuse |
| `ua_mismatch` | UA mismatch on refresh |
| `password_reset_request` | forgot-password |
| `password_reset_complete` | reset-password success |
| `email_verify` | Email verified |
| `token_revoke` | Logout / family revoke |

**Helper:**

```python
async def log_auth_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: str | None = None,
    request: Request | None = None,
    **metadata,
) -> None:
    entry = AuthAuditLog(
        id=str(uuid4()),
        user_id=user_id,
        event_type=event_type,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        metadata_=metadata or None,
    )
    db.add(entry)
```

No flush — entry groups with the main transaction. If the main transaction rolls back, audit entry rolls back too (acceptable for auth events — a failed operation that gets retried will log again).

No query API in this phase. Read via direct SQL or future admin panel.

### 8. JWT Secret Hardening — `main.py` + `config.py`

In `create_app()`, before `Litestar(...)`:

```python
if settings.app.log_level != "DEBUG" and settings.jwt.secret_key.get_secret_value() == "change-me-to-a-random-secret":
    raise RuntimeError(
        "JWT secret key is using the default value. "
        "Set JWT_SECRET_KEY environment variable to a secure random string."
    )
```

Dev environment: `APP_LOG_LEVEL=DEBUG` → no check. Production: must set `JWT_SECRET_KEY`.

### 9. Token Cleanup

**Lazy probabilistic** — in `crud/refresh_token.py`:

```python
async def cleanup_expired(db: AsyncSession, batch_size: int = 100) -> int:
    result = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC)).limit(batch_size)
    )
    await db.flush()
    return result.rowcount
```

Called with ~1/100 probability on each `get_active_by_hash()` call. No per-request overhead on 99% of requests.

Same pattern for `password_reset_tokens` in `crud/password_reset_token.py`.

**Optional arq cron** — `cleanup_expired_tokens` task in `worker.py`, runs hourly. Batch delete expired refresh tokens and password reset tokens.

## Files Changed

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/middleware/cookie_auth.py` | Create | CookieToHeaderMiddleware |
| `backend/app/services/audit.py` | Create | Audit log helper |
| `backend/app/models/auth_audit_log.py` | Create | Audit log ORM model |
| `backend/app/crud/auth_audit_log.py` | Create | Audit log CRUD + cleanup |
| `backend/app/models/refresh_token.py` | Modify | Add `user_agent_hash` column |
| `backend/app/routes/auth.py` | Modify | Cookie set/clear; email verify gate; UA check; audit logging |
| `backend/app/main.py` | Modify | Wire CookieToHeaderMiddleware; reject default JWT secret |
| `backend/app/config.py` | Modify | Cookie config; JWT secret validation |
| `backend/app/schemas.py` | Modify | 403 email-not-verified error schema |
| `backend/app/middleware/__init__.py` | Modify | Export CookieToHeaderMiddleware |
| `backend/app/worker.py` | Modify | Add cleanup cron job |
| `backend/app/crud/refresh_token.py` | Modify | Add UA hash on create; lazy cleanup |
| `backend/app/crud/password_reset_token.py` | Modify | Lazy cleanup |
| `frontend/src/lib/api-client.ts` | Modify | Remove localStorage; add `credentials: "include"` |
| `frontend/src/lib/auth.ts` | Modify | Remove token helpers; cookie-based auth |
| `frontend/src/components/auth-provider.tsx` | Modify | Remove token refresh logic; sb_auth cookie check |

## Alembic Migrations

1. `add_user_agent_hash_to_refresh_tokens` — column + backfill `'legacy'`
2. `create_auth_audit_log_table` — new table with indexes
3. `set_existing_users_email_verified` — `UPDATE users SET is_email_verified = TRUE WHERE is_email_verified IS NULL`

## Risks

| Risk | Mitigation |
|------|------------|
| Frontend migration breaks existing sessions | Cookie auth is additive — header auth still works during migration |
| SameSite=Lax breaks email link flows | Lax allows top-level GET navigations; POST from email links not affected (reset uses POST from our own page) |
| UA mismatch false positives (browser updates) | Browser minor updates don't change UA string significantly; major updates are rare |
| Audit log table grows unbounded | Indexed on `user_id` + `created_at`; optional retention policy in future phase |
| Lazy cleanup too slow under high load | arq cron handles batch cleanup; lazy is best-effort |
| Rollback after partial frontend migration | Header auth continues to work; frontend can revert to localStorage |

## Out of Scope

- Account lockout after failed logins (rate limiting sufficient)
- CSRF double-submit token (SameSite=Lax sufficient for API-only backend)
- Access token UA binding (15-min lifetime, overhead not justified)
- IP binding on refresh (mobile networks change IP frequently)
- Audit log query API (admin panel — future phase)
- JWT secret rotation support (manual env update sufficient for current scale)
- RS256 / asymmetric JWT signing (HS256 adequate for single-service architecture)
