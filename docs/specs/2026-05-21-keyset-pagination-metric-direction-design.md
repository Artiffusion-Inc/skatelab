# Phase 2a: Keyset Pagination & Metric Direction Fix

**Date:** 2026-05-21
**Status:** Draft
**Depends on:** Phase 1a (connection pooling) — merged

## Problem

### 1. Offset pagination duplicates rows on page turn

`GET /sessions?limit=20&offset=40` uses offset-based pagination. When rows are inserted or deleted between page turns, items shift and either duplicate or vanish.

### 2. Trend direction inverted for "lower is better" metrics

`get_trend` treats `slope > 0` as "improving" and `slope < 0` as "declining" regardless of metric direction. For `direction="lower"` metrics (knee_angle, trunk_lean), a decreasing value is improvement — the trend label is backwards.

### 3. Diagnostics ignore metric direction

`check_declining_trend` always flags `slope < 0` as decline. For "lower is better" metrics, a decreasing slope is improvement. `check_stagnation` and `check_high_variability` are direction-agnostic and are correct.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pagination style | Keyset cursor on `(created_at, id)` | Stable across inserts/deletes, no skipping or duplication |
| Sort order | `created_at DESC` only | `overall_score` has no uniqueness guarantee; client-side sort or separate endpoint later |
| Cursor encoding | Base64 of `created_at\|id` | Opaque to client, easy to decode server-side |
| Direction logic | Inline `if/else` on `mdef.direction` in route and diagnostics | Simple condition, no need for MetricDef methods — direction is a 2-branch check |
| PR calculation | Worker must set `is_pr` direction-aware | Verify and fix worker PR logic; route `get_prs` reads `is_pr=True` from DB, no change needed |

## Changes

### 1. Keyset Pagination — `crud/session.py`

**Current:** `list_by_user(db, user_id, element_type, limit, offset, sort)`

**Target:** `list_by_user(db, user_id, element_type, limit, cursor)`

```python
async def list_by_user(
    db: AsyncSession,
    user_id: str,
    *,
    element_type: str | None = None,
    limit: int = 20,
    cursor: tuple[datetime, str] | None = None,
) -> list[Session]:
    query = (
        select(Session)
        .options(selectinload(Session.metrics))
        .where(Session.user_id == user_id)
    )
    if element_type:
        query = query.where(Session.element_type == element_type)
    if cursor is not None:
        cursor_dt, cursor_id = cursor
        query = query.where(
            (Session.created_at < cursor_dt)
            | ((Session.created_at == cursor_dt) & (Session.id < cursor_id))
        )
    query = query.order_by(Session.created_at.desc(), Session.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    sessions = list(result.scalars().all())
    return sessions
```

The `limit + 1` trick: fetch one extra row to determine `has_more` without a separate count query.

`count_by_user` stays for the initial `total` count only (first page).

### 2. Keyset Pagination — `routes/sessions.py`

**Current:** `limit`, `offset`, `sort` query params → `SessionListResponse(page, page_size, total, pages)`

**Target:** `limit`, `cursor` query params → `SessionListResponse(sessions, next_cursor, has_more, total)`

```python
@get("")
async def list_sessions(
    self,
    user: CurrentUser,
    db: DbDep,
    user_id: str | None = None,
    element_type: str | None = None,
    limit: int = Parameter(default=20, ge=1, le=100),
    cursor: str | None = Parameter(default=None),
) -> SessionListResponse:
    # Decode cursor
    parsed_cursor = None
    if cursor:
        parsed_cursor = _decode_cursor(cursor)

    sessions = await list_by_user(
        db, user_id=target_user_id, element_type=element_type,
        limit=limit, cursor=parsed_cursor,
    )

    has_more = len(sessions) > limit
    sessions = sessions[:limit]

    next_cursor = None
    if has_more:
        last = sessions[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    total = await count_by_user(db, user_id=target_user_id, element_type=element_type)

    return SessionListResponse(
        sessions=[await _session_to_response(s) for s in sessions],
        total=total,
        next_cursor=next_cursor,
        has_more=has_more,
    )
```

Cursor encoding helpers:

```python
import base64

def _encode_cursor(created_at: datetime, session_id: str) -> str:
    payload = f"{created_at.isoformat()}|{session_id}"
    return base64.urlsafe_b64encode(payload.encode()).decode()

def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    payload = base64.urlsafe_b64decode(cursor.encode()).decode()
    dt_str, sid = payload.split("|", 1)
    return datetime.fromisoformat(dt_str), sid
```

### 3. Schema — `schemas.py`

Replace `PaginatedResponse` with cursor-aware response.

**Current:**

```python
class PaginatedResponse(BaseModel):
    total: int
    page: int = 1
    page_size: int = 20
    pages: int = 1

    @property
    def has_next(self) -> bool: ...
    @property
    def has_prev(self) -> bool: ...
```

**Target:**

```python
class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int
    next_cursor: str | None = None
    has_more: bool = False
```

Drop `PaginatedResponse`, `page`, `page_size`, `pages`, `has_next`, `has_prev`. Only `SessionListResponse` uses pagination.

### 4. Direction-aware Trend — `routes/metrics.py:get_trend`

**Current:**

```python
if slope > 0 and r_sq > 0.3:
    trend = "improving"
elif slope < 0 and r_sq > 0.3:
    trend = "declining"
```

**Target:**

```python
improving = (slope > 0) if mdef.direction == "higher" else (slope < 0)
declining = (slope < 0) if mdef.direction == "higher" else (slope > 0)
if improving and r_sq > 0.3:
    trend = "improving"
elif declining and r_sq > 0.3:
    trend = "declining"
```

### 5. Direction-aware Diagnostics — `services/diagnostics.py:check_declining_trend`

**Current:**

```python
def check_declining_trend(*, element, metric, values, metric_label):
    ...
    if slope < 0 and r_squared > 0.5:
        return Finding(...)
```

**Target:**

```python
def check_declining_trend(*, element, metric, values, metric_label, direction):
    ...
    is_decline = (slope < 0) if direction == "higher" else (slope > 0)
    if is_decline and r_squared > 0.5:
        return Finding(...)
```

Caller in `routes/metrics.py:get_diagnostics` passes `direction=mdef.direction`.

### 6. Worker PR Calculation — `worker.py`

Verify how `is_pr` and `prev_best` are set. The worker should:

- For `direction="higher"` metrics: `is_pr = (value > prev_best)` or `is_pr = True` if no previous
- For `direction="lower"` metrics: `is_pr = (value < prev_best)` or `is_pr = True` if no previous

If the worker currently only checks `value > prev_best` (always "higher is better"), fix to use `mdef.direction`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `crud/session.py` | Replace offset with keyset cursor in `list_by_user` | ~20 |
| `routes/sessions.py` | Replace offset/sort params with cursor, encode/decode | ~25 |
| `schemas.py` | Replace `PaginatedResponse` with `SessionListResponse` (cursor-based) | ~10 |
| `routes/metrics.py` | Direction-aware trend in `get_trend`, pass `direction` to diagnostics | ~10 |
| `services/diagnostics.py` | Add `direction` param to `check_declining_trend` | ~5 |
| `worker.py` | Direction-aware `is_pr` calculation | ~10 |
| Tests | Update session pagination tests, add direction-aware trend/diagnostics tests | ~80 |

## Out of Scope

- `overall_score` sort in sessions (no unique key for keyset)
- Auth/security hardening (Phase 1b)
- DB connection pool tuning (`pool_size`, `max_overflow`)
- Metric registry expansion