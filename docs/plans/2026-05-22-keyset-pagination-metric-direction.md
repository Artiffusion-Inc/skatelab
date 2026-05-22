# Phase 2a: Keyset Pagination & Metric Direction Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace offset pagination with stable keyset cursor and fix metric direction bugs (trend, diagnostics, PR batch fetch).

**Architecture:** Keyset cursor on `(created_at, id)` replaces offset/sort params. Direction-aware inline logic fixes trend labels, diagnostics decline detection, and PR batch fetch. Alembic migration recalculates historical `is_pr`/`prev_best` for "lower" metrics.

**Tech Stack:** SQLAlchemy 2.0 async, Litestar 2.x, Alembic, pytest-asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/crud/session.py` | Modify | Replace offset/sort with cursor in `list_by_user` |
| `backend/app/crud/session_metric.py` | Modify | Direction-aware `get_current_best` and `get_current_best_batch` |
| `backend/app/routes/sessions.py` | Modify | Replace offset/sort params with cursor, encode/decode helpers |
| `backend/app/schemas.py` | Modify | `SessionListResponse` stops inheriting `PaginatedResponse`, add `next_cursor`/`has_more` |
| `backend/app/models/session.py` | Modify | Add composite index for keyset pagination |
| `backend/app/routes/metrics.py` | Modify | Direction-aware trend in `get_trend`, pass `direction` to `check_declining_trend` |
| `backend/app/services/diagnostics.py` | Modify | Add `direction` param to `check_declining_trend` |
| `backend/alembic/versions/2026_05_22_1200-*.py` | Create | Migration: add composite index + recalculate `is_pr`/`prev_best` |
| `backend/tests/test_diagnostics.py` | Modify | Add direction-aware declining trend tests |
| `backend/tests/routes/test_metrics.py` | Modify | Add direction-aware trend tests, update existing tests |
| `backend/tests/routes/test_sessions.py` | Modify | Update pagination tests for cursor-based response |
| `backend/tests/crud/test_session_metric.py` | Modify | Add direction-aware `get_current_best` and batch tests |
| `backend/tests/crud/test_session_metric_batch.py` | Modify | Update batch tests for direction-aware logic |

---

## Wave 1: Direction-Aware Logic (no API changes)

These tasks are independent — can run in parallel via subagents but share no files.

### Task 1: Direction-aware trend in `routes/metrics.py:get_trend`

**Files:**

- Modify: `backend/app/routes/metrics.py:122-131`
- Test: `backend/tests/routes/test_metrics.py`

- [ ] **Step 1: Write failing test for direction-aware trend ("lower" metric)**

Add to `backend/tests/routes/test_metrics.py`:

```python
@pytest.mark.asyncio
async def test_trend_lower_metric_improving(
    client, auth_headers_a, user_a, db_session: AsyncSession
):
    """GET /metrics/trend for a 'lower' metric: decreasing values = improving."""
    now = datetime.now(UTC)
    # knee_angle is direction="lower" for three_turn
    values = [140.0, 125.0, 110.0]  # decreasing = improving for "lower"
    for i, val in enumerate(values):
        session = Session(
            id=f"s-lower-improve-{i}",
            user_id=user_a.id,
            element_type="three_turn",
            status="done",
            created_at=now - timedelta(days=10 - i * 3),
        )
        db_session.add(session)
        await db_session.flush()
        await _insert_metric(db_session, session.id, "knee_angle", val)

    response = await client.get(
        "/api/v1/metrics/trend",
        params={"element_type": "three_turn", "metric_name": "knee_angle"},
        headers=auth_headers_a,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["trend"] == "improving"


@pytest.mark.asyncio
async def test_trend_lower_metric_declining(
    client, auth_headers_a, user_a, db_session: AsyncSession
):
    """GET /metrics/trend for a 'lower' metric: increasing values = declining."""
    now = datetime.now(UTC)
    values = [100.0, 120.0, 140.0]  # increasing = declining for "lower"
    for i, val in enumerate(values):
        session = Session(
            id=f"s-lower-decline-{i}",
            user_id=user_a.id,
            element_type="three_turn",
            status="done",
            created_at=now - timedelta(days=10 - i * 3),
        )
        db_session.add(session)
        await db_session.flush()
        await _insert_metric(db_session, session.id, "knee_angle", val)

    response = await client.get(
        "/api/v1/metrics/trend",
        params={"element_type": "three_turn", "metric_name": "knee_angle"},
        headers=auth_headers_a,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["trend"] == "declining"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/routes/test_metrics.py::test_trend_lower_metric_improving tests/routes/test_metrics.py::test_trend_lower_metric_declining -v`
Expected: FAIL — trend returns "declining" for decreasing "lower" values (direction-blind logic)

- [ ] **Step 3: Implement direction-aware trend logic**

In `backend/app/routes/metrics.py`, replace lines 122-131:

```python
        # Compute trend
        values = [dp.value for dp in data_points]
        trend = "stable"
        if len(values) >= 3:
            from app.services.diagnostics import linear_regression

            slope, r_sq = linear_regression(values)
            improving = (slope > 0) if mdef.direction == "higher" else (slope < 0)
            declining = (slope < 0) if mdef.direction == "higher" else (slope > 0)
            if improving and r_sq > 0.3:
                trend = "improving"
            elif declining and r_sq > 0.3:
                trend = "declining"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/routes/test_metrics.py -v -k "trend_lower"`
Expected: PASS

- [ ] **Step 5: Verify existing trend tests still pass**

Run: `cd backend && uv run pytest tests/routes/test_metrics.py -v -k "trend"`
Expected: ALL PASS (existing "higher" metric tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/metrics.py backend/tests/routes/test_metrics.py
git commit -m "fix(metrics): direction-aware trend for lower-is-better metrics"
```

---

### Task 2: Direction-aware diagnostics in `services/diagnostics.py`

**Files:**

- Modify: `backend/app/services/diagnostics.py:66-85`
- Modify: `backend/app/routes/metrics.py:273-275` (caller)
- Test: `backend/tests/test_diagnostics.py`

- [ ] **Step 1: Write failing test for direction-aware declining trend**

Add to `backend/tests/test_diagnostics.py`:

```python
def test_declining_trend_lower_metric_improving():
    """No warning when 'lower' metric values decrease (that's improvement)."""
    values = [150.0, 140.0, 130.0, 120.0, 110.0]
    finding = check_declining_trend(
        element="three_turn",
        metric="knee_angle",
        values=values,
        metric_label="Угол колена",
        direction="lower",
    )
    assert finding is None


def test_declining_trend_lower_metric_declining():
    """Warning when 'lower' metric values increase (that's decline)."""
    values = [110.0, 120.0, 130.0, 140.0, 150.0]
    finding = check_declining_trend(
        element="three_turn",
        metric="knee_angle",
        values=values,
        metric_label="Угол колена",
        direction="lower",
    )
    assert finding is not None
    assert finding.severity == "warning"


def test_declining_trend_higher_default():
    """Existing behavior: slope < 0 = decline for direction='higher'."""
    values = [0.50, 0.48, 0.45, 0.43, 0.40]
    finding = check_declining_trend(
        element="lutz",
        metric="landing_knee_stability",
        values=values,
        metric_label="Стабильность приземления",
        direction="higher",
    )
    assert finding is not None
    assert finding.severity == "warning"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_diagnostics.py::test_declining_trend_lower_metric_improving tests/test_diagnostics.py::test_declining_trend_lower_metric_declining -v`
Expected: FAIL — `check_declining_trend` doesn't accept `direction` param yet

- [ ] **Step 3: Add `direction` param to `check_declining_trend`**

In `backend/app/services/diagnostics.py`, replace `check_declining_trend` (lines 66-85):

```python
def check_declining_trend(
    *,
    element: str,
    metric: str,
    values: list[float],
    metric_label: str,
    direction: str = "higher",
) -> Finding | None:
    """Warning when linear regression shows decline with R² > 0.5."""
    if len(values) < 5:
        return None
    slope, r_squared = linear_regression(values)
    is_decline = (slope < 0) if direction == "higher" else (slope > 0)
    if is_decline and r_squared > 0.5:
        return Finding(
            severity="warning",
            element=element,
            metric=metric,
            message=f"{metric_label}: ухудшается",
            detail=f"Тренд: declining (R²={r_squared:.2f})",
        )
    return None
```

- [ ] **Step 4: Update caller in `routes/metrics.py`**

In `backend/app/routes/metrics.py`, line 273, add `direction=mdef.direction`:

```python
            f = check_declining_trend(
                element=element,
                metric=metric_name,
                values=values,
                metric_label=mdef.label_ru,
                direction=mdef.direction,
            )
```

- [ ] **Step 5: Update existing test to pass `direction`**

In `backend/tests/test_diagnostics.py`, update `test_declining_trend` (line 40-49):

```python
def test_declining_trend():
    """Warning when slope is negative with good R²."""
    values = [0.50, 0.48, 0.45, 0.43, 0.40]
    finding = check_declining_trend(
        element="lutz",
        metric="landing_knee_stability",
        values=values,
        metric_label="Стабильность приземления",
        direction="higher",
    )
    assert finding is not None
    assert finding.severity == "warning"
```

- [ ] **Step 6: Run all diagnostics tests**

Run: `cd backend && uv run pytest tests/test_diagnostics.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/diagnostics.py backend/app/routes/metrics.py backend/tests/test_diagnostics.py
git commit -m "fix(diagnostics): direction-aware declining trend for lower-is-better metrics"
```

---

### Task 3: Direction-aware PR batch fetch in `crud/session_metric.py`

**Files:**

- Modify: `backend/app/crud/session_metric.py:15-76`
- Test: `backend/tests/crud/test_session_metric.py`
- Test: `backend/tests/crud/test_session_metric_batch.py`

- [ ] **Step 1: Write failing test for direction-aware `get_current_best`**

Add to `backend/tests/crud/test_session_metric.py`:

```python
async def test_get_current_best_lower_direction(db_session):
    """get_current_best with direction='lower' returns min, not max."""
    _make_user(db_session, "user-lower")
    await db_session.flush()

    s1 = Session(user_id="user-lower", element_type="three_turn", status="done")
    s2 = Session(user_id="user-lower", element_type="three_turn", status="done")
    db_session.add(s1)
    db_session.add(s2)
    await db_session.flush()

    db_session.add(SessionMetric(session_id=s1.id, metric_name="knee_angle", metric_value=140.0))
    db_session.add(SessionMetric(session_id=s2.id, metric_name="knee_angle", metric_value=105.0))
    await db_session.flush()

    best = await get_current_best(db_session, "user-lower", "three_turn", "knee_angle", direction="lower")
    assert best == 105.0


async def test_get_current_best_higher_direction(db_session):
    """get_current_best with direction='higher' returns max (existing behavior)."""
    _make_user(db_session, "user-higher")
    await db_session.flush()

    s1 = Session(user_id="user-higher", element_type="waltz_jump", status="done")
    s2 = Session(user_id="user-higher", element_type="waltz_jump", status="done")
    db_session.add(s1)
    db_session.add(s2)
    await db_session.flush()

    db_session.add(SessionMetric(session_id=s1.id, metric_name="airtime", metric_value=0.5))
    db_session.add(SessionMetric(session_id=s2.id, metric_name="airtime", metric_value=0.8))
    await db_session.flush()

    best = await get_current_best(db_session, "user-higher", "waltz_jump", "airtime", direction="higher")
    assert best == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/crud/test_session_metric.py::test_get_current_best_lower_direction -v`
Expected: FAIL — `get_current_best` doesn't accept `direction` param

- [ ] **Step 3: Add `direction` param to `get_current_best`**

In `backend/app/crud/session_metric.py`, replace `get_current_best` (lines 15-41):

```python
async def get_current_best(
    db: AsyncSession,
    user_id: str,
    element_type: str,
    metric_name: str,
    direction: str = "higher",
) -> float | None:
    """Get the current best value for a user+element+metric combination.

    Only considers non-deleted sessions. For direction="higher", returns max.
    For direction="lower", returns min.
    """
    order_col = SessionMetric.metric_value.desc() if direction == "higher" else SessionMetric.metric_value.asc()
    query = (
        select(SessionMetric.metric_value)
        .join(Session)
        .where(
            Session.user_id == user_id,
            Session.element_type == element_type,
            SessionMetric.metric_name == metric_name,
            Session.status == "done",
        )
        .order_by(order_col)
        .limit(1)
    )
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    return row
```

- [ ] **Step 4: Replace `get_current_best_batch` with direction-aware version**

In `backend/app/crud/session_metric.py`, replace `get_current_best_batch` (lines 44-76):

```python
async def get_current_best_batch(
    db: AsyncSession,
    user_id: str,
    element_type: str,
    metric_names: list[str],
) -> dict[str, float]:
    """Get current best values for multiple metrics in a single query.

    Uses METRIC_REGISTRY to determine direction per metric.
    Higher-is-better → max, lower-is-better → min.
    Missing metrics (no data) are omitted from the dict.
    """
    if not metric_names:
        return {}

    from sqlalchemy import func

    from app.metrics_registry import METRIC_REGISTRY

    higher_metrics = [n for n in metric_names if METRIC_REGISTRY.get(n, type("", (), {"direction": "higher"})()).direction == "higher"]
    lower_metrics = [n for n in metric_names if METRIC_REGISTRY.get(n, type("", (), {"direction": "higher"})()).direction == "lower"]

    bests: dict[str, float] = {}

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
                SessionMetric.metric_name.in_(higher_metrics),
                Session.status == "done",
            )
            .group_by(SessionMetric.metric_name)
        )
        bests.update({row.metric_name: row.best_value for row in result.all()})

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
                SessionMetric.metric_name.in_(lower_metrics),
                Session.status == "done",
            )
            .group_by(SessionMetric.metric_name)
        )
        bests.update({row.metric_name: row.best_value for row in result.all()})

    return bests
```

- [ ] **Step 5: Write test for direction-aware batch fetch**

Add to `backend/tests/crud/test_session_metric.py`:

```python
async def test_get_current_best_batch_lower_metrics(db_session):
    """get_current_best_batch uses min for 'lower' direction metrics."""
    _make_user(db_session, "user-batch-lower")
    await db_session.flush()

    s1 = Session(user_id="user-batch-lower", element_type="three_turn", status="done")
    s2 = Session(user_id="user-batch-lower", element_type="three_turn", status="done")
    db_session.add(s1)
    db_session.add(s2)
    await db_session.flush()

    # knee_angle is direction="lower" — best = min
    db_session.add(SessionMetric(session_id=s1.id, metric_name="knee_angle", metric_value=140.0))
    db_session.add(SessionMetric(session_id=s2.id, metric_name="knee_angle", metric_value=105.0))
    # trunk_lean is direction="lower" — best = min
    db_session.add(SessionMetric(session_id=s1.id, metric_name="trunk_lean", metric_value=15.0))
    db_session.add(SessionMetric(session_id=s2.id, metric_name="trunk_lean", metric_value=5.0))
    await db_session.flush()

    result = await get_current_best_batch(
        db_session, "user-batch-lower", "three_turn", ["knee_angle", "trunk_lean"]
    )
    assert result["knee_angle"] == 105.0
    assert result["trunk_lean"] == 5.0
```

- [ ] **Step 6: Update existing `get_current_best` test to pass `direction`**

In `backend/tests/crud/test_session_metric.py`, update `test_get_current_best_returns_max`:

```python
async def test_get_current_best_returns_max(db_session):
    _make_user(db_session)
    await db_session.flush()

    s1 = Session(user_id="user-1", element_type="waltz_jump", status="done")
    s2 = Session(user_id="user-1", element_type="waltz_jump", status="done")
    db_session.add(s1)
    db_session.add(s2)
    await db_session.flush()

    db_session.add(SessionMetric(session_id=s1.id, metric_name="airtime", metric_value=0.5))
    db_session.add(SessionMetric(session_id=s2.id, metric_name="airtime", metric_value=0.8))
    await db_session.flush()

    best = await get_current_best(db_session, "user-1", "waltz_jump", "airtime", direction="higher")
    assert best == 0.8
```

Update other `get_current_best` calls in the same file to add `direction="higher"`:

- `test_get_current_best_no_data`: add `direction="higher"`
- `test_get_current_best_ignores_deleted_sessions`: add `direction="higher"`
- `test_get_current_best_ignores_wrong_element_type`: add `direction="higher"`

- [ ] **Step 7: Update mock-based batch test**

In `backend/tests/crud/test_session_metric_batch.py`, update `test_get_current_best_batch_returns_dict` to use `direction="higher"` metrics (airtime, max_height are both "higher" direction):

```python
async def test_get_current_best_batch_returns_dict():
    from app.crud.session_metric import get_current_best_batch

    mock_row1 = MagicMock()
    mock_row1.metric_name = "airtime"
    mock_row1.best_value = 0.65
    mock_row2 = MagicMock()
    mock_row2.metric_name = "max_height"
    mock_row2.best_value = 0.42

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row1, mock_row2]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    result = await get_current_best_batch(
        db,
        user_id="user-1",
        element_type="waltz_jump",
        metric_names=["airtime", "max_height"],
    )
    assert result == {"airtime": 0.65, "max_height": 0.42}
```

No change needed here since both metrics are "higher" direction. But the mock won't validate the SQL — that's what the real-DB tests are for.

- [ ] **Step 8: Run all session_metric tests**

Run: `cd backend && uv run pytest tests/crud/test_session_metric.py tests/crud/test_session_metric_batch.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/crud/session_metric.py backend/tests/crud/test_session_metric.py backend/tests/crud/test_session_metric_batch.py
git commit -m "fix(crud): direction-aware PR batch fetch — min for lower-is-better metrics"
```

---

## Wave 2: Keyset Pagination (depends on Wave 1 for clean commit history)

### Task 4: Keyset pagination — `schemas.py`

**Files:**

- Modify: `backend/app/schemas.py:434-435`

- [ ] **Step 1: Write failing test for new `SessionListResponse` shape**

Add to `backend/tests/routes/test_sessions.py` (will fail until schema changes):

```python
@pytest.mark.asyncio
async def test_list_sessions_cursor_shape(client, auth_headers, authed_user, db_session: AsyncSession):
    """GET /sessions returns next_cursor and has_more fields."""
    from app.crud.session import create as crud_create

    # Create 3 sessions
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=authed_user.id, element_type="waltz_jump")
        await crud_create(db_session, user_id=authed_user.id, element_type="toe_loop")
        await crud_create(db_session, user_id=authed_user.id, element_type="flip")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(
            "/api/v1/sessions",
            params={"limit": 2},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert "next_cursor" in data
    assert "has_more" in data
    assert data["has_more"] is True
    assert len(data["sessions"]) == 2
    assert data["total"] == 3
```

- [ ] **Step 2: Replace `SessionListResponse` schema**

In `backend/app/schemas.py`, replace lines 434-435:

```python
class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int
    next_cursor: str | None = None
    has_more: bool = False
```

Keep `PaginatedResponse` class as-is (still used by `ConnectionListResponse` and `ProgramListResponse`).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "refactor(schemas): SessionListResponse with cursor fields, stop inheriting PaginatedResponse"
```

---

### Task 5: Keyset pagination — `crud/session.py`

**Files:**

- Modify: `backend/app/crud/session.py:34-52`

- [ ] **Step 1: Replace `list_by_user` with keyset cursor**

In `backend/app/crud/session.py`, replace `list_by_user` (lines 34-52):

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
    return list(result.scalars().all())
```

Add import at top if missing:

```python
from datetime import datetime  # noqa: TC003
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/crud/session.py
git commit -m "refactor(crud): keyset cursor pagination in list_by_user"
```

---

### Task 6: Keyset pagination — `routes/sessions.py`

**Files:**

- Modify: `backend/app/routes/sessions.py:98-144`

- [ ] **Step 1: Replace `list_sessions` handler with cursor logic**

In `backend/app/routes/sessions.py`, replace the `list_sessions` method (lines 98-144) and add cursor encode/decode helpers:

```python
def _encode_cursor(created_at: datetime, session_id: str) -> str:
    return f"{created_at.isoformat()}|{session_id}"


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    dt_str, sid = cursor.split("|", 1)
    return datetime.fromisoformat(dt_str), sid


class SessionsController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["sessions"]

    # ... create_session stays the same ...

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
        # Coaches can view their students' sessions
        target_user_id = user_id if user_id else user.id
        if (
            user_id
            and user_id != user.id
            and not await is_connected_as(
                db,
                from_user_id=user.id,
                to_user_id=user_id,
                connection_type=ConnectionType.COACHING,
            )
        ):
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not a coach for this user",
            )

        parsed_cursor = None
        if cursor:
            try:
                parsed_cursor = _decode_cursor(cursor)
            except (ValueError, KeyError):
                raise ClientException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="Invalid cursor",
                )

        sessions = await list_by_user(
            db,
            user_id=target_user_id,
            element_type=element_type,
            limit=limit,
            cursor=parsed_cursor,
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

Add `datetime` import at top:

```python
from datetime import datetime
```

Remove `sort` from `list_by_user` import call — it no longer exists.

- [ ] **Step 2: Update existing session list tests**

In `backend/tests/routes/test_sessions.py`, update `test_list_sessions`:

```python
@pytest.mark.asyncio
async def test_list_sessions(client, auth_headers, authed_user, db_session: AsyncSession):
    """GET /sessions returns list with total count and cursor fields."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=authed_user.id, element_type="waltz_jump")
        await crud_create(db_session, user_id=authed_user.id, element_type="toe_loop")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get("/api/v1/sessions", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2
    assert data["has_more"] is False
    assert data["next_cursor"] is None
```

Update `test_list_sessions_filter_element_type` to also check new fields:

```python
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["sessions"][0]["element_type"] == "waltz_jump"
    assert data["has_more"] is False
```

Update `test_list_sessions_coach_allowed`:

```python
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["sessions"][0]["element_type"] == "waltz_jump"
    assert data["has_more"] is False
```

- [ ] **Step 3: Add cursor pagination tests**

Add to `backend/tests/routes/test_sessions.py`:

```python
@pytest.mark.asyncio
async def test_list_sessions_cursor_pagination(client, auth_headers, authed_user, db_session: AsyncSession):
    """GET /sessions with limit returns has_more=True and next_cursor."""
    from app.crud.session import create as crud_create

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        await crud_create(db_session, user_id=authed_user.id, element_type="waltz_jump")
        await crud_create(db_session, user_id=authed_user.id, element_type="toe_loop")
        await crud_create(db_session, user_id=authed_user.id, element_type="flip")

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        # First page
        response = await client.get(
            "/api/v1/sessions",
            params={"limit": 2},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["sessions"]) == 2
    assert data["has_more"] is True
    assert data["next_cursor"] is not None
    first_page_ids = {s["id"] for s in data["sessions"]}

    # Second page using cursor
    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.get(
            "/api/v1/sessions",
            params={"limit": 2, "cursor": data["next_cursor"]},
            headers=auth_headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["sessions"]) == 1
    assert data["has_more"] is False
    assert data["next_cursor"] is None
    second_page_ids = {s["id"] for s in data["sessions"]}

    # No overlap between pages
    assert first_page_ids.isdisjoint(second_page_ids)


@pytest.mark.asyncio
async def test_list_sessions_invalid_cursor(client, auth_headers):
    """GET /sessions with malformed cursor returns 400."""
    response = await client.get(
        "/api/v1/sessions",
        params={"cursor": "not-a-valid-cursor"},
        headers=auth_headers,
    )
    assert response.status_code == 400
```

- [ ] **Step 4: Run all session route tests**

Run: `cd backend && uv run pytest tests/routes/test_sessions.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/sessions.py backend/tests/routes/test_sessions.py
git commit -m "feat(sessions): keyset cursor pagination replaces offset/sort"
```

---

### Task 7: Database composite index for keyset pagination

**Files:**

- Modify: `backend/app/models/session.py:75-77`

- [ ] **Step 1: Add composite index to Session model**

In `backend/app/models/session.py`, replace `__table_args__` (lines 75-77):

```python
    __table_args__ = (
        Index("ix_sessions_user_element_created", "user_id", "element_type", "created_at"),
        Index("ix_sessions_user_element_created_id_desc", "user_id", "element_type", "created_at", "id"),
    )
```

- [ ] **Step 2: Create Alembic migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "add_keyset_pagination_index_and_recalculate_prs"`

This creates a migration file. It should detect the new index.

- [ ] **Step 3: Add `is_pr`/`prev_best` recalculation to the migration**

Open the generated migration file and add the recalculation logic. The migration should:

1. Add the composite index (autogenerated)
2. Recalculate `is_pr`/`prev_best` for all metrics based on direction

```python
"""add keyset pagination index and recalculate prs

Revision ID: <auto>
Revises: e1f2a3b4c5d6
Create Date: 2026-05-22 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "<auto>"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

# Metric direction mapping (must match METRIC_REGISTRY)
LOWER_METRICS = {"landing_knee_angle", "knee_angle", "trunk_lean"}


def upgrade() -> None:
    # Add composite index for keyset pagination
    op.create_index(
        "ix_sessions_user_element_created_id_desc",
        "sessions",
        ["user_id", "element_type", "created_at", "id"],
    )

    # Recalculate is_pr and prev_best for all metrics
    # Step 1: Reset all is_pr and prev_best
    op.execute("""
        UPDATE session_metrics SET is_pr = FALSE, prev_best = NULL
    """)

    # Step 2: For each (user_id, element_type, metric_name), find the best value
    # and mark it as PR, set prev_best to the second-best

    # "Higher is better" metrics: best = max value
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                sm.metric_value,
                s.user_id,
                s.element_type,
                sm.metric_name,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value DESC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name NOT IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET is_pr = TRUE
        FROM ranked r
        WHERE sm.id = r.id AND r.rn = 1
    """)

    # "Lower is better" metrics: best = min value
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                sm.metric_value,
                s.user_id,
                s.element_type,
                sm.metric_name,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value ASC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET is_pr = TRUE
        FROM ranked r
        WHERE sm.id = r.id AND r.rn = 1
    """)

    # Set prev_best for PR rows (second-best value)
    # "Higher" metrics: second max
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                sm.metric_value,
                s.user_id,
                s.element_type,
                sm.metric_name,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value DESC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name NOT IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET prev_best = r2.metric_value
        FROM ranked r1
        JOIN ranked r2 ON r1.user_id = r2.user_id
            AND r1.element_type = r2.element_type
            AND r1.metric_name = r2.metric_name
            AND r2.rn = 2
        WHERE sm.id = r1.id AND r1.rn = 1
    """)

    # "Lower" metrics: second min
    op.execute("""
        WITH ranked AS (
            SELECT
                sm.id,
                sm.metric_value,
                s.user_id,
                s.element_type,
                sm.metric_name,
                ROW_NUMBER() OVER (
                    PARTITION BY s.user_id, s.element_type, sm.metric_name
                    ORDER BY sm.metric_value ASC, sm.id DESC
                ) AS rn
            FROM session_metrics sm
            JOIN sessions s ON s.id = sm.session_id
            WHERE s.status = 'done'
                AND sm.metric_name IN ('landing_knee_angle', 'knee_angle', 'trunk_lean')
        )
        UPDATE session_metrics sm
        SET prev_best = r2.metric_value
        FROM ranked r1
        JOIN ranked r2 ON r1.user_id = r2.user_id
            AND r1.element_type = r2.element_type
            AND r1.metric_name = r2.metric_name
            AND r2.rn = 2
        WHERE sm.id = r1.id AND r1.rn = 1
    """)


def downgrade() -> None:
    op.drop_index("ix_sessions_user_element_created_id_desc", table_name="sessions")
    # Note: is_pr/prev_best recalculation is not reversible without a backup
```

- [ ] **Step 4: Verify migration generates correctly**

Run: `cd backend && uv run alembic upgrade head`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/session.py backend/alembic/
git commit -m "feat(db): keyset pagination index + is_pr/prev_best recalculation migration"
```

---

## Wave 3: Integration Verification

### Task 8: Full test suite + type check

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run type check**

Run: `cd backend && uv run basedpyright app/`
Expected: 0 errors

- [ ] **Step 3: Run linter**

Run: `cd backend && uv run ruff check app/`
Expected: 0 errors

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: fix lint/type issues from Phase 2a"
```

---

## Self-Review

### Spec coverage

| Spec section | Task |
|---|---|
| 1. Keyset pagination — crud/session.py | Task 5 |
| 2. Keyset pagination — routes/sessions.py | Task 6 |
| 3. Schema — SessionListResponse | Task 4 |
| 4. Database index | Task 7 |
| 5. Direction-aware trend | Task 1 |
| 6. Direction-aware diagnostics | Task 2 |
| 7. PR batch fetch fix | Task 3 |
| 8. Data migration | Task 7 |

### Placeholder scan

No TBD/TODO/fill-in-details found.

### Type consistency

- `check_declining_trend` signature: `direction: str = "higher"` — matches caller `mdef.direction` (str)
- `get_current_best` signature: `direction: str = "higher"` — matches all callers
- `get_current_best_batch` no longer takes `direction` param — reads `METRIC_REGISTRY` internally
- `SessionListResponse` fields: `sessions`, `total`, `next_cursor`, `has_more` — matches route handler return
- `_encode_cursor` / `_decode_cursor` — `datetime` + `str` ↔ `str` — matches `Session.created_at` (datetime) and `Session.id` (str)
