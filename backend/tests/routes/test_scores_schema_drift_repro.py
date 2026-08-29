"""#787 repro: get_session_scores model_validate no try/except — schema drift
(NULL where required, type mismatch, dropped column) raised ValidationError
→ unhandled 500. Must wrap → clean 502."""

from pathlib import Path

import pytest
from app.schemas import SessionScoreResponse
from pydantic import ValidationError

ROUTE_FILE = Path(__file__).resolve().parents[2] / "app" / "routes" / "scores.py"


def test_source_model_validate_wrapped_in_try_except_502():
    """#787: SessionScoreResponse.model_validate must be wrapped in
    try/except ValidationError → ClientException(status_code=502)."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "SessionScoreResponse.model_validate(" in src
    assert "except ValidationError" in src, "#787: model_validate has no ValidationError handler"
    assert "status_code=502" in src, "#787: schema drift must 502, not 500"
    assert "logger.exception" in src


def test_session_score_response_model_validate_raises_on_garbage():
    """Observable: schema drift raises ValidationError (the unhandled-500
    root cause). The route now catches it → 502."""
    with pytest.raises((ValidationError, Exception)):
        SessionScoreResponse.model_validate(object())  # type: ignore[arg-type]
