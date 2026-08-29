"""RED repro — `TimerLayer.render` ValueError crash on NaN fps (tranche HG).

`TimerLayer.render` (timer_layer.py:23-49) builds `elapsed = frame_idx / fps`
then `minutes = int(elapsed // 60)` at line 29. The `if fps <= 0` guard
at line 25 catches NEGATIVE and ZERO but NOT NaN (NaN comparisons return
False). A NaN fps from upstream (corrupt video metadata, NaN propagation,
bad config) propagates to `int(NaN)` → `ValueError: cannot convert float
NaN to integer`.

Crash on the unguarded `int(elapsed // 60)` — `int(NaN // 60) = int(NaN) =
ValueError`. The timer layer is a top-level overlay rendered per-frame on
every video; a NaN fps crashes the layer for the entire video duration.
The user never sees a timer (or the entire HUD render aborts if downstream
catches the exception and silently drops the layer).

The fix (NOT applied — repro only): guard `if not math.isfinite(fps) or
fps <= 0: return frame` at line 25. NaN fps → unchanged frame, mirroring
the existing `fps <= 0` graceful-skip design (the timer is a UX nicety,
not a correctness requirement — degrade, don't crash). Root-cause fix at
the divide site; all callers (TimerLayer only — single render entrypoint)
protected.

Contract: NaN fps must NOT crash `TimerLayer.render` with
`ValueError: cannot convert float NaN to integer`. Must return the frame
unchanged (mirror the existing `fps <= 0` skip design). Finite fps
(positive) must continue to render normally — no regression on the
valid-finite path.

RED now: observable assertions describe CORRECT behavior — NaN fps →
unchanged frame, no ValueError. They FAIL because `int(NaN // 60)` raises.
The source-check confirms the `math.isfinite` guard is present (root
cause locked).
"""

import inspect
import math

import numpy as np

from src.visualization.layers.base import LayerContext
from src.visualization.layers.timer_layer import TimerLayer


def _blank_frame(w: int = 640, h: int = 480) -> np.ndarray:
    """Create a blank black frame."""
    return np.zeros((h, w, 3), dtype=np.uint8)


# --------------------------------------------------------------------------- #
# Observable 1: TimerLayer.render(NaN fps) — no ValueError, frame unchanged.
# --------------------------------------------------------------------------- #


def test_timer_layer_nan_fps_no_crash_repro():
    """CORRECT behavior: `TimerLayer.render(frame, LayerContext(fps=NaN))`
    must return the frame unchanged, NOT raise
    `ValueError: cannot convert float NaN to integer`.

    RED now: `int(NaN // 60)` (line 29) raises ValueError. The `if fps <= 0`
    guard at line 25 does NOT catch NaN (NaN comparisons return False). After
    the fix: `if not math.isfinite(fps) or fps <= 0: return frame` → frame
    returned unchanged.
    """
    layer = TimerLayer()
    frame = _blank_frame()
    ctx = LayerContext(frame_width=640, frame_height=480, fps=math.nan, frame_idx=30)
    result = layer.render(frame, ctx)
    assert np.array_equal(result, _blank_frame()), (
        "BUG: TimerLayer.render(NaN fps) crashed. int(NaN // 60) raises "
        "ValueError; NaN fps must return the frame unchanged (mirror the "
        "existing fps<=0 skip design — degrade, don't crash)."
    )


# --------------------------------------------------------------------------- #
# Observable 2: positive-infinity fps — same graceful-skip behavior.
# --------------------------------------------------------------------------- #


def test_timer_layer_inf_fps_no_crash_repro():
    """CORRECT behavior: `TimerLayer.render(frame, LayerContext(fps=+inf))`
    must return the frame unchanged, NOT raise. `math.isfinite` rejects both
    NaN and ±inf; this test locks the broader `isfinite` semantic (not just
    `isnan`) so the guard cannot be regressed to a NaN-only check.
    """
    layer = TimerLayer()
    frame = _blank_frame()
    ctx = LayerContext(frame_width=640, frame_height=480, fps=math.inf, frame_idx=30)
    result = layer.render(frame, ctx)
    assert np.array_equal(result, _blank_frame()), (
        "BUG: TimerLayer.render(+inf fps) crashed. math.isfinite rejects both "
        "NaN and ±inf; the guard must use isfinite, not just isnan."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid finite fps still renders text on the frame.
# --------------------------------------------------------------------------- #


def test_timer_layer_valid_fps_unchanged_repro():
    """Regression guard: a valid (positive, finite) fps must still draw the
    timer text on the frame. The NaN guard must not change the valid-finite
    case. PASSES today; locks the contract.
    """
    layer = TimerLayer()
    frame = _blank_frame()
    ctx = LayerContext(frame_width=640, frame_height=480, fps=30.0, frame_idx=60)
    result = layer.render(frame, ctx)
    assert not np.array_equal(result, _blank_frame()), (
        "BUG (regression): a valid fps must still draw the timer. The NaN "
        "guard must not change the valid-finite case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — math.isfinite guard at the divide site.
# --------------------------------------------------------------------------- #


def test_timer_layer_nan_guard_source_repro():
    """GREEN contract source check: the NaN-fps crash is fixed by a
    `math.isfinite(fps)` guard at the divide site in `TimerLayer.render`
    (before `elapsed = frame_idx / fps`), returning the frame unchanged
    on NaN — mirroring the existing `fps <= 0` skip design. Root-cause fix;
    all callers (TimerLayer only) protected.
    """
    src = inspect.getsource(TimerLayer.render)
    assert "isfinite" in src, (
        "BUG: TimerLayer.render must guard `if not math.isfinite(fps) or "
        "fps <= 0: return frame` (line 25) before `elapsed = frame_idx / fps` "
        "(line 28). NaN fps → 30/NaN=NaN → int(NaN // 60) ValueError. Mirror "
        "the existing fps<=0 graceful-skip design — degrade, don't crash."
    )
