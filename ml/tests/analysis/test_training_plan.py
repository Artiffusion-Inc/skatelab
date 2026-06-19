"""Tests for training plan generation."""

import pytest

from ml.src.analysis.training_plan import EXERCISE_RECOMMENDATIONS, generate_training_plan
from ml.src.analysis.types import SubScore


class TestGenerateTrainingPlan:
    @pytest.fixture
    def sample_subscores(self):
        return [
            SubScore("takeoff_power", "Взлётная мощь", 7.2, 0.85, ["airtime"]),
            SubScore("rotation_axis", "Ось вращения", 5.8, 0.72, ["rotation_speed"]),
            SubScore("arm_coordination", "Координация рук", 6.5, 0.68, ["symmetry"]),
            SubScore("landing_absorption", "Амортизация", 4.1, 0.91, ["landing_knee_angle"]),
            SubScore("core_stability", "Стабильность корпуса", 8.0, 0.79, ["trunk_lean"]),
        ]

    def test_generates_plan(self, sample_subscores):
        plan = generate_training_plan(sample_subscores)
        assert len(plan.items) >= 3

    def test_prioritized_by_weakest(self, sample_subscores):
        plan = generate_training_plan(sample_subscores)
        # Landing absorption (4.1) is weakest, should be priority 1
        assert plan.items[0].priority == 1
        assert plan.focus_subscore == "landing_absorption"

    def test_items_not_completed(self, sample_subscores):
        plan = generate_training_plan(sample_subscores)
        for item in plan.items:
            assert item.completed is False

    def test_generated_at_present(self, sample_subscores):
        plan = generate_training_plan(sample_subscores)
        assert plan.generated_at != ""

    def test_all_subscores_have_recommendations(self):
        for key in [
            "takeoff_power",
            "rotation_axis",
            "arm_coordination",
            "landing_absorption",
            "core_stability",
        ]:
            assert key in EXERCISE_RECOMMENDATIONS
            assert len(EXERCISE_RECOMMENDATIONS[key]) >= 1
