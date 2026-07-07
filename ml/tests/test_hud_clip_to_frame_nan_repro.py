"""RED repro — `hud.layout.clip_to_frame` NaN-coord silently coerces to
top-left frame origin (tranche GH).

Bug: ml/src/visualization/hud/layout.py:359-360 `clip_to_frame` has

    x = max(0, min(x, frame_width - 1))
    y = max(0, min(y, frame_height - 1))

NaN is silently coerced to (0, 0) — top-left frame origin — via
Python's NaN-arg-order in min/max (NB: opposite direction from
`core.geometry.clip_to_frame` which clamps NaN to the opposite
corner — here `x` is the first arg to `min` so NaN propagates
through `min(NaN, ...)` and the literal `0` wins in `max(0, NaN)`):

    NaN x    → min(NaN, w-1) = NaN  (first-arg NaN propagates)
             → max(0,  NaN)  = 0    (literal 0 wins)
    NaN y    → same          → y = 0
    NaN both → (0, 0, ...)

INDISTINGUISHABLE from a legitimate (0, 0) origin. HUD / overlay
element silently anchors to the top-left, overlapping logos,
toolbars, frame counter.

Differs from `core.geometry.clip_to_frame` (tranche GC, PR #1130)
where first-arg = `width - margin` → NaN clamps to the right
edge. Different first-arg → different corner. Same root cause,
different visible symptom.

Concretely (on 1920x1080 frame, element 100x100):
    clip_to_frame(100,  200,  100, 100, 1920, 1080)  → (100, 200, 100, 100)  (valid)
    clip_to_frame(NaN,  200,  100, 100, 1920, 1080)  → (0,   200, 100, 100)  (BUG: x=0)
    clip_to_frame(100,  NaN,  100, 100, 1920, 1080)  → (100, 0,   100, 100)  (BUG: y=0)
    clip_to_frame(NaN,  NaN,  100, 100, 1920, 1080)  → (0,   0,   100, 100)  (BUG: origin)
    clip_to_frame(0,    0,    100, 100, 1920, 1080)  → (0,   0,   100, 100)  (valid, same as NaN)

Prod impact: NaN keypoint (undetected joint, gap-filler failure,
3D lift failure) silently anchors the HUD element to the top-left
frame origin. The user cannot distinguish "missing data" from
"real element at the origin".

Fix (NOT applied — repro only): guard x and y with
`math.isfinite(x) and math.isfinite(y)` at function entry and
raise `ValueError` so the upstream bug surfaces at the trust
boundary. Matches the style of `core.geometry.clip_to_frame`
(fixed in PR #1130 for #1070 — same root cause, different corner).

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — finite coords → finite clipped output)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `clip_to_frame` is a pure-Python
utility. We feed synthetic NaN/finite coordinates to isolate
the silent origin coerce.
"""

from __future__ import annotations

import inspect
import math

import pytest

from src.visualization.hud.layout import clip_to_frame

# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_hud_clip_to_frame_has_isfinite_guard_on_xy():
    """GREEN contract source check: `hud.layout.clip_to_frame` guards
    x and y with `math.isfinite` at function entry. The unfixed
    function uses `max(0, min(x, frame_width - 1))` which is
    NaN-blind (min(NaN, ...) propagates the NaN, and `max(0, NaN)`
    returns 0 via Python's first-arg-wins semantics, so NaN x
    silently lands on the left edge / top-left origin).
    """
    src = inspect.getsource(clip_to_frame)

    assert "math.isfinite" in src, (
        "hud.layout.clip_to_frame has no `math.isfinite` guard — "
        "NaN x/y silently coerces to top-left origin. Add "
        "`if not (math.isfinite(x) and math.isfinite(y)): "
        "raise ValueError(...)` at function entry."
    )


# =============================================================================
# Observables — BUG present → PASS; fix flips these to FAIL (RED contract).
# =============================================================================


def test_hud_clip_to_frame_nan_x_raises_value_error():
    """NaN x must raise — the unfixed function silently returns x=0
    because `min(NaN, frame_w-1)` propagates NaN (first-arg NaN
    wins) and `max(0, NaN)` returns 0 (literal 0 first-arg wins).
    Both behaviors are indistinguishable downstream, which is the
    bug.
    """
    with pytest.raises(ValueError, match="finite"):
        clip_to_frame(math.nan, 200, 100, 100, 1920, 1080)  # type: ignore[arg-type]


def test_hud_clip_to_frame_nan_y_raises_value_error():
    """NaN y must raise — the unfixed function silently returns y=0
    via the same arg-order trap as NaN x.
    """
    with pytest.raises(ValueError, match="finite"):
        clip_to_frame(100, math.nan, 100, 100, 1920, 1080)  # type: ignore[arg-type]


def test_hud_clip_to_frame_nan_both_raises_value_error():
    """NaN x AND y must raise — unfixed function silently returns
    (0, 0, ...) which is exactly the same result as a legitimate
    in-frame origin. Top-left anchor indistinguishable from
    missing-data.
    """
    with pytest.raises(ValueError, match="finite"):
        clip_to_frame(math.nan, math.nan, 100, 100, 1920, 1080)  # type: ignore[arg-type]


# =============================================================================
# Regression — valid finite coords must still clip correctly.
# =============================================================================


def test_hud_clip_to_frame_valid_finite_clamps_to_frame():
    """Regression: finite coordinates clip correctly and unchanged
    behavior. Inside-frame → unchanged; outside-frame → clamped to
    (0, 0) and width/height adjusted so the element fits the frame.
    """
    # Inside frame, no clipping
    assert clip_to_frame(100, 200, 100, 100, 1920, 1080) == (100, 200, 100, 100)
    # Origin — same as NaN(both) on the unfixed function, but here it's a
    # legitimate value, not a bug
    assert clip_to_frame(0, 0, 100, 100, 1920, 1080) == (0, 0, 100, 100)
    # Negative → clamped to 0
    assert clip_to_frame(-50, -50, 100, 100, 1920, 1080) == (0, 0, 100, 100)
    # Outside frame on the right / bottom → x/y clamped to (0, 0) edge
    # (NB: HUD variant does not preserve the original out-of-frame x
    # like core.geometry does — the caller's x/y is just clamped, then
    # width/height is shrunk to fit)
    assert clip_to_frame(2000, 2000, 100, 100, 1920, 1080) == (1919, 1079, 1, 1)
