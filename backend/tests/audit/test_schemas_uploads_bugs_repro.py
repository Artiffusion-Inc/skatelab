"""#678: SessionResponse.recommendations accepts empty strings.
#681: uploads total_size unbounded — DoS.
"""

from __future__ import annotations

import inspect

import pytest
from app.schemas import SessionResponse

# ---------------------------------------------------------------------------
# #678: recommendations empty string filter
# ---------------------------------------------------------------------------


def test_recommendations_filter_in_source():
    """#678: SessionResponse has _filter_empty_strings validator."""
    source = inspect.getsource(SessionResponse)
    assert "_filter_empty_strings" in source, "#678: filter validator missing"


def test_recommendations_filter_removes_empty_strings():
    """#678: _filter_empty_strings removes empty strings."""
    result = SessionResponse._filter_empty_strings(
        ["", "Тренируйте взлёт", "", "Улучшите вращение"]
    )
    assert result == ["Тренируйте взлёт", "Улучшите вращение"]


def test_recommendations_filter_all_empty():
    """#678: all-empty list becomes empty list."""
    result = SessionResponse._filter_empty_strings(["", "", ""])
    assert result == []


def test_recommendations_filter_none_stays_none():
    """#678: None passes through unchanged."""
    result = SessionResponse._filter_empty_strings(None)
    assert result is None


def test_recommendations_filter_preserves_valid():
    """#678: valid strings pass through."""
    result = SessionResponse._filter_empty_strings(["one", "two"])
    assert result == ["one", "two"]


# ---------------------------------------------------------------------------
# #681: total_size upper bound
# ---------------------------------------------------------------------------


def test_total_size_upper_bound_in_source():
    """#681: init_upload total_size has le constraint."""
    from pathlib import Path

    uploads_path = Path(__file__).resolve().parents[2] / "app" / "routes" / "uploads.py"
    source = uploads_path.read_text()
    assert "le=" in source and "total_size" in source, "#681: total_size upper bound missing"
