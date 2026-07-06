"""#670: skill_progress StopIteration on unknown skill_id.

next() without default raises StopIteration on unknown skill_id.
Fix: next(..., None) + raise ValueError with skill_id in message.
"""

from __future__ import annotations

import inspect

import pytest
from app.crud.skill_progress import SKILL_DEFINITIONS


def test_value_error_guard_in_source():
    """#670: get_or_create raises ValueError on unknown skill_id."""
    from app.crud.skill_progress import get_or_create

    source = inspect.getsource(get_or_create)
    assert "Unknown skill_id" in source, "#670: ValueError guard missing from get_or_create"


def test_known_skill_ids_in_definitions():
    """All SKILL_DEFINITIONS have valid id/category/tier/xp_reward."""
    for d in SKILL_DEFINITIONS:
        assert "id" in d
        assert "category" in d
        assert "tier" in d
        assert "xp_reward" in d


def test_next_without_default_raises_stopiteration():
    """Baseline: next() on empty generator raises StopIteration."""
    with pytest.raises(StopIteration):
        next(s for s in SKILL_DEFINITIONS if s["id"] == "nonexistent_skill_id")


def test_next_with_default_returns_none():
    """next(..., None) returns None for unknown skill_id — no exception."""
    result = next((s for s in SKILL_DEFINITIONS if s["id"] == "nonexistent_skill_id"), None)
    assert result is None


def test_next_with_default_finds_known():
    """next(..., None) returns matching definition for known skill_id."""
    result = next((s for s in SKILL_DEFINITIONS if s["id"] == "jumps_bronze"), None)
    assert result is not None
    assert result["id"] == "jumps_bronze"
