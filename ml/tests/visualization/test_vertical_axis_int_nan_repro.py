"""Repro — `VerticalAxisLayer._draw_dashed_line` int(NaN) crash on NaN coords (#1156).

Bug: ml/src/visualization/layers/vertical_axis_layer.py:214-217

    sx = int(x1 + dx * drawn)
    sy = int(y1 + dy * drawn)
    ex = int(x1 + dx * seg_end)
    ey = int(y1 + dy * seg_end)

If `x1` or `x2` is NaN, `dx = NaN`, and `int(NaN)` raises
`ValueError: cannot convert float NaN to integer`. The
`if dist < 1: return` early-return does NOT catch NaN
(NaN < 1 is False).

Fix: Add `math.isfinite(x1) and math.isfinite(x2)` (and y1, y2) guard
at top of `_draw_dashed_line`.

Methodology (per audit reglement):
- Behavioral: NaN coords fed to the actual function must not crash
  (proves the guard is at the trust boundary, not just somewhere).
- Regression: valid finite coords still draw the dashed line.
- Source check: locks down `math.isfinite` so a future revert (e.g.
  try/except around int(NaN)) fails the suite.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Add ml/src to sys.path so we can import the real `src` package without
# polluting sys.modules with stubs.
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import numpy as np  # noqa: E402

from src.visualization.layers.vertical_axis_layer import VerticalAxisLayer  # noqa: E402

NAN = float("nan")


def _layer():
    return VerticalAxisLayer()


def _blank_frame(w=640, h=480):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _call_draw_dashed(layer, frame, pt1, pt2):
    """Call _draw_dashed_line and surface a clean assertion on int(NaN)."""
    try:
        layer._draw_dashed_line(frame, pt1, pt2, (200, 200, 100), 1, dash=8)
    except ValueError as ex:
        if "cannot convert float NaN to integer" in str(ex):
            raise AssertionError(
                f"BUG #1156: int(NaN) crash in _draw_dashed_line: {ex!r}. "
                f"Add math.isfinite guard at top of method."
            ) from ex
        raise


# -----------------------------------------------------------------------------
# Behavioral 1: NaN x1 in pt1 must not crash
# -----------------------------------------------------------------------------
def test_dash_nan_x1_does_not_crash():
    """NaN `x1` must not raise `ValueError: cannot convert float NaN to
    integer` in int(x1 + dx * drawn). Guard at the trust boundary of the
    inner primitive.
    """
    _call_draw_dashed(_layer(), _blank_frame(), (NAN, 100), (200, 100))


# -----------------------------------------------------------------------------
# Behavioral 2: NaN x2 in pt2 must not crash
# -----------------------------------------------------------------------------
def test_dash_nan_x2_does_not_crash():
    """Symmetric to x1."""
    _call_draw_dashed(_layer(), _blank_frame(), (100, 100), (NAN, 100))


# -----------------------------------------------------------------------------
# Behavioral 3: NaN y1 in pt1 must not crash
# -----------------------------------------------------------------------------
def test_dash_nan_y1_does_not_crash():
    """NaN `y1` must not raise `ValueError` in int(y1 + dy * drawn)."""
    _call_draw_dashed(_layer(), _blank_frame(), (100, NAN), (200, 200))


# -----------------------------------------------------------------------------
# Behavioral 4: both endpoints NaN must not crash
# -----------------------------------------------------------------------------
def test_dash_both_nan_does_not_crash():
    """Worst case: both endpoints NaN. The dist=NaN early-return (NaN < 1
    is False) is exactly the path the issue describes. Guard must catch
    this case too.
    """
    _call_draw_dashed(_layer(), _blank_frame(), (NAN, NAN), (NAN, NAN))


# -----------------------------------------------------------------------------
# Regression: valid finite coords still draw the dashed line
# -----------------------------------------------------------------------------
def test_dash_valid_finite_still_draws():
    """Sanity: a normal call (finite pt1, pt2) must keep producing a
    dashed line on the frame. Locks down that the guard doesn't regress
    the happy path.
    """
    layer = _layer()
    frame = _blank_frame()
    layer._draw_dashed_line(frame, (100, 100), (300, 100), (200, 200, 100), 1, dash=8)
    # Some pixels along the line should be non-zero (color drawn).
    assert frame.any(), "valid call should draw pixels on the frame"


# -----------------------------------------------------------------------------
# Source check: locks down the math.isfinite guard
# -----------------------------------------------------------------------------
def test_draw_dashed_line_source_has_isfinite_guard():
    """Locks down the fix: `_draw_dashed_line` must explicitly check
    `math.isfinite` on the endpoint coordinates. The fix idiom
    (`isfinite(x1) and isfinite(x2)`) — not just `dist < 1` which fails
    to catch NaN. A try/except around int(NaN) would mask the bug.
    """
    src = inspect.getsource(VerticalAxisLayer._draw_dashed_line)
    assert "math.isfinite" in src, (
        "VerticalAxisLayer._draw_dashed_line must guard NaN coords with "
        "math.isfinite to prevent int(NaN) crash (#1156). "
        "Source snippet:\n" + src
    )
