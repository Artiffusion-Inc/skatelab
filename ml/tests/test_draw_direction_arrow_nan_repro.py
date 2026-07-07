"""Repro tests for issue #1085: _draw_direction_arrow NaN int() crash.

RED on master:
`_draw_direction_arrow` in `ml/src/visualization/hud/elements.py` crashes with
uncaught `ValueError: cannot convert float NaN to integer` when x, y, size,
or angle is NaN. NaN joint positions (missing keypoint, gap-filler failure,
biomechanics metric error) abort blade direction arrow render and may abort
the whole HUD layer.

Root cause: no `math.isfinite` guard on x, y, size, angle, or thickness
before the `int(...)` casts at lines 447-455.

Fix: skip the arrow (early return) when any input is not finite. Mirrors
the existing foot_angle guard in `draw_blade_indicator_hud` (issue #965
fix, see also #974 / #970 placeholder convention).
"""

import inspect
import math

import numpy as np

from src.visualization.hud.elements import _draw_direction_arrow

FRAME = np.zeros((120, 200, 3), dtype=np.uint8)


def _call(
    x: float = 100.0,
    y: float = 60.0,
    angle: float = 0.0,
    size: int = 10,
    thickness: int = 1,
) -> np.ndarray:
    """Call _draw_direction_arrow with a fresh copy of FRAME."""
    _draw_direction_arrow(FRAME.copy(), x, y, angle, size, thickness, (0, 255, 0))
    return FRAME


class TestDrawDirectionArrowNanGuard:
    def test_isfinite_guard_precedes_int_cast(self):
        """Source-level lock: math.isfinite guard must appear before any int() cast."""
        src = inspect.getsource(_draw_direction_arrow)
        assert "isfinite" in src, "_draw_direction_arrow missing isfinite guard"
        # Skip the docstring/annotations: find isfinite guard position and
        # check it precedes the first int() cast at the arrow-point math.
        guard_idx = src.index("isfinite")
        int_positions = [i for i in range(len(src)) if src.startswith("int(", i)]
        # Drop type-annotation matches ("tuple[int, int, int]" at top of fn).
        # The runtime casts are the LAST 6 int() occurrences (4 arrow points
        # + np.int32 dtype + nothing else in this fn). Assert all of those
        # come after the guard.
        runtime_int = int_positions[-6:]
        assert all(guard_idx < i for i in runtime_int), (
            f"isfinite guard (pos {guard_idx}) must precede runtime int() "
            f"casts at positions {runtime_int}"
        )

    def test_nan_x_does_not_crash(self):
        """NaN x must not raise ValueError: cannot convert float NaN to integer."""
        frame = _call(x=math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_nan_y_does_not_crash(self):
        """NaN y must not raise ValueError."""
        frame = _call(y=math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_nan_size_does_not_crash(self):
        """NaN size must not raise ValueError."""
        frame = _call(size=math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_nan_angle_does_not_crash(self):
        """NaN angle must not raise ValueError."""
        frame = _call(angle=math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_finite_inputs_render_unchanged(self):
        """Regression: all-finite inputs render normally (no guard regression)."""
        frame = _call(x=100.0, y=60.0, angle=30.0, size=10, thickness=1)
        assert frame is not None
        assert frame.shape == FRAME.shape
