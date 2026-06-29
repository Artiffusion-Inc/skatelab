"""Tests for multi-dimensional scoring."""

from typing import ClassVar

import pytest

from ml.src.analysis.multi_score import _normalize, compute_subscores


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
        assert names == [
            "takeoff_power",
            "rotation_axis",
            "arm_coordination",
            "landing_absorption",
            "core_stability",
        ]

    def test_subscore_values_in_range(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        for s in result.subscores:
            assert 0 <= s.value <= 10
            assert 0 <= s.confidence <= 1

    def test_default_quality(self, sample_metrics):
        result = compute_subscores(sample_metrics)
        assert result.data_quality == "good"
        assert result.skeleton_reliability == "reliable"


# --------------------------------------------------------------------------- #
# #434 — landing_absorption must score soft landing higher than hard landing
# --------------------------------------------------------------------------- #
class TestLandingAbsorptionHardLandingScale:
    _BASE: ClassVar[dict] = {
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
        "landing_trunk_recovery": 0.9,
        "approach_torso_lean": 5,
        "trunk_lean": 10,
    }

    def _landing_absorption(self, metrics: dict) -> float:
        score = compute_subscores(metrics)
        sub = next(s for s in score.subscores if s.name == "landing_absorption")
        return sub.value

    def test_soft_landing_scores_higher_than_hard_landing(self):
        """A soft landing (hard_landing=1.0 per compute_hard_landing's scale
        '1.0=soft, 0.0=very hard') must yield a HIGHER landing_absorption
        subscore than a very hard landing (hard_landing=0.0). Old code used
        (1 - hard_landing), inverting the scale. #434"""
        soft = self._BASE | {"hard_landing": 1.0}
        hard = self._BASE | {"hard_landing": 0.0}

        soft_score = self._landing_absorption(soft)
        hard_score = self._landing_absorption(hard)

        assert soft_score > hard_score, (
            f"landing_absorption inverted: soft landing (hard_landing=1.0) "
            f"scores {soft_score}, hard landing (hard_landing=0.0) scores "
            f"{hard_score}. compute_hard_landing returns 1.0=soft/0.0=very "
            "hard (metrics.py:988); multi_score must use hard_landing directly."
        )
