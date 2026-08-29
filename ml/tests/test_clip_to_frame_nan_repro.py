"""RED repro — `clip_to_frame` NaN-coord silently coerces to frame corner
(tranche GC).

Bug: ml/src/visualization/core/geometry.py:367-369 `clip_to_frame` has

    x_clipped = max(margin, min(width - margin, x))
    y_clipped = max(margin, min(height - margin, y))

NaN is silently coerced to a frame corner via Python's NaN-arg-order
behavior in `min`/`max`:

    NaN x → min(w-m, NaN) = w-m → max(m, w-m) = w-m  → right edge
    NaN y → min(h-m, NaN) = h-m → max(m, h-m) = h-m  → bottom edge
    NaN both → (w-m, h-m)                                → bottom-right

All three cases are INDISTINGUISHABLE from a legitimate out-of-frame
position (e.g. (2000, 2000) on a 1920x1080 frame also yields
(width-margin, height-margin)).

Concretely (on 1920x1080 frame, margin=10):
    clip_to_frame((100,  200),  1920, 1080, 10)  → (100,  200)   (valid)
    clip_to_frame((NaN,  200),  1920, 1080, 10)  → (1910, 200)   (BUG: right edge)
    clip_to_frame((100,  NaN),  1920, 1080, 10)  → (100,  1070)  (BUG: bottom edge)
    clip_to_frame((NaN,  NaN),  1920, 1080, 10)  → (1910, 1070)  (BUG: corner)
    clip_to_frame((2000, 2000), 1920, 1080, 10)  → (1910, 1070)  (valid, same as NaN)

Prod impact: NaN keypoint (undetected joint, gap-filler failure, 3D
lift failure) silently appears as a real joint at the frame corner.
HUD overlays anchor to the corner. 3D export uses the corner as the
joint position. The user cannot distinguish "missing data" from
"real joint at the corner" — exactly the same observable as a
legitimate out-of-frame point.

Fix (NOT applied — repro only): guard x and y with
`math.isfinite(x) and math.isfinite(y)` at function entry and raise
`ValueError` so the upstream bug surfaces at the trust boundary.

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — finite coords → finite clipped output)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `clip_to_frame` is a pure-Python utility.
We feed synthetic NaN/finite coordinates to isolate the silent corner
coerce.
"""

from __future__ import annotations

import inspect
import math

import pytest

from src.visualization.core.geometry import clip_to_frame

# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_clip_to_frame_has_isfinite_guard_on_xy():
    """GREEN contract source check: `clip_to_frame` guards x and y with
    `math.isfinite` at function entry. The unfixed function uses
    `max(margin, min(width - margin, x))` which is NaN-blind
    (min(w-m, NaN) returns w-m via Python's first-arg-wins semantics,
    so NaN x silently lands on the right edge).
    """
    src = inspect.getsource(clip_to_frame)

    # The root-cause NaN-blind min/max must be GONE on fix. The
    # unfixed function has `max(margin, min(width - margin, x))`
    # and the matching y line. After the fix, the function must
    # explicitly call `math.isfinite` on x and y and raise on
    # non-finite input.
    assert "math.isfinite" in src, (
        "clip_to_frame has no `math.isfinite` guard — NaN x/y silently "
        "coerces to frame corner. Add `if not (math.isfinite(x) and "
        "math.isfinite(y)): raise ValueError(...)` at function entry."
    )


# =============================================================================
# Observables — BUG present → PASS; fix flips these to FAIL (RED contract).
# =============================================================================


def test_clip_to_frame_nan_x_raises_value_error():
    """NaN x must raise — the unfixed function silently returns the
    right edge (width - margin) because `min(w-m, NaN)` returns w-m
    via Python's NaN-arg-order semantics. Both behaviors are
    indistinguishable downstream, which is the bug.
    """
    with pytest.raises(ValueError, match="finite"):
        clip_to_frame((math.nan, 200.0), 1920, 1080, 10)


def test_clip_to_frame_nan_y_raises_value_error():
    """NaN y must raise — the unfixed function silently returns the
    bottom edge (height - margin). Same arg-order trap.
    """
    with pytest.raises(ValueError, match="finite"):
        clip_to_frame((100.0, math.nan), 1920, 1080, 10)


def test_clip_to_frame_nan_both_raises_value_error():
    """NaN x AND y must raise — unfixed function silently returns
    the bottom-right corner (width-margin, height-margin), which
    is exactly the same result as a legitimate out-of-frame point.
    """
    with pytest.raises(ValueError, match="finite"):
        clip_to_frame((math.nan, math.nan), 1920, 1080, 10)


# =============================================================================
# Regression — valid finite coords must still clip correctly.
# =============================================================================


def test_clip_to_frame_valid_finite_clamps_to_frame():
    """Regression: finite coordinates clip correctly and unchanged
    behavior. Inside-frame → unchanged; outside-frame → clamped to
    margin / (width - margin, height - margin). Float x/y supported
    (current signature accepts Position2D = tuple[float, float]).
    """
    # Inside frame, no clipping
    assert clip_to_frame((100.0, 200.0), 1920, 1080, 10) == (100.0, 200.0)
    # Outside frame on the right / bottom → clamped to width/height - margin
    assert clip_to_frame((2000.0, 2000.0), 1920, 1080, 10) == (1910.0, 1070.0)
    # Negative / 0 → clamped to margin
    assert clip_to_frame((-50.0, -50.0), 1920, 1080, 10) == (10.0, 10.0)
    # Exactly at frame edge (with margin) → unchanged
    assert clip_to_frame((10.0, 10.0), 1920, 1080, 10) == (10.0, 10.0)
