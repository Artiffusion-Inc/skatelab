"""End-to-end integration test for GOE scoring pipeline."""

import pytest

from src.analysis.goe_grader import GOEGrader
from src.analysis.recommender import Recommender
from src.types import GOEGrade, MetricResult


class TestGOEIntegration:
    def test_full_pipeline_good_jump(self):
        """Good 3T -> positive GOE -> recommendations with ISU context."""
        grader = GOEGrader()
        recommender = Recommender()

        metrics = [
            MetricResult(
                name="max_height", value=0.40, unit="norm", is_good=True, reference_range=(0.2, 0.5)
            ),
            MetricResult(
                name="landing_com_velocity",
                value=-0.5,
                unit="norm/s",
                is_good=True,
                reference_range=(-2.0, 0.0),
            ),
            MetricResult(
                name="landing_smoothness",
                value=0.85,
                unit="score",
                is_good=True,
                reference_range=(0.5, 1.0),
            ),
            MetricResult(
                name="hard_landing",
                value=0.15,
                unit="score",
                is_good=True,
                reference_range=(0.0, 0.5),
            ),
            MetricResult(
                name="rotation_speed",
                value=420,
                unit="deg/s",
                is_good=True,
                reference_range=(300, 550),
            ),
            MetricResult(
                name="airtime", value=0.50, unit="s", is_good=True, reference_range=(0.3, 0.7)
            ),
            MetricResult(
                name="arm_position_score",
                value=0.8,
                unit="score",
                is_good=True,
                reference_range=(0.6, 1.0),
            ),
            MetricResult(
                name="landing_trunk_recovery",
                value=0.7,
                unit="score",
                is_good=True,
                reference_range=(0.5, 1.0),
            ),
            MetricResult(
                name="rotation_count",
                value=3.0,
                unit="score",
                is_good=True,
                reference_range=(2.5, 3.5),
            ),
        ]

        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.grade >= 3

        recommendations = recommender.recommend_with_goe(metrics, "toe_loop", grade)
        assert any("GOE" in r for r in recommendations)

    def test_full_pipeline_fall(self):
        """Fall on 3T -> GOE -5 -> fall deduction."""
        from app.services.choreography.deductions import detect_deductions

        grader = GOEGrader()
        metrics_values = {"landing_smoothness": 0.02, "hard_landing": 0.95, "rotation_count": 3.0}
        metrics = [
            MetricResult(name=k, value=v, unit="score", is_good=False, reference_range=(0, 1))
            for k, v in metrics_values.items()
        ]

        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.grade == -5
        assert grade.estimated_score == pytest.approx(2.10)

        deductions = detect_deductions(metrics_values)
        assert len(deductions) == 1
        assert deductions[0].deduction.id == "fall"

    def test_modifier_under_rotation_reduces_bv(self):
        """3T with < modifier -> BV = 3.36 (80% of 4.20)."""
        grader = GOEGrader()
        metrics = [
            MetricResult(
                name="rotation_count",
                value=2.6,
                unit="score",
                is_good=False,
                reference_range=(0, 1),
            )
        ]
        grade = grader.compute_goe_grade(metrics, base_value=4.20, expected_rotations=3.0)
        assert grade.modifier == "<"
        assert grade.base_value == pytest.approx(3.36)
