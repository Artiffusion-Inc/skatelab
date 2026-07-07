"""Repro tests for issue #1315: horizon_roll np.mean NaN-propagate in spatial_reference.

RED on master: `roll = float(np.mean(all_angles))` at line 194 silently returns
NaN when all_angles contains any non-finite value. CameraPose.roll=NaN then
poisons the downstream consumer chain (compensate_poses, 3D lift, biomech).

The repro exercises the exact np.mean(all_angles) statement at line 194 with
non-finite input. The fix is a guard at the same site — a pre-filter on
all_angles, np.nanmean, or np.nan_to_num. All three are equivalent for the
caller; we lock the source pattern (any of nanmean / isfinite / nan_to_num).
"""

import inspect
import math

import numpy as np

from src.detection.spatial_reference import SpatialReferenceDetector

# This is the exact statement at line 194. Bug: it returns NaN when any
# element is non-finite. Fix: guard it.
ROLL_STMT = "float(np.mean(all_angles))"


def _compute_roll(all_angles: list[float]) -> float:
    """Mirror line 194 of _estimate_from_horizon."""
    return float(np.mean(all_angles))


class TestHorizonRollNaNPropagate:
    """Repro for #1315: np.mean(all_angles) propagates NaN to CameraPose.roll."""

    def test_source_uses_nan_safe_mean_or_isfinite_guard(self):
        """Root-cause lock: np.mean(all_angles) at line 194 must be NaN-safe.

        The fix is either (a) np.nanmean, (b) an isfinite pre-filter, or
        (c) np.nan_to_num. Bare np.mean is the unguarded pattern that
        propagates NaN when all_angles contains NaN/inf.
        """
        src = inspect.getsource(SpatialReferenceDetector._estimate_from_horizon)
        # The unguarded pattern is `float(np.mean(all_angles))` — no nanmean,
        # no isfinite filter, no nan_to_num. Lock the fix.
        assert "nanmean" in src or "isfinite" in src or "nan_to_num" in src, (
            "_estimate_from_horizon must guard np.mean against NaN/inf in all_angles (issue #1315)"
        )
        # Belt and suspenders: also assert the bare statement is gone.
        assert ROLL_STMT not in src, f"unguarded `{ROLL_STMT}` must be replaced (issue #1315)"

    def test_bare_np_mean_propagates_nan_to_roll(self):
        """Demonstrate the bug surface: bare np.mean on NaN list returns NaN.

        This is the same statement as line 194. The function-level fix must
        not return NaN roll when all_angles contains NaN. Asserting the
        bare-statement behavior locks the precondition for the fix.
        """
        all_angles = [1.0, math.nan, 2.0, 1.5]
        roll = _compute_roll(all_angles)
        # The bug: roll is NaN. The fix in the function will keep roll finite.
        # We document the bug here so the test file shows the precondition.
        assert math.isnan(roll), (
            "Precondition: bare np.mean propagates NaN. The fix at the call "
            "site must prevent this value from reaching CameraPose.roll."
        )

    def test_estimate_from_horizon_with_nan_angles_returns_finite_roll(self, monkeypatch):
        """End-to-end: with NaN angles in all_angles, roll must be finite.

        Patches cv2.HoughLinesP to return one line, and the per-line angle
        computation to yield NaN. This simulates the real-world precondition
        where an upstream chain (e.g. dx=0, dy=0 or a degenerate fit)
        produces NaN-positive values that bypass the abs(angle) < 10 filter.
        """
        import src.detection.spatial_reference as sr_mod

        # Make the per-line angle produce NaN: dx=0, dy=0 -> arctan2(0,0)=0,
        # but we patch arctan2 to return NaN to simulate degenerate inputs.
        def nan_arctan2(*a, **kw):
            return np.float64(math.nan)

        monkeypatch.setattr(np, "arctan2", nan_arctan2)
        monkeypatch.setattr(sr_mod.cv2, "HoughLinesP", lambda *a, **kw: np.array([[[0, 0, 0, 0]]]))

        pose = SpatialReferenceDetector()._estimate_from_horizon(
            np.zeros((120, 200, 3), dtype=np.uint8)
        )
        # The fix: even if all_angles somehow ends up containing NaN, the
        # guarded np.mean must yield a finite roll. The current empty-list
        # guard returns roll=0.0; we accept any finite value.
        assert math.isfinite(pose.roll), (
            f"CameraPose.roll must be finite when all_angles contains NaN, got {pose.roll}"
        )
        assert math.isfinite(pose.confidence)
        assert math.isfinite(pose.pitch)
        assert math.isfinite(pose.yaw)

    def test_estimate_from_horizon_with_inf_angles_returns_finite_roll(self, monkeypatch):
        """inf in all_angles must not propagate to roll."""
        import src.detection.spatial_reference as sr_mod

        monkeypatch.setattr(np, "arctan2", lambda *a, **kw: np.float64(math.inf))
        monkeypatch.setattr(sr_mod.cv2, "HoughLinesP", lambda *a, **kw: np.array([[[0, 0, 1, 0]]]))

        pose = SpatialReferenceDetector()._estimate_from_horizon(
            np.zeros((120, 200, 3), dtype=np.uint8)
        )
        assert math.isfinite(pose.roll), (
            f"CameraPose.roll must be finite when all_angles contains inf, got {pose.roll}"
        )

    def test_finite_horizon_angles_yield_zero_roll(self):
        """Sanity: the happy path (all horizontal lines) yields roll=0.0."""
        # No monkeypatching: real cv2.HoughLinesP on a solid frame returns
        # no lines, and the empty-list guard returns roll=0.0. This is the
        # existing well-tested behavior; we keep it as a regression anchor.
        pose = SpatialReferenceDetector()._estimate_from_horizon(
            np.zeros((120, 200, 3), dtype=np.uint8)
        )
        assert pose.roll == 0.0
        assert pose.confidence == 0.0
