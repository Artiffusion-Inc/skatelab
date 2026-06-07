"""Tests for ISU GOE grader."""

import pytest

from src.analysis.goe_grader import GOEGrader
from src.types import GOEGrade, MetricResult


def _make_metrics(**kwargs: float) -> list[MetricResult]:
    """Create MetricResult list from keyword args."""
    return [
        MetricResult(name=k, value=v, unit="score", is_good=True, reference_range=(0, 1))
        for k, v in kwargs.items()
    ]


class TestGOEGraderModifierDetection:
    def test_clean_element(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=3.0)
        modifier = grader.detect_modifier(metrics, expected_rotations=3.0)
        assert modifier == ""

    def test_under_rotated(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=2.6)
        modifier = grader.detect_modifier(metrics, expected_rotations=3.0)
        assert modifier == "<"

    def test_downgraded(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=2.4)
        modifier = grader.detect_modifier(metrics, expected_rotations=3.0)
        assert modifier == "<<"

    def test_landed_quarter(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=2.85)
        modifier = grader.detect_modifier(metrics, expected_rotations=3.0)
        assert modifier == "q"

    def test_wrong_edge(self):
        grader = GOEGrader()
        metrics = _make_metrics(approach_direction_change=95.0)
        modifier = grader.detect_modifier(metrics, expected_rotations=3.0)
        assert modifier == "e"

    def test_unclear_edge(self):
        grader = GOEGrader()
        metrics = _make_metrics(approach_direction_change=70.0)
        modifier = grader.detect_modifier(metrics, expected_rotations=3.0)
        assert modifier == "!"


class TestGOEGraderPositives:
    def test_all_bullets_met(self):
        grader = GOEGrader()
        metrics = _make_metrics(
            max_height=0.40,
            landing_com_velocity=-0.5,
            landing_smoothness=0.8,
            hard_landing=0.2,
            rotation_speed=400,
            airtime=0.5,
            approach_direction_change=50,
            arm_position_score=0.8,
            landing_trunk_recovery=0.7,
        )
        positives = grader.count_positives(metrics)
        assert "height_length" in positives
        assert "takeoff_landing" in positives
        assert "effortless" in positives
        assert "body_position" in positives

    def test_no_positives(self):
        grader = GOEGrader()
        metrics = _make_metrics(
            max_height=0.1,
            landing_smoothness=0.1,
            hard_landing=0.9,
        )
        positives = grader.count_positives(metrics)
        assert len(positives) == 0


class TestGOEGraderNegatives:
    def test_fall_detection(self):
        grader = GOEGrader()
        metrics = _make_metrics(landing_smoothness=0.02, hard_landing=0.95)
        negatives = grader.detect_negatives(metrics)
        assert "fall" in negatives

    def test_no_fall(self):
        grader = GOEGrader()
        metrics = _make_metrics(landing_smoothness=0.6, hard_landing=0.3)
        negatives = grader.detect_negatives(metrics)
        assert "fall" not in negatives

    def test_poor_speed_height(self):
        grader = GOEGrader()
        metrics = _make_metrics(airtime=0.1)
        negatives = grader.detect_negatives(metrics)
        assert "poor_speed_height" in negatives


class TestGOEGraderComputeGrade:
    def test_perfect_execution_grade_plus5(self):
        grader = GOEGrader()
        metrics = _make_metrics(
            max_height=0.40,
            landing_com_velocity=-0.5,
            landing_smoothness=0.9,
            hard_landing=0.1,
            rotation_speed=450,
            airtime=0.55,
            approach_direction_change=50,
            arm_position_score=0.9,
            landing_trunk_recovery=0.8,
            rotation_count=3.0,
        )
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.grade == 5
        assert grade.base_value == pytest.approx(4.20)
        assert grade.estimated_score == pytest.approx(6.30)
        assert grade.modifier == ""

    def test_fall_forces_minus5(self):
        grader = GOEGrader()
        metrics = _make_metrics(
            landing_smoothness=0.02,
            hard_landing=0.95,
            rotation_count=3.0,
        )
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.grade == -5
        assert grade.estimated_score == pytest.approx(2.10)

    def test_any_error_caps_at_plus3(self):
        grader = GOEGrader()
        metrics = _make_metrics(
            max_height=0.40,
            landing_com_velocity=-0.5,
            landing_smoothness=0.9,
            hard_landing=0.1,
            rotation_speed=450,
            airtime=0.55,
            approach_direction_change=50,
            arm_position_score=0.9,
            landing_trunk_recovery=0.8,
            rotation_count=2.85,  # q modifier = error
        )
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.grade <= 3  # Capped at +3 because q error exists

    def test_neutral_execution(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=3.0)
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.grade == 0
        assert grade.estimated_score == pytest.approx(4.20)

    def test_under_rotated_modifier_reduces_bv(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=2.6)
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.modifier == "<"
        assert grade.base_value == pytest.approx(3.36)  # 80% of 4.20

    def test_confidence_with_missing_metrics(self):
        grader = GOEGrader()
        metrics = _make_metrics(rotation_count=3.0)  # Only 1 metric
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.confidence < 1.0
