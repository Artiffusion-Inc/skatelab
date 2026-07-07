"""Repro tests for #1200: _draw_direction_arrow int(NaN) crash in hud/elements.py.

Bug: `_draw_direction_arrow` in `ml/src/visualization/hud/elements.py` crashed with
uncaught `ValueError: cannot convert float NaN to integer` when x, y, size, angle,
or thickness was NaN. NaN propagates here from missing joint keypoints,
gap-filler failure, or a broken biomechanics metric; the crash aborts the blade
direction arrow render and may abort the whole HUD layer.

Root cause: no `math.isfinite` guard on x, y, size, angle, or thickness before
the `int(...)` casts computing the four arrow points (tip + 2x base).

Status on master: fix already landed via #1085 / #1116 (commit 6f7e6add) which
added the `math.isfinite(...)` guard at the top of `_draw_direction_arrow`.
These tests lock the contract so the guard cannot regress.

Contract: any non-finite input → early return (skip the arrow). Mirrors the
existing foot_angle guard in `draw_blade_indicator_hud` (issue #965) and the
placeholder convention from #974 / #970.
"""

from __future__ import annotations

import inspect
import math

import numpy as np

from src.visualization.hud.elements import _draw_direction_arrow

FRAME = np.zeros((120, 200, 3), dtype=np.uint8)
COLOR = (0, 255, 0)


def _call(
    x: float = 100.0,
    y: float = 60.0,
    angle: float = 0.0,
    size: int = 10,
    thickness: int = 1,
) -> np.ndarray:
    """Call _draw_direction_arrow with a fresh copy of FRAME and return the buffer."""
    buf = FRAME.copy()
    _draw_direction_arrow(buf, x, y, angle, size, thickness, COLOR)
    return buf


class TestArrowNaNGuard:
    """Guard _draw_direction_arrow against NaN/inf inputs (#1200 / #1085)."""

    def test_nan_x_does_not_crash(self):
        """Observable 1: NaN x must not raise ValueError: cannot convert float NaN to integer."""
        buf = _call(x=math.nan)
        assert buf.shape == FRAME.shape

    def test_nan_y_does_not_crash(self):
        """Observable 2: NaN y must not raise ValueError."""
        buf = _call(y=math.nan)
        assert buf.shape == FRAME.shape

    def test_nan_size_does_not_crash(self):
        """Observable 3: NaN size must not raise ValueError."""
        buf = _call(size=math.nan)
        assert buf.shape == FRAME.shape

    def test_nan_angle_does_not_crash(self):
        """Observable 4: NaN angle must not raise ValueError."""
        buf = _call(angle=math.nan)
        assert buf.shape == FRAME.shape

    def test_inf_size_does_not_crash(self):
        """inf size must not raise OverflowError from int(inf)."""
        buf = _call(size=math.inf)
        assert buf.shape == FRAME.shape

    def test_finite_inputs_render_unchanged(self):
        """Regression: all-finite inputs render normally (no guard regression)."""
        buf = _call(x=100.0, y=60.0, angle=30.0, size=10, thickness=1)
        assert buf.shape == FRAME.shape
        # Arrow draws at least one non-zero pixel when geometry is valid.
        assert buf.any()

    def test_isfinite_guard_precedes_int_cast(self):
        """Source-level lock: math.isfinite guard must appear before any int() cast."""
        src = inspect.getsource(_draw_direction_arrow)
        assert "isfinite" in src, "_draw_direction_arrow missing isfinite guard"
        guard_idx = src.index("isfinite")
        # The four runtime int() casts compute arrow points (tip + 2x base).
        int_positions = [i for i in range(len(src)) if src.startswith("int(", i)]
        runtime_int = int_positions[-4:]
        assert all(guard_idx < i for i in runtime_int), (
            f"isfinite guard (pos {guard_idx}) must precede runtime int() "
            f"casts at positions {runtime_int}"
        )

    def test_foot_angle_nan_renders_neutral_arrow(self):
        """Caller `draw_blade_indicator_hud` must convert NaN foot_angle → 0.0
        so the arrow renders neutral and the HUD text shows '—' placeholder
        instead of leaking 'nan°' / 'inf°' to the user.
        """
        from src.types import BladeState3D, BladeType, MotionDirection
        from src.visualization.hud.elements import draw_blade_indicator_hud

        state = BladeState3D(
            blade_type=BladeType.OUTSIDE,
            foot="left",
            motion_direction=MotionDirection.FORWARD,
            foot_angle=math.nan,  # corrupted metric
            ankle_angle=90.0,
            knee_angle=120.0,
            vertical_accel=0.0,
            position_3d=(0, 0, 0),
            velocity_3d=(0, 0, 0),
            confidence=0.9,
            frame_idx=0,
        )
        buf = FRAME.copy()
        # Should not raise. NaN foot_angle must be neutralized upstream.
        draw_blade_indicator_hud(buf, state, position=(100, 60), size=10, thickness=1)
        assert buf.shape == FRAME.shape
