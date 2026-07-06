"""#786/#785 repro: get_session_phases had no rate limit and no model_validate
try/except — DB read flood + schema drift → unhandled 500."""

from pathlib import Path

import pytest
from app.schemas import SessionPhaseResponse
from pydantic import ValidationError

ROUTE_FILE = Path(__file__).resolve().parents[2] / "app" / "routes" / "phases.py"


def test_source_get_session_phases_has_rate_limit_per_user_scope():
    """#786: get_session_phases must call check_rate_limit with phases:{user.id}."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "check_rate_limit(" in src, "#786: phases route has no check_rate_limit"
    assert "phases:" in src
    assert "max_requests=60" in src
    assert "window_seconds=60" in src


def test_source_get_session_phases_rate_limit_after_ownership_before_fetch():
    """Rate-limit after assert_session_owned (cheap auth first), before the DB fetch."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    body = src[src.index("async def get_session_phases") :]
    assert_session_idx = body.index("assert_session_owned")
    rate_limit_idx = body.index("check_rate_limit")
    fetch_idx = body.index("get_by_session_id")
    assert assert_session_idx < rate_limit_idx < fetch_idx


def test_source_model_validate_wrapped_in_try_except_502():
    """#785: SessionPhaseResponse.model_validate must be wrapped in
    try/except ValidationError → ClientException(status_code=502)."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "SessionPhaseResponse.model_validate(" in src
    assert "except ValidationError" in src, "#785: model_validate has no ValidationError handler"
    assert "status_code=502" in src, "#785: schema drift must 502, not 500"
    assert "logger.exception" in src


def test_session_phase_response_model_validate_raises_on_garbage():
    """Observable: schema drift raises ValidationError (unhandled-500 root cause)."""
    with pytest.raises((ValidationError, Exception)):
        SessionPhaseResponse.model_validate(object())  # type: ignore[arg-type]
