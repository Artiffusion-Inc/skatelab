"""RED repro — /prs route returns stale first-encountered PR, not most recent.

backend/app/routes/metrics.py:202-232 — /prs route:
    query = select(SessionMetric, Session.element_type) ... where is_pr ...
    result = await db.execute(query)
    rows = result.all()
    prs = []
    seen = set()
    for row in rows:
        key = (row.element_type, row.SessionMetric.metric_name)
        if key not in seen: ... prs.append(row)

No `.order_by(Session.created_at.desc())` — rows arrive in DB-insertion order.
Iteration dedupes by (element_type, metric_name) and keeps the FIRST — the
oldest PR. Subsequent PRs (newer session, higher value) are silently dropped
behind the seen-set. (#632)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = BACKEND_ROOT / "app" / "routes" / "metrics.py"


def _load_metrics_module():
    spec = importlib.util.spec_from_file_location("_metrics_route_under_test", METRICS_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_orders_prs_query_by_created_at_desc():
    """The /prs query must have `.order_by(Session.created_at.desc())`."""
    src = METRICS_PATH.read_text(encoding="utf-8")
    # Anchor on @get("/prs") and walk to the next @get or end of file.
    prs_start = src.find('@get("/prs")')
    assert prs_start != -1, "expected @get('/prs') decorator in metrics.py"
    next_method = src.find("\n    @get", prs_start + 1)
    block = src[prs_start:next_method] if next_method != -1 else src[prs_start:]

    # The block must contain the is_pr filter AND an order_by on created_at.
    assert "SessionMetric.is_pr" in block, "expected is_pr filter in /prs block"
    assert ".order_by" in block and "Session.created_at" in block, (
        f"/prs block must .order_by(Session.created_at) so the most recent PR "
        f"appears first and the seen-set dedup keeps it. Without order_by the "
        f"first-encountered (oldest) row is returned (#632). Block was:\n{block}"
    )


def test_prs_route_query_has_order_by_created_at_desc():
    """The actual SQLAlchemy query built by /prs must have ORDER BY created_at DESC.

    Captures the query the route builds, compiles it to SQL, and asserts
    the ORDER BY clause contains `created_at` with DESC direction. The
    source-test in test_source_orders_prs_query_by_created_at_desc only
    checks the file content; this one verifies the *runtime* query object
    the route constructs. (#632)
    """
    mod = _load_metrics_module()

    captured_query = {}

    class _StubResult:
        def all(self):
            return []

    class _StubDB:
        async def execute(self, query):
            captured_query["query"] = query
            return _StubResult()

    class _StubUser:
        id = "u1"

    async def _is_connected(*_a, **_kw):
        return True

    import asyncio

    async def _run():
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(mod, "is_connected_as", _is_connected)
            get_prs_fn = mod.MetricsController.get_prs.fn
            await get_prs_fn(
                self=None,
                user=_StubUser(),
                db=_StubDB(),
                user_id=None,
                element_type=None,
            )

    asyncio.run(_run())

    assert "query" in captured_query, "route did not call db.execute"
    q = captured_query["query"]
    compiled = str(q.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY" in compiled.upper(), (
        f"/prs query must have ORDER BY clause so the most recent PR is "
        f"returned. Compiled SQL: {compiled}"
    )
    # Verify it orders by `created_at` AND the DESC direction. SQLAlchemy
    # emits `sessions.created_at DESC` — check both.
    assert "created_at" in compiled, (
        f"/prs ORDER BY must use created_at (the PR's session timestamp). Compiled SQL: {compiled}"
    )
    assert "DESC" in compiled.upper(), (
        f"/prs ORDER BY must be DESC (newest-first) so the most recent PR is "
        f"kept by the seen-set dedup. Compiled SQL: {compiled}"
    )


def test_prs_route_source_includes_order_by_line_executable():
    """Source-level: the order_by must be on an executable line, not in a comment.

    Anchored regex on `\\.order_by\\s*\\(\\s*Session\\.created_at` to ensure
    the order_by is actually called on the query (not a docstring/comment).
    """
    import re

    src = METRICS_PATH.read_text(encoding="utf-8")
    # Match `.order_by(Session.created_at...)` (optional .desc()/.asc()) on a real line.
    pat = re.compile(r"\.order_by\s*\(\s*Session\.created_at", re.MULTILINE)
    matches = list(pat.finditer(src))
    assert matches, (
        "expected executable `.order_by(Session.created_at...)` in metrics.py "
        "so /prs rows arrive newest-first (#632). None found."
    )
