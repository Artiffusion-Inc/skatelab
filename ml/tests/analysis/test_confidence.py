"""Tests for confidence scoring."""

import pytest

from ml.src.analysis.confidence import compute_overall_confidence, compute_phase_confidence
from ml.src.analysis.types import PhaseDetectionResultV2, PhaseExtended


class TestComputePhaseConfidence:
    @pytest.fixture
    def sample_phase(self):
        return PhaseExtended(
            name="takeoff",
            start_frame=55,
            end_frame=60,
            start_time=1.83,
            end_time=2.0,
            confidence=0.91,
            detection_method="com_parabola",
        )

    def test_high_confidence_phase(self, sample_phase):
        result = compute_phase_confidence(sample_phase, total_frames=120, fps=30)
        assert result > 0.5

    def test_short_duration_low_confidence(self):
        phase = PhaseExtended("takeoff", 55, 56, 1.83, 1.87, 0.9, "com_parabola")
        result = compute_phase_confidence(phase, total_frames=120, fps=30)
        assert result < 0.8

    def test_heuristic_lower_than_com(self):
        com_phase = PhaseExtended("air", 60, 85, 2.0, 2.83, 0.88, "com_parabola")
        heuristic_phase = PhaseExtended("air", 60, 85, 2.0, 2.83, 0.88, "heuristic")
        com_conf = compute_phase_confidence(com_phase, 120, 30)
        heuristic_conf = compute_phase_confidence(heuristic_phase, 120, 30)
        assert com_conf > heuristic_conf


class TestComputeOverallConfidence:
    @pytest.fixture
    def sample_result(self):
        return PhaseDetectionResultV2(
            phases=[
                PhaseExtended("approach", 30, 55, 1.0, 1.83, 0.82, "com_parabola"),
                PhaseExtended("takeoff", 55, 60, 1.83, 2.0, 0.91, "com_parabola"),
                PhaseExtended("air", 60, 85, 2.0, 2.83, 0.88, "com_parabola"),
                PhaseExtended("landing", 85, 92, 2.83, 3.07, 0.85, "com_parabola"),
                PhaseExtended("glide_out", 92, 120, 3.07, 4.0, 0.74, "heuristic"),
            ],
            overall_confidence=0.84,
            element_type="axel",
        )

    def test_overall_confidence(self, sample_result):
        conf = compute_overall_confidence(sample_result, total_frames=120, fps=30)
        assert 0.0 < conf <= 1.0

    def test_empty_phases_zero_confidence(self):
        result = PhaseDetectionResultV2(phases=[])
        conf = compute_overall_confidence(result, total_frames=120, fps=30)
        assert conf == 0.0
