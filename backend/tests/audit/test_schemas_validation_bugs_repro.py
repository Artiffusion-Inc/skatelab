"""#673: SessionScoreResponse.overall no 0-10 constraint.
#674: UserResponse.validate_datetime no None guard.
#675: MultiDimensionalScoreSchema accepts empty subscores.
"""

from __future__ import annotations

import inspect

import pytest
from app.schemas import (
    MultiDimensionalScoreSchema,
    SessionScoreResponse,
    SubScoreSchema,
    UserResponse,
)
from pydantic import ValidationError


def _sub(name: str = "a", label_ru: str = "А", value: float = 5.0) -> SubScoreSchema:
    return SubScoreSchema(
        name=name, label_ru=label_ru, value=value, confidence=0.5, contributing_metrics=[]
    )


# ---------------------------------------------------------------------------
# Source guards
# ---------------------------------------------------------------------------


def test_session_score_overall_constraint_in_source():
    """#673: SessionScoreResponse.overall has ge=0, le=10."""
    source = inspect.getsource(SessionScoreResponse)
    assert "ge=0" in source or "le=10" in source, "#673: overall constraint missing"


def test_user_response_none_guard_in_source():
    """#674: UserResponse.validate_datetime has None guard."""
    source = inspect.getsource(UserResponse.validate_datetime)
    assert "if v is None" in source, "#674: None guard missing from validate_datetime"


def test_multi_dimensional_min_length_in_source():
    """#675: MultiDimensionalScoreSchema.subscores has min_length=1."""
    source = inspect.getsource(MultiDimensionalScoreSchema)
    assert "min_length=1" in source, "#675: min_length=1 missing from subscores"


# ---------------------------------------------------------------------------
# #673: SessionScoreResponse.overall constraint
# ---------------------------------------------------------------------------


def test_session_score_overall_negative_rejected():
    """#673: overall=-3.5 rejected by validation."""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        SessionScoreResponse(
            id="x",
            session_id="s",
            subscores=[_sub()],
            overall=-3.5,
            data_quality="good",
            skeleton_reliability="reliable",
            created_at="2026-07-05T00:00:00",
            updated_at="2026-07-05T00:00:00",
        )


def test_session_score_overall_above_10_rejected():
    """#673: overall=15.0 rejected by validation."""
    with pytest.raises(ValidationError, match="less than or equal to 10"):
        SessionScoreResponse(
            id="x",
            session_id="s",
            subscores=[_sub()],
            overall=15.0,
            data_quality="good",
            skeleton_reliability="reliable",
            created_at="2026-07-05T00:00:00",
            updated_at="2026-07-05T00:00:00",
        )


def test_session_score_overall_valid_accepted():
    """#673: overall=7.5 accepted."""
    s = SessionScoreResponse(
        id="x",
        session_id="s",
        subscores=[_sub()],
        overall=7.5,
        data_quality="good",
        skeleton_reliability="reliable",
        created_at="2026-07-05T00:00:00",
        updated_at="2026-07-05T00:00:00",
    )
    assert s.overall == 7.5


# ---------------------------------------------------------------------------
# #674: UserResponse.validate_datetime None guard
# ---------------------------------------------------------------------------


def test_user_response_validate_datetime_none_returns_none():
    """#674: validate_datetime(None) returns None, not "None"."""
    result = UserResponse.validate_datetime(None)
    assert result is None


# ---------------------------------------------------------------------------
# #675: MultiDimensionalScoreSchema empty subscores
# ---------------------------------------------------------------------------


def test_multi_dimensional_empty_subscores_rejected():
    """#675: empty subscores list rejected."""
    with pytest.raises(ValidationError, match="at least 1"):
        MultiDimensionalScoreSchema(subscores=[], overall=5.0)


def test_multi_dimensional_valid_subscores_accepted():
    """#675: non-empty subscores accepted."""
    s = MultiDimensionalScoreSchema(subscores=[_sub()], overall=5.0)
    assert len(s.subscores) == 1
