# Phase 1b Auth/Security Hardening — 5-Agent Deep Review Report

**Date:** 2026-05-22
**Reviewers:** Security Architect, Backend Architect, Frontend Architect, Parallelization Analyst, QA & Migration Specialist

---

## Critical Issues (Must Fix Before Implementation)

### C1. Column Name Mismatch
Spec uses `is_email_verified`, actual DB column is `is_verified` (from migration `2026_05_07_1200-c7d8e9f0a1b2`). All references must use `is_verified`.

### C2. Cookie Parsing Bug in Middleware
Spec's `CookieToHeaderMiddleware` uses `MutableScopeHeaders(scope=scope).get("cookie", "")` — `MutableScopeHeaders` does not expose `.get()` for individual headers by lowercase key. This will raise `AttributeError` at runtime. Fix: iterate `scope["headers"]` directly to find the `cookie` header, or use `headers.getall("cookie")`.

### C3. Audit Log Entries Silently Lost
`db.add(entry)` without `await db.flush()` means entries never reach the DB on read-only endpoints (e.g., failed login — SELECT only, no flush/commit). On rollback, entries are also lost. For security events, this is unacceptable. Fix: `await db.flush()` inside `log_auth_event()`. For events that should survive rollback (reuse_detected, ua_mismatch), consider a separate session or at minimum flush before the exception.

### C4. RefreshRequest Must Be Optional
Litestar validates `data: RefreshRequest` body before the handler runs. If frontend sends cookie-only (no JSON body), `refresh_token` is a required field → `ValidationException`. Fix: `refresh_token: str | None = None` in schema, then `refresh_from_cookie or data.refresh_token` in handler.

### C5. Cookie Path Mismatch on Logout
`_clear_auth_cookies` sets `path="/"` for all 3 cookies, but `refresh_token` was set with `path="/api/v1/auth"`. Browser won't clear a cookie unless `Path` matches exactly. Fix: clear each cookie with its original path.

### C6. User-Agent String Truncation Missing
`auth_audit_log.user_agent` is `String(512)`. `log_auth_event` doesn't truncate. UA strings > 512 chars (rare but possible) will crash with `DataError`. Fix: truncate to 512 before insert.

### C7. Frontend `uploadMusicFile` Not Covered
`frontend/src/lib/api/choreography.ts` uses `XMLHttpRequest` with hardcoded `http://localhost:8000` and manual `Authorization: Bearer ${token}`. Not mentioned in spec. Must: (1) use env-configured base URL, (2) replace `Authorization` header with `xhr.withCredentials = true`, (3) remove `getAccessToken` import from `choreography/new/page.tsx`.

### C8. `silentRefresh` Must Be Kept
Spec says "remove manual token refresh logic" from auth-provider, but the 401→refresh→retry loop in `api-client.ts` is essential. Without it, a 15-minute access token expiry means every expired request redirects to login. Fix: keep `silentRefresh` mechanism, but remove `setTokens`/`localStorage` — trust browser cookie jar after refresh.

---

## Important Issues (Should Address)

### I1. No Forced Re-Auth on Migration
Existing stolen tokens remain valid indefinitely (up to 7-day refresh expiry). Consider a migration that revokes all existing refresh tokens and forces re-login on first cookie-auth deployment. Risk: UX disruption for all users, but eliminates legacy attack surface.

### I2. `sb_auth` Is a Session Oracle
The non-httpOnly `sb_auth` cookie is readable by JavaScript. An XSS payload can check session state. Recommendation: either make it httpOnly with a signed value, or remove it and use a lightweight `/api/v1/auth/session` endpoint for SSR.

### I3. Probabilistic Cleanup Ineffective
1/100 probability means ~10 days before first cleanup in dev/staging. Recommendation: remove probabilistic cleanup entirely, rely solely on arq cron in `FastWorkerSettings.cron_jobs` running hourly. Deterministic, testable, no math surprises.

### I4. JWT Secret Check Too Weak
`settings.app.log_level != "DEBUG"` is not a reliable production indicator. A production app can be `INFO` with a default secret. Better: require `JWT_SECRET_KEY` is non-default unconditionally, with an explicit `SKIP_JWT_SECRET_CHECK=true` env var for local dev.

### I5. Migration Backfill Should Be Batched
`UPDATE refresh_tokens SET user_agent_hash = 'legacy'` locks all rows. On large tables, this blocks concurrent token creation. Use batched updates (LIMIT 1000 per transaction) or a post-deployment script.

### I6. Frontend Dual-Path During Transition
Spec removes all localStorage helpers. If cookie auth breaks in production, rollback requires a frontend revert. Recommendation: keep localStorage as fallback for one release cycle, or add a `useCookies` feature flag.

### I7. `__Host-` Cookie Prefix
Using `__Host-access_token` prefix enforces `Secure` + no `Domain` + `Path=/`. Prevents cookie tossing attacks from subdomains. Low effort, high security gain.

