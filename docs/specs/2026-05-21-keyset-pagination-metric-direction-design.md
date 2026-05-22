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

### 4. PR batch fetch uses wrong value for "lower" metrics

`get_current_best_batch` in `crud/session_metric.py` always uses `func.max()` for every metric. For `direction="lower"` metrics, the best value is the minimum, not maximum. This feeds incorrect `current_best` to `check_pr`, causing false positive PRs.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pagination style | Keyset cursor on `(created_at, id)` | Stable across inserts/deletes, no skipping or duplication |
| Sort order | `created_at DESC` only | `overall_score` has no uniqueness guarantee; client-side sort or separate endpoint later |
| Cursor encoding | Raw ISO timestamp + UUID separated by `\|` | URL-safe, debuggable in DevTools, no encryption needed |
| Direction logic | Inline `if/else` on `mdef.direction` | Simple condition, no need for MetricDef methods |
| PR batch fetch | `func.min()` for "lower", `func.max()` for "higher" | Fixes false positive PRs for knee_angle, trunk_lean |
| Backward compat | Drop offset entirely | Frontend doesn't use offset/sort params, clean break |

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

`count_by_user` stays for `total` (returned on every page since frontend uses it for stats summary).

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
    target_user_id = user_id if user_id else user.id
    # ... authorization check ...

    parsed_cursor = None
    if cursor:
        try:
            parsed_cursor = _decode_cursor(cursor)
        except (ValueError, KeyError):
            raise ClientException(status_code=400, detail="Invalid cursor")

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
def _encode_cursor(created_at: datetime, session_id: str) -> str:
    return f"{created_at.isoformat()}|{session_id}"

def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    dt_str, sid = cursor.split("|", 1)
    return datetime.fromisoformat(dt_str), sid
```

Invalid cursor → 400 Bad Request.

### 3. Schema — `schemas.py`

Keep `PaginatedResponse` for `ConnectionListResponse` and `ProgramListResponse`. Replace only `SessionListResponse`:

```python
class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int
    next_cursor: str | None = None
    has_more: bool = False
```

Remove `SessionListResponse`'s inheritance from `PaginatedResponse`.

### 4. Database Index

Add composite index for keyset pagination:

```python
Index("ix_sessions_user_element_created_id_desc", "user_id", "element_type", "created_at", "id")
```

This covers `WHERE user_id = ? AND element_type = ? ORDER BY created_at DESC, id DESC` and the keyset `WHERE` clause.

### 5. Direction-aware Trend — `routes/metrics.py:get_trend`

```python
improving = (slope > 0) if mdef.direction == "higher" else (slope < 0)
declining = (slope < 0) if mdef.direction == "higher" else (slope > 0)
if improving and r_sq > 0.3:
    trend = "improving"
elif declining and r_sq > 0.3:
    trend = "declining"
```

### 6. Direction-aware Diagnostics — `services/diagnostics.py:check_declining_trend`

```python
def check_declining_trend(*, element, metric, values, metric_label, direction):
    ...
    is_decline = (slope < 0) if direction == "higher" else (slope > 0)
    if is_decline and r_squared > 0.5:
        return Finding(...)
```

Caller in `routes/metrics.py:get_diagnostics` passes `direction=mdef.direction`.

### 7. PR Batch Fetch — `crud/session_metric.py:get_current_best_batch`

**Current:**

```python
func.max(SessionMetric.metric_value).label("best_value")
```

**Target:** Direction-aware batch fetch. Two queries: one for "higher" metrics (max), one for "lower" metrics (min), merged.

```python
async def get_current_best_batch(
    db: AsyncSession, user_id: str, element_type: str
) -> dict[str, float]:
    """Get current best value per metric, considering direction."""
    from app.metrics_registry import METRIC_REGISTRY

    higher_metrics = [name for name, m in METRIC_REGISTRY.items() if m.direction == "higher"]
    lower_metrics = [name for name, m in METRIC_REGISTRY.items() if m.direction == "lower"]

    bests: dict[str, float] = {}

    # Higher is better → max value
    if higher_metrics:
        result = await db.execute(
            select(
                SessionMetric.metric_name,
                func.max(SessionMetric.metric_value).label("best_value"),
            )
            .join(Session)
            .where(
                Session.user_id == user_id,
                Session.element_type == element_type,
                Session.status == "done",
                SessionMetric.metric_name.in_(higher_metrics),
            )
            .group_by(SessionMetric.metric_name)
        )
        bests.update({row.metric_name: row.best_value for row in result.all()})

    # Lower is better → min value
    if lower_metrics:
        result = await db.execute(
            select(
                SessionMetric.metric_name,
                func.min(SessionMetric.metric_value).label("best_value"),
            )
            .join(Session)
            .where(
                Session.user_id == user_id,
                Session.element_type == element_type,
                Session.status == "done",
                SessionMetric.metric_name.in_(lower_metrics),
            )
            .group_by(SessionMetric.metric_name)
        )
        bests.update({row.metric_name: row.best_value for row in result.all()})

    return bests
```

Also fix `get_current_best` (single metric) to accept direction and use `desc()` for "higher" / `asc()` for "lower".

### 8. Data Migration — Recalculate `is_pr` and `prev_best`

Historical data for `direction="lower"` metrics has incorrect `is_pr` and `prev_best` values. Add an Alembic migration that:

1. For each `(user_id, element_type, metric_name)` group where direction="lower":
   - Order rows by `metric_value ASC` (lower is better)
   - Mark the minimum as `is_pr=True`, set `prev_best` to the previous minimum
   - Mark all others as `is_pr=False`, `prev_best=None`

2. For each group where direction="higher":
   - Order rows by `metric_value DESC`
   - Mark the maximum as `is_pr=True`, set `prev_best` to the previous maximum
   - Mark all others as `is_pr=False`, `prev_best=None`

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `crud/session.py` | Replace offset with keyset cursor in `list_by_user` | ~20 |
| `crud/session_metric.py` | Fix `get_current_best_batch` for direction, fix `get_current_best` for direction | ~30 |
| `routes/sessions.py` | Replace offset/sort params with cursor, encode/decode, error handling | ~30 |
| `schemas.py` | `SessionListResponse` stops inheriting `PaginatedResponse`, add `next_cursor`/`has_more` | ~10 |
| `models/session.py` | Add composite index for keyset pagination | ~3 |
| `routes/metrics.py` | Direction-aware trend in `get_trend`, pass `direction` to diagnostics | ~10 |
| `services/diagnostics.py` | Add `direction` param to `check_declining_trend` | ~5 |
| `alembic/` | Migration to recalculate `is_pr`/`prev_best` for "lower" metrics | ~50 |
| Tests | Update session pagination tests, add direction-aware trend/diagnostics/PR tests | ~100 |

## Out of Scope

- `overall_score` sort in sessions (no unique key for keyset)
- Auth/security hardening (Phase 1b)
- DB connection pool tuning (`pool_size`, `max_overflow`)
- Metric registry expansion
- Rate limiting for `GET /sessions`
- Frontend infinite scroll implementation (frontend currently fetches all sessions)