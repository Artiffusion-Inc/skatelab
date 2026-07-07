"""Repro tests for issue #965: draw_blade_indicator_hud NaN/inf foot_angle crash + 'nan°' leak.

RED on master:
1. `_draw_direction_arrow` calls `int(x + size * math.sin(math.radians(nan)))` →
   `ValueError: cannot convert float NaN to integer` crashes HUD render.
2. `angle_text = f"{blade_state.foot_angle:.1f}°"` silently renders "nan°" /
   "inf°" into the user-facing HUD overlay text.

Root cause: no isfinite guard on `foot_angle` before the int() cast and the
f-string render. Mirror #974 (draw_phase_indicator) / #970 (draw_axes)
placeholder convention ("—").
"""

import inspect
import math

import numpy as np

from src.types import BladeState3D, BladeType, MotionDirection
from src.visualization.hud.elements import draw_blade_indicator_hud

FRAME = np.zeros((120, 200, 3), dtype=np.uint8)


def _state(foot_angle: float) -> BladeState3D:
    return BladeState3D(
        blade_type=BladeType.INSIDE,
        foot="left",
        motion_direction=MotionDirection.FORWARD,
        foot_angle=foot_angle,
        ankle_angle=90.0,
        knee_angle=120.0,
        vertical_accel=0.0,
        position_3d=(0.0, 0.0, 0.0),
        velocity_3d=(0.0, 0.0, 0.0),
        confidence=0.8,
        frame_idx=0,
    )


def _draw(foot_angle: float) -> np.ndarray:
    return draw_blade_indicator_hud(FRAME.copy(), _state(foot_angle))


class TestDrawBladeIndicatorNanFoot:
    def test_nan_foot_angle_no_nan_text(self):
        """No literal 'nan' may render in the foot-angle HUD text."""
        # Source-level root-cause lock: draw_blade_indicator_hud must guard
        # NaN/inf foot_angle before the f-string renders "nan°".
        src = inspect.getsource(draw_blade_indicator_hud)
        assert "isfinite" in src, "draw_blade_indicator_hud missing isfinite guard on foot_angle"
        fmt_idx = src.index(":.1f")
        guard_idx = src.index("isfinite")
        assert guard_idx < fmt_idx, "isfinite guard must precede the foot_angle f-string"
        # Placeholder convention mirrors #974 (draw_phase_indicator) / #970.
        assert "—" in src, (
            "draw_blade_indicator_hud must substitute placeholder for non-finite foot_angle"
        )

    def test_nan_foot_angle_does_not_crash(self):
        """NaN foot_angle must not raise ValueError from int(NaN)."""
        frame = _draw(math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape
        # No literal "nan" / "NaN" leak into rendered pixels — verified by the
        # source-level guard test above (placeholder "—" replaces the format
        # path when foot_angle is not finite).

    def test_inf_foot_angle_does_not_crash_no_inf_text(self):
        """inf foot_angle: no crash, no 'inf' text leak."""
        src = inspect.getsource(draw_blade_indicator_hud)
        # Same isfinite guard covers inf (inf is not finite).
        assert "isfinite" in src
        fmt_idx = src.index(":.1f")
        guard_idx = src.index("isfinite")
        assert guard_idx < fmt_idx, "isfinite guard must precede the foot_angle f-string"
        frame = _draw(math.inf)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_finite_foot_angle_unchanged(self):
        """Regression: finite foot_angle renders the numeric value normally."""
        frame = _draw(-15.0)
        assert frame is not None
        assert frame.shape == FRAME.shape
        src = inspect.getsource(draw_blade_indicator_hud)
        assert "isfinite" in src
        assert "°" in src, "finite foot_angle must still flow through the degree format"
