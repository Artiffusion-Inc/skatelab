"""Tests for ISU deductions module."""

from app.services.choreography.deductions import (
    ALL_DEDUCTIONS,
    DETECTABLE_DEDUCTIONS,
    detect_deductions,
)


class TestDeductions:
    def test_all_deductions_loaded(self):
        assert len(ALL_DEDUCTIONS) >= 10

    def test_detectable_deductions_subset(self):
        assert len(DETECTABLE_DEDUCTIONS) >= 1
        assert all(d.detectable for d in DETECTABLE_DEDUCTIONS)

    def test_fall_detected(self):
        # Fall = hard impact (hard_landing≈0, very hard end of scale) + low smoothness. #421
        results = detect_deductions({"landing_smoothness": 0.02, "hard_landing": 0.05})
        assert len(results) == 1
        assert results[0].deduction.id == "fall"
        assert results[0].confidence >= 0.7

    def test_no_fall(self):
        # Soft landing (high hard_landing) + decent smoothness is NOT a fall. #421
        results = detect_deductions({"landing_smoothness": 0.6, "hard_landing": 0.9})
        assert len(results) == 0

    def test_fall_requires_both_signals(self):
        # Hard landing mid-scale (0.5) is not a hard-enough impact to flag a fall. #421
        results = detect_deductions({"landing_smoothness": 0.02, "hard_landing": 0.5})
        assert len(results) == 0
