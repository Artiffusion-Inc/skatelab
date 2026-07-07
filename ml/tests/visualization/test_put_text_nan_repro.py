"""Repro — `int(font_scale * 32)` crash on NaN font_scale in put_text calls (#1212).

Bug: ml/src/visualization/hud/elements.py lines 371, 396, 513

    font_size=int(font_scale * 32)

If `font_scale` is NaN (corrupt config / upstream NaN propagation),
`int(NaN)` raises `ValueError: cannot convert float NaN to integer`,
aborting the entire label text render.

Lines 158, 240 use literal `0.6 * 32` (safe). Lines 371, 396, 513 use
`font_scale * 32` (vulnerable). Line 396 also factors 0.8 (still NaN-prone).

Fix: Add `math.isfinite(font_scale)` guard before the int() conversion,
e.g. `font_size = int(font_scale * 32) if math.isfinite(font_scale) else 32`.

Methodology (per audit reglement):
- Behavioral: NaN font_scale fed to the actual functions must not crash
  (proves the guard is at the trust boundary, not just somewhere).
- Regression: valid finite font_scale still produces sane int.
- Source check: locks down `math.isfinite` so a future revert fails the suite.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

# conftest.py adds ml/ to sys.path, so `src` is the ml/src package.
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from src.types import BladeState3D, BladeType, MotionDirection  # noqa: E402
from src.visualization.hud import elements  # noqa: E402
from src.visualization.hud.elements import (  # noqa: E402
    draw_blade_indicator_hud,
    draw_info_text,
)

NAN = float("nan")
INF = float("inf")


def _blank_frame(w=640, h=480):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _blade_state():
    return BladeState3D(
        blade_type=BladeType.INSIDE,
        foot="left",
        motion_direction=MotionDirection.FORWARD,
        foot_angle=-15.0,
        ankle_angle=90.0,
        knee_angle=120.0,
        vertical_accel=0.0,
        position_3d=(0, 0, 0),
        velocity_3d=(0, 0, 0),
        confidence=0.8,
        frame_idx=0,
    )


def _call_safe(fn, *args, **kwargs):
    """Call fn; surface a clean assertion on int(NaN) ValueError."""
    try:
        return fn(*args, **kwargs)
    except ValueError as ex:
        if "cannot convert float NaN to integer" in str(ex):
            raise AssertionError(
                f"BUG #1212: int(NaN) crash in put_text font_size path: {ex!r}. "
                f"Add math.isfinite(font_scale) guard before int(font_scale * 32)."
            ) from ex
        raise


# -----------------------------------------------------------------------------
# Behavioral 1: NaN font_scale in draw_blade_indicator_hud must not crash
# -----------------------------------------------------------------------------
def test_blade_indicator_nan_font_scale_does_not_crash(monkeypatch):
    """NaN `font_scale` (e.g. from corrupt config) must not raise
    `ValueError: cannot convert float NaN to integer` in
    `int(font_scale * 32)` at the put_text call (elements.py:371).
    """
    monkeypatch.setattr(elements, "font_scale", NAN)
    frame = _blank_frame()
    _call_safe(draw_blade_indicator_hud, frame, _blade_state())


# -----------------------------------------------------------------------------
# Behavioral 2: NaN font_scale in draw_info_text must not crash
# -----------------------------------------------------------------------------
def test_info_text_nan_font_scale_does_not_crash(monkeypatch):
    """NaN `font_scale` must not raise in `int(font_scale * 32)`
    at the put_text call (elements.py:513). draw_info_text iterates
    over multiple lines, so the crash aborts all of them.
    """
    monkeypatch.setattr(elements, "font_scale", NAN)
    frame = _blank_frame()
    _call_safe(draw_info_text, frame, ["Line 1", "Line 2"], (10, 30))


# -----------------------------------------------------------------------------
# Behavioral 3: inf font_scale (inf*32 = inf -> int(inf) ValueError)
# -----------------------------------------------------------------------------
def test_info_text_inf_font_scale_does_not_crash(monkeypatch):
    """Inf `font_scale` -> inf*32 = inf -> int(inf) ValueError too.
    Same guard should catch it (math.isfinite covers both NaN and inf).
    """
    monkeypatch.setattr(elements, "font_scale", INF)
    frame = _blank_frame()
    _call_safe(draw_info_text, frame, ["Line"], (10, 30))


# -----------------------------------------------------------------------------
# Regression: valid finite font_scale still works (no silent no-op regression)
# -----------------------------------------------------------------------------
def test_blade_indicator_valid_font_scale_still_runs(monkeypatch):
    """Sanity: a normal call (finite font_scale) must keep producing a
    frame (guard does not regress the happy path).
    """
    monkeypatch.setattr(elements, "font_scale", 0.6)
    frame = _blank_frame()
    result = draw_blade_indicator_hud(frame, _blade_state())
    assert result is frame
    assert frame.any(), "valid call should draw pixels on the frame"


# -----------------------------------------------------------------------------
# Source check: locks down the math.isfinite guard in put_text call sites
# -----------------------------------------------------------------------------
def test_elements_source_has_isfinite_guard_for_font_scale():
    """Locks down the fix: at least one of the vulnerable put_text
    call sites in elements.py (371, 396, 513) must explicitly check
    `math.isfinite` on `font_scale` before the int() conversion.

    Locks the guard, not a try/except — a try/except around int(NaN)
    would mask the bug at call sites we don't reach in the regression
    suite.
    """
    src_path = elements.__file__
    src = Path(src_path).read_text(encoding="utf-8")

    assert "math.isfinite" in src, (
        "elements.py must guard NaN font_scale with math.isfinite to prevent "
        "int(NaN) crash in put_text calls (#1212). "
        "Source snippet:\n" + src
    )

    # And specifically: the guard must reference font_scale (not just any
    # other variable), so the fix is on the right call sites, not a
    # distraction on a sibling variable.
    func_src = inspect.getsource(draw_blade_indicator_hud)
    assert "math.isfinite" in func_src and "font_scale" in func_src, (
        "draw_blade_indicator_hud must guard NaN font_scale with "
        "math.isfinite(font_scale) before int(font_scale * 32) (#1212). "
        "Source snippet:\n" + func_src
    )

    info_src = inspect.getsource(draw_info_text)
    assert "math.isfinite" in info_src and "font_scale" in info_src, (
        "draw_info_text must guard NaN font_scale with "
        "math.isfinite(font_scale) before int(font_scale * 32) (#1212). "
        "Source snippet:\n" + info_src
    )
