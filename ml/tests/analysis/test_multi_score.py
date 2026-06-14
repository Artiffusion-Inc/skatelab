"""Tests for multi-dimensional scoring."""

import pytest
from ml.src.analysis.multi_score import compute_subscores, _normalize


class TestNormalize:
    def test_clamp_below_zero(self):
        assert _normalize(-0.5) == 0.0

    def test_clamp_above_one(self):
        assert _normalize(1.5) == 1.0

    def test_midpoint(self):
        assert _normalize(0.5) == 0.5

    def test_custom_range(self):
        assert _normalize(5.0, min_val=0.0, max_val=10.0) == 0.5


class TestComputeSubscores:
    @pytest.fixture
    def sample_metrics(self):
        return {
            "airtime": 0.5,
            "relative_jump_height": 0.4,
            "approach_consistency": 5.0,
            "rotation_speed": 450,
            "total_rotation_deg": 720,
            "under_rotation_deg": 30,
            "arm_position_score": 0.7,
            "symmetry": 0.75,
            "landing_knee_angle": 110,
            "landing_knee_stability": 0.8,
            "landing_smoothness": 0.6,
            "hard_landing": 0.2,
            "landing_trunk_recovery": 0.9,
            "approach_torso_lean": 5,
            "trunk_lean": 10,
        }

    def test_returns_five_subscores(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        assert len(result.subscores) == 5

    def test_overall_in_range(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        assert 0 <= result.overall <= 10

    def test_subscore_names(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        names = [s.name for s in result.subscores]
        assert names == ["takeoff_power", "rotation_axis", "arm_coordination", "landing_absorption", "core_stability"]

    def test_subscore_values_in_range(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        for s in result.subscores:
            assert 0 <= s.value <= 10
            assert 0 <= s.confidence <= 1

    def test_default_quality(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        assert result.data_quality == "good"
        assert result.skeleton_reliability == "reliable"