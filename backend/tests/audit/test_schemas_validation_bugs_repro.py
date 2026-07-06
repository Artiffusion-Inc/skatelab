"""#673: SessionScoreResponse.overall no 0-10 constraint.
#674: UserResponse.validate_datetime no None guard.
#675: MultiDimensionalScoreSchema accepts empty subscores.
#676: PhaseExtendedSchema accepts infinity.
#677: TrendResponse.trend no pattern constraint.
#679: Layout.total_tes accepts NaN/negative.
"""

from __future__ import annotations

import inspect
import math

import pytest
from app.schemas import (
    Layout,
    LayoutElement,
    MultiDimensionalScoreSchema,
    PhaseExtendedSchema,
    SessionScoreResponse,
    SubScoreSchema,
    TrendResponse,
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


def test_phase_extended_reject_infinity_in_source():
    """#676: PhaseExtendedSchema has _reject_infinity validator."""
    source = inspect.getsource(PhaseExtendedSchema)
    assert "isfinite" in source, "#676: infinity guard missing from PhaseExtendedSchema"


def test_trend_response_pattern_in_source():
    """#677: TrendResponse.trend has pattern constraint."""
    source = inspect.getsource(TrendResponse)
    assert "improving" in source and "declining" in source, "#677: trend pattern missing"


def test_layout_total_tes_validator_in_source():
    """#679: Layout.total_tes has _reject_nonfinite_tes validator."""
    source = inspect.getsource(Layout)
    assert "isfinite" in source, "#679: nonfinite guard missing from Layout"


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


# ---------------------------------------------------------------------------
# #676: PhaseExtendedSchema rejects infinity
# ---------------------------------------------------------------------------


def test_phase_extended_inf_rejected():
    """#676: end_time=inf rejected."""
    with pytest.raises(ValidationError, match="finite"):
        PhaseExtendedSchema(
            name="approach",
            start_frame=0,
            end_frame=10,
            start_time=0.0,
            end_time=float("inf"),
            confidence=0.5,
            detection_method="auto",
        )


def test_phase_extended_nan_rejected():
    """#676: start_time=NaN rejected by ge=0 constraint."""
    with pytest.raises(ValidationError):
        PhaseExtendedSchema(
            name="approach",
            start_frame=0,
            end_frame=10,
            start_time=float("nan"),
            end_time=1.0,
            confidence=0.5,
            detection_method="auto",
        )


def test_phase_extended_valid_accepted():
    """#676: finite start_time/end_time accepted."""
    p = PhaseExtendedSchema(
        name="approach",
        start_frame=0,
        end_frame=10,
        start_time=0.0,
        end_time=5.0,
        confidence=0.9,
        detection_method="auto",
    )
    assert p.end_time == 5.0


# ---------------------------------------------------------------------------
# #677: TrendResponse.trend pattern constraint
# ---------------------------------------------------------------------------


def test_trend_response_invalid_rejected():
    """#677: trend='blah' rejected."""
    with pytest.raises(ValidationError, match=r"improving\|stable\|declining"):
        TrendResponse(
            metric_name="airtime",
            element_type="jumps",
            data_points=[],
            trend="blah",
            current_pr=None,
            reference_range=None,
        )


def test_trend_response_valid_accepted():
    """#677: trend='improving' accepted."""
    t = TrendResponse(
        metric_name="airtime",
        element_type="jumps",
        data_points=[],
        trend="improving",
        current_pr=None,
        reference_range=None,
    )
    assert t.trend == "improving"


# ---------------------------------------------------------------------------
# #679: Layout.total_tes rejects NaN/negative/inf
# ---------------------------------------------------------------------------


def test_layout_total_tes_nan_rejected():
    """#679: total_tes=NaN rejected."""
    with pytest.raises(ValidationError):
        Layout(elements=[LayoutElement(code="3A")], total_tes=float("nan"), back_half_indices=[])


def test_layout_total_tes_inf_rejected():
    """#679: total_tes=inf rejected."""
    with pytest.raises(ValidationError, match="finite"):
        Layout(elements=[LayoutElement(code="3A")], total_tes=float("inf"), back_half_indices=[])


def test_layout_total_tes_negative_rejected():
    """#679: total_tes=-1 rejected by ge=0."""
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Layout(elements=[LayoutElement(code="3A")], total_tes=-1.0, back_half_indices=[])


def test_layout_total_tes_valid_accepted():
    """#679: total_tes=42.5 accepted."""
    layout = Layout(elements=[LayoutElement(code="3A")], total_tes=42.5, back_half_indices=[])
    assert layout.total_tes == 42.5
