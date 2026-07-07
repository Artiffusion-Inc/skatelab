"""Repro tests for #1102: coach_panel is_visible_at int(NaN) crash on NaN display_duration/fps.

Bug: `end_frame = self.landing_frame + int(self.display_duration * self.fps)` crashes
with `ValueError: cannot convert float NaN to integer` when display_duration or fps is NaN.
This aborts the entire HUD render for that frame; user never sees the recommendation overlay.

Contract: NaN display_duration or NaN fps → is_visible_at returns False (not crash).
The HUD stays visible for the user, the overlay just skips drawing this panel.
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


class TestIsVisibleAtNaNGuard:
    """Guard `is_visible_at` against NaN inputs in display_duration / fps."""

    def test_nan_display_duration_returns_false(self):
        """NaN display_duration must not crash int(NaN); return False (hide overlay)."""
        data = _make(landing_frame=100, display_duration=math.nan, fps=30.0)
        # Per issue: must not raise ValueError
        assert data.is_visible_at(150) is False
        # And must not be visible at landing frame either — config is poisoned.
        assert data.is_visible_at(100) is False

    def test_nan_fps_returns_false(self):
        """NaN fps must not crash int(NaN); return False (hide overlay)."""
        data = _make(landing_frame=100, display_duration=4.0, fps=math.nan)
        assert data.is_visible_at(150) is False
        assert data.is_visible_at(100) is False

    def test_both_nan_returns_false(self):
        """Both NaN: same crash path, must return False instead of raising."""
        data = _make(landing_frame=100, display_duration=math.nan, fps=math.nan)
        assert data.is_visible_at(150) is False

    def test_finite_still_works_regression(self):
        """Valid finite values must behave exactly as before — no regression."""
        data = _make(landing_frame=100, display_duration=4.0, fps=30.0)
        # 100 + 4.0*30 = 220
        assert data.is_visible_at(99) is False
        assert data.is_visible_at(100) is True
        assert data.is_visible_at(219) is True
        assert data.is_visible_at(221) is False

    def test_source_has_isfinite_guard(self):
        """is_visible_at source must include a math.isfinite guard for display_duration or fps.

        Static check so a future refactor cannot remove the guard silently and
        re-introduce the int(NaN) crash.
        """
        src = inspect.getsource(CoachOverlayData.is_visible_at)
        # Acceptable guards: math.isfinite on display_duration OR fps, OR any
        # explicit "isnan"/"isnan_or_isinf" check. A bare try/except around int(NaN)
        # also crashes downstream callers, so require explicit isfinite.
        assert "math.isfinite" in src, (
            "is_visible_at must guard NaN via math.isfinite(self.display_duration) "
            "or math.isfinite(self.fps) to prevent int(NaN) crash (#1102)"
        )
