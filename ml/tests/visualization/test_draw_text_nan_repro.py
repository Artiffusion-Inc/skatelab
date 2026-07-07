"""Repro — `int(x), int(y)` crash on NaN position in draw_text_outlined (#1243).

Bug: ml/src/visualization/core/text.py:63-65

    x, y = position
    _pos = (int(x), int(y))   # NaN -> int(NaN) raises

If `position` carries NaN coords (corrupt text position, missing HUD anchor,
partial layer state), `int(NaN)` raises
`ValueError: cannot convert float NaN to integer`, aborting the entire
text render and breaking the HUD export.

Fix: Add `math.isfinite(x) and math.isfinite(y)` guard before the int()
conversion. Crash at trust boundary, not at every caller.

Methodology (per audit reglement):
- Behavioral: NaN position fed to draw_text_outlined must not crash
  (proves the guard is at the trust boundary, not just somewhere).
- Regression: valid finite position still produces a drawn frame.
- Source check: locks down `math.isfinite` so a future revert fails the suite.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from src.visualization.core import text as text_module
from src.visualization.core.text import draw_text_outlined

NAN = float("nan")
INF = float("inf")


def _blank_frame(w=640, h=480):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _call_safe(fn, *args, **kwargs):
    """Call fn; surface a clean assertion on int(NaN) ValueError."""
    try:
        return fn(*args, **kwargs)
    except ValueError as ex:
        if "cannot convert float NaN to integer" in str(ex):
            raise AssertionError(
                f"BUG #1243: int(NaN) crash in draw_text position path: {ex!r}. "
                f"Add math.isfinite(x) and math.isfinite(y) guard before "
                f"int(x), int(y)."
            ) from ex
        raise


# -----------------------------------------------------------------------------
# Behavioral 1: NaN x in position must not crash
# -----------------------------------------------------------------------------
def test_draw_text_outlined_nan_x_does_not_crash():
    """NaN x in `position` (e.g. corrupt HUD anchor) must not raise
    `ValueError: cannot convert float NaN to integer` in
    `int(x), int(y)` at the cv2.putText call (text.py:65).
    """
    frame = _blank_frame()
    _call_safe(draw_text_outlined, frame, "Hello", (NAN, 30))


# -----------------------------------------------------------------------------
# Behavioral 2: NaN y in position must not crash
# -----------------------------------------------------------------------------
def test_draw_text_outlined_nan_y_does_not_crash():
    """NaN y in `position` must not raise in `int(x), int(y)`
    at the cv2.putText call (text.py:65).
    """
    frame = _blank_frame()
    _call_safe(draw_text_outlined, frame, "Hello", (10, NAN))


# -----------------------------------------------------------------------------
# Behavioral 3: both NaN must not crash
# -----------------------------------------------------------------------------
def test_draw_text_outlined_nan_both_does_not_crash():
    """Both coords NaN (partial layer state) must not raise
    in `int(x), int(y)` at the cv2.putText call (text.py:65).
    """
    frame = _blank_frame()
    _call_safe(draw_text_outlined, frame, "Hello", (NAN, NAN))


# -----------------------------------------------------------------------------
# Behavioral 4: inf in position must not crash (int(inf) raises too)
# -----------------------------------------------------------------------------
def test_draw_text_outlined_inf_position_does_not_crash():
    """Inf coords -> int(inf) ValueError too.
    Same guard should catch it (math.isfinite covers both NaN and inf).
    """
    frame = _blank_frame()
    _call_safe(draw_text_outlined, frame, "Hello", (INF, 30))


# -----------------------------------------------------------------------------
# Regression: valid finite position still works (no silent no-op regression)
# -----------------------------------------------------------------------------
def test_draw_text_outlined_valid_position_still_runs():
    """Sanity: a normal call (finite position) must keep producing a
    frame with text pixels (guard does not regress the happy path).
    """
    frame = _blank_frame()
    result = draw_text_outlined(frame, "Hello", (10, 30))
    assert result is frame
    assert frame.any(), "valid call should draw pixels on the frame"


# -----------------------------------------------------------------------------
# Source check: locks down the math.isfinite guard for position in text.py
# -----------------------------------------------------------------------------
def test_text_source_has_isfinite_guard_for_position():
    """Locks down the fix: draw_text_outlined must explicitly check
    `math.isfinite` on the position coords before the int() conversion.

    Locks the guard, not a try/except — a try/except around int(NaN)
    would mask the bug at call sites we don't reach in the regression
    suite.
    """
    src_path = text_module.__file__
    src = Path(src_path).read_text(encoding="utf-8")

    assert "math.isfinite" in src, (
        "text.py must guard NaN position with math.isfinite to prevent "
        "int(NaN) crash in draw_text_outlined (#1243). "
        "Source snippet:\n" + src
    )

    # And specifically: the guard must be inside draw_text_outlined
    # (the function called out in the issue), not just a sibling function.
    func_src = inspect.getsource(draw_text_outlined)
    assert "math.isfinite" in func_src, (
        "draw_text_outlined must guard NaN position with math.isfinite "
        "before int(x), int(y) (#1243). "
        "Source snippet:\n" + func_src
    )
