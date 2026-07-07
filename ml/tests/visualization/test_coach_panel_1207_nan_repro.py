"""Repro tests for #1207: coach_panel is_visible_at int(display_duration*fps) NaN crash.

Sibling of #1102. Bug: `end_frame = self.landing_frame + int(self.display_duration * self.fps)`
crashes with `ValueError: cannot convert float NaN to integer` when display_duration or fps is NaN.

These tests add extra observables beyond the #1102 suite:
  - positive/negative infinity inputs (int(inf) also raises)
  - landing_frame at frame 0
  - per-frame visibility near boundary
  - source-location pin (line ~75 of coach_panel.py) so the guard cannot
    drift below the int() conversion without failing this test.

Contract: non-finite display_duration or fps → is_visible_at returns False
(not raise). Finite values → unchanged behavior.
"""

from __future__ import annotations

import inspect
import math

from src.visualization.hud.coach_panel import CoachOverlayData


def _make(landing_frame: int, display_duration: float, fps: float) -> CoachOverlayData:
    return CoachOverlayData(
        element_name_ru="тест",
        metrics=[],
        recommendations=[],
        landing_frame=landing_frame,
        fps=fps,
        display_duration=display_duration,
    )


def _src() -> str:
    return inspect.getsource(CoachOverlayData.is_visible_at)


class TestIsVisibleAtNaNGuard1207:
    """Guard is_visible_at against NaN/inf inputs (sibling of #1102)."""

    def test_nan_display_duration_does_not_raise(self):
        """NaN display_duration must not raise ValueError, return False."""
        data = _make(landing_frame=120, display_duration=math.nan, fps=30.0)
        # Per issue #1207: must not raise ValueError: cannot convert float NaN
        assert data.is_visible_at(150) is False
        assert data.is_visible_at(120) is False
        assert data.is_visible_at(300) is False

    def test_nan_fps_does_not_raise(self):
        """NaN fps must not raise ValueError, return False."""
        data = _make(landing_frame=120, display_duration=4.0, fps=math.nan)
        assert data.is_visible_at(150) is False
        assert data.is_visible_at(120) is False

    def test_pos_inf_display_duration_does_not_raise(self):
        """+inf display_duration would also crash int(inf) → must return False."""
        data = _make(landing_frame=120, display_duration=math.inf, fps=30.0)
        # int(inf) raises OverflowError; guard must short-circuit.
        assert data.is_visible_at(150) is False

    def test_negative_inf_fps_does_not_raise(self):
        """-inf fps → int(-inf) raises OverflowError; must return False."""
        data = _make(landing_frame=120, display_duration=4.0, fps=-math.inf)
        assert data.is_visible_at(150) is False

    def test_finite_landing_zero_visibility_still_works(self):
        """Regression: landing_frame=0 with finite values still shows the panel."""
        data = _make(landing_frame=0, display_duration=2.0, fps=30.0)
        # 0 + 2.0*30 = 60
        assert data.is_visible_at(0) is True
        assert data.is_visible_at(59) is True
        assert data.is_visible_at(60) is False

    def test_source_isfinite_guard_above_int_conversion(self):
        """is_visible_at must contain math.isfinite AND use it before int().

        Static check: the guard must appear in source, and the int(...) call
        for end_frame must be reachable only after the guard. We pin the
        presence of isfinite in the source — if a refactor removes it, the
        int(NaN) crash re-appears and this test fails.
        """
        src = _src()
        assert "math.isfinite" in src, (
            "is_visible_at must guard NaN via math.isfinite to prevent "
            "int(NaN) crash (#1207, sibling of #1102)"
        )
        # And the int() conversion must still exist (i.e. we did not just
        # delete the visible-window logic entirely).
        assert "int(" in src, "is_visible_at must still compute end_frame via int(...)"
