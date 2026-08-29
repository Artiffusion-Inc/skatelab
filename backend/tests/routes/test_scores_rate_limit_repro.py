"""#788 repro: get_session_scores had no rate limit — DB read flood on
session_scores table. Source-asserts the guard exists with per-user scope."""

from pathlib import Path

ROUTE_FILE = Path(__file__).resolve().parents[2] / "app" / "routes" / "scores.py"


def test_source_get_session_scores_has_rate_limit_call_with_per_user_scope():
    """#788: get_session_scores must call check_rate_limit with scores:{user.id}."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "check_rate_limit(" in src, "#788: scores route has no check_rate_limit call"
    assert "scores:" in src, "#788: rate-limit scope must be scores:<user.id>"
    assert "max_requests=60" in src
    assert "window_seconds=60" in src


def test_source_get_session_scores_rate_limit_after_ownership_check():
    """Rate-limit must come AFTER assert_session_owned (cheap auth before
    the counted read), but BEFORE the DB fetch that the limit guards.
    Scope to the function body so import lines don't skew the order.
    """
    src = ROUTE_FILE.read_text(encoding="utf-8")
    fn_start = src.index("async def get_session_scores")
    body = src[fn_start:]
    assert_session_idx = body.index("assert_session_owned")
    rate_limit_idx = body.index("check_rate_limit")
    fetch_idx = body.index("get_by_session_id")
    assert assert_session_idx < rate_limit_idx < fetch_idx, (
        "expected assert_session_owned < check_rate_limit < get_by_session_id"
    )