### I8. `request.client` None Guard
`request.client` can be `None` in some proxy setups. Audit helper must handle this — use `request.client.host if request.client else "unknown"`. Rate limiting already does this, but audit helper must match.

---

## Parallelization Analysis

### Wave 1: Independent Foundations (parallel, 5 groups)

| Group | Files | Agent |
|-------|-------|-------|
| A: Config + Middleware | `config.py`, `middleware/cookie_auth.py`, `__init__.py`, `main.py` (wiring + JWT hardening) | 1 |
| B: Audit Log | `models/auth_audit_log.py`, migration, `crud/auth_audit_log.py`, `services/audit.py` | 2 |
| C: Refresh Token Hardening | `models/refresh_token.py` (UA hash), migration, `crud/refresh_token.py` (UA + cleanup) | 3 |
| D: Password Reset Cleanup | `crud/password_reset_token.py` (lazy cleanup) | 4 |
| E: Schema | `schemas.py` (`RefreshRequest` optional, 403 error) | 5 |

### Wave 2: Auth Routes (sequential, single agent)

All tasks touch `routes/auth.py`. Must be single agent.
1. Cookie set/clear helpers
2. Email verification gate
3. UA binding check
4. Audit logging calls

### Wave 3: Frontend Migration (sequential, single agent)

1. `api-client.ts` — remove localStorage, add `credentials: "include"`, keep silentRefresh
2. `auth.ts` — remove token storage, cookie-based auth
3. `auth-provider.tsx` — remove token refresh, check `sb_auth` cookie
4. `api.ts` + `choreography.ts` — add `credentials: "include"` / `withCredentials`

### Wave 4: Worker + Integration

1. `worker.py` — add cleanup cron to `FastWorkerSettings`
2. Full test suite + type check

### Critical Path
Config+Middleware → Routes (cookie mgmt) → Frontend → Integration tests

---

## Missing Tests (26 total)

1. Cookie middleware: injects header when absent
2. Cookie middleware: does NOT override existing Authorization
3. Cookie middleware: URL-decoded cookie values
4. Login sets 3 cookies (httpOnly, SameSite, Path, Max-Age)
5. Register sets 3 cookies
6. Refresh sets new cookies
7. Logout clears all 3 cookies (with correct paths)
8. Refresh reads cookie first, falls back to body
9. Refresh with expired cookie + valid body succeeds
10. Login with `is_verified=False` → 403
11. Login with `is_verified=True` → 200
12. 403 response includes verification hint
13. Refresh with matching UA succeeds
14. Refresh with mismatched UA → 401 + family revoke
15. Legacy token (`user_agent_hash='legacy'`) skips UA check
16. Token creation stores UA hash
17. Successful login → audit entry
18. Failed login → audit entry
19. Token reuse → audit entry with family_id
20. UA mismatch → audit entry
21. Password reset request/complete → audit entries
22. Logout → audit entry
23. JWT secret default → RuntimeError in production
24. JWT secret default → OK in DEBUG
25. Cleanup cron deletes expired tokens
26. Header auth still works with cookie middleware active

---

## Rollback Plan

| Phase | Breaks Frontend? | Rollback |
|-------|------------------|----------|
| 1: Audit + JWT + cleanup | No | Safe, no API change |
| 2: Email gate + UA binding | No | Code revert, DB columns stay |
| 3: Cookie middleware + routes | No | Remove middleware from `main.py` |
| 4: Frontend migration | Yes (requires Phase 3) | Revert frontend commit; header auth still works |

**Gap:** Frontend removes all localStorage helpers. A full rollback requires reverting both backend middleware AND frontend. Consider keeping localStorage fallback for one release cycle (I6).

---

## Recommendations Priority Matrix

| # | Issue | Priority | Effort |
|---|-------|----------|--------|
| C1 | Column name `is_verified` not `is_email_verified` | Critical | 5 min |
| C2 | Cookie parsing: use `scope["headers"]` not `MutableScopeHeaders.get` | Critical | 10 min |
| C3 | Audit log: add `await db.flush()` | Critical | 5 min |
| C4 | `RefreshRequest.refresh_token` optional | Critical | 10 min |
| C5 | Logout cookie path must match set path | Critical | 5 min |
| C6 | Truncate UA to 512 chars | Critical | 5 min |
| C7 | Fix `uploadMusicFile` XMLHttpRequest | Critical | 30 min |
| C8 | Keep `silentRefresh`, remove only `setTokens`/`localStorage` | Critical | 15 min |
| I1 | Forced re-auth on migration | Important | 30 min |
| I2 | Harden or remove `sb_auth` | Important | 1 hr |
| I3 | Remove probabilistic cleanup, cron only | Important | 15 min |
| I4 | JWT secret check: unconditional with dev override | Important | 10 min |
| I5 | Batch migration backfill | Important | 30 min |
| I6 | Keep localStorage fallback for one release | Important | 1 hr |
| I7 | `__Host-` cookie prefix | Nice-to-have | 15 min |
| I8 | `request.client` None guard | Important | 5 min |