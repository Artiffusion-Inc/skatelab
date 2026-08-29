"""RED repro — `select_person_crop` (utils/video.py:173, 174, 177, 178)
crashes with uncaught `ValueError("cannot convert float NaN to integer")`
when bbox coords or padding is NaN.

```python
crop_w = int(bbox.width * (1 + 2 * padding))   # line 173 — bbox.width may be NaN
crop_h = int(bbox.height * (1 + 2 * padding))  # line 174 — bbox.height may be NaN
x1 = int(bbox.center_x - crop_w / 2)           # line 177 — bbox.center_x may be NaN
y1 = int(bbox.center_y - crop_h / 2)           # line 178 — bbox.center_y may be NaN
```

`BoundingBox` is a frozen dataclass — `width = x2 - x1`, `center_x = (x1 + x2) / 2`.
If any of x1/y1/x2/y2 is NaN, the derived width/height/center propagate NaN
into the `int(...)` call sites with no `math.isfinite` / `np.isfinite` guard.
`int(float('nan'))` raises the stdlib `ValueError("cannot convert float NaN to
integer")` — undocumented, no hint that the cause is non-finite bbox coords.

Sister bug to #1041 (`get_video_meta` CAP_PROP_FRAME_* NaN crash, fixed
2026-04). Same pattern: trust-boundary input passes NaN through arithmetic
into unguarded `int()`. Fix (NOT applied — repro only): guard each of the
4 `int(...)` call sites (or, equivalently, the bbox-derived values) with
`math.isfinite` so the function either returns the input frame unchanged
(graceful no-op) or raises a typed exception — matching the philosophy of
the `crop_w <= 0` / `x2 > w` fallback paths already in the function.

Contract: `select_person_crop` with non-finite bbox coords or padding must
NEVER crash with the undocumented stdlib `ValueError("cannot convert float
NaN to integer")`. Valid finite bboxes (the common case) must pass through
unchanged — the regression test.

Pure-Python: numpy + BoundingBox dataclass — no real video, no GPU, no DB.
"""

import inspect
import math

import numpy as np

from src.types import BoundingBox
from src.utils.video import select_person_crop

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _frame(h: int = 100, w: int = 100) -> np.ndarray:
    """Synthetic BGR frame (zeros, HxWx3) — content is irrelevant for crash
    mechanics, only shape matters for the clamping logic."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def _finite_bbox() -> BoundingBox:
    """A valid finite BoundingBox centered in a 100x100 frame. Baseline."""
    return BoundingBox(x1=40.0, y1=40.0, x2=60.0, y2=60.0, confidence=0.9)


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded int(...) sites on NaN-prone
# bbox.width / height / center_x / center_y.
# --------------------------------------------------------------------------- #


def test_select_person_crop_source_has_no_nan_guard():
    """Root cause locked: `select_person_crop` (utils/video.py:173-178)
    calls `int(bbox.width * ...)` / `int(bbox.height * ...)` /
    `int(bbox.center_x - ...)` / `int(bbox.center_y - ...)` with NO
    `math.isfinite` / `np.isfinite` / `np.isnan` / `math.isnan` /
    `np.nan_to_num` guard. After the fix, the guard MUST appear so
    `int(NaN)` cannot propagate to the stdlib `int()` call."""
    src = inspect.getsource(select_person_crop)
    has_guard = (
        "math.isfinite" in src
        or "np.isfinite" in src
        or "math.isnan" in src
        or "np.isnan" in src
        or "np.nan_to_num" in src
    )
    assert has_guard, (
        "BUG: select_person_crop (utils/video.py:173-178) calls int(...) "
        "on bbox.width / height / center_x / center_y with no finite guard. "
        "int(NaN) raises ValueError. Add a math.isfinite guard before the "
        "int() calls (e.g. early-return the input frame on non-finite bbox "
        "or padding, matching the `crop_w <= 0` fallback at line 188)."
    )


# --------------------------------------------------------------------------- #
# Observable 1: locks the crash mechanism independently of the function.
# --------------------------------------------------------------------------- #


def test_int_nan_raises_valueerror():
    """Locks the crash mechanism independently of select_person_crop:
    `int(float('nan'))` raises ValueError. This is what propagates out of
    select_person_crop on non-finite bbox — the stdlib error, not a typed
    exception naming the corrupt field. Passes today (Python stdlib
    contract); exists to document the mechanism the fix must interrupt.
    """
    try:
        int(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError(
            "int(float('nan')) did not raise ValueError — Python stdlib "
            "contract changed? Re-check the assertion below."
        )


# --------------------------------------------------------------------------- #
# Observable 2: NaN bbox x1 → derived center_x/width/height are NaN →
# int(NaN) ValueError escapes from select_person_crop.
# --------------------------------------------------------------------------- #


def test_nan_bbox_x1_does_not_crash_with_undocumented_valueerror():
    """Contract: NaN bbox.x1 must NOT crash with the undocumented stdlib
    `ValueError("cannot convert float NaN to integer")` that has no hint
    the cause is non-finite bbox coords. The fix produces a clean signal —
    either the input frame returned unchanged (graceful no-op) or a typed
    exception.

    RED before fix: stdlib ValueError ("cannot convert float NaN to
    integer") escapes — undocumented. GREEN after fix: returns the input
    frame (or typed exception) without the stdlib ValueError.
    """
    frame = _frame()
    nan_bbox = BoundingBox(x1=float("nan"), y1=40.0, x2=60.0, y2=60.0, confidence=0.9)
    try:
        result = select_person_crop(frame, nan_bbox)
    except ValueError as e:
        msg = str(e)
        # RED branch: stdlib int(NaN) ValueError leaks. The fix must
        # replace this with a clean signal (return frame or typed exception).
        assert "cannot convert float NaN to integer" not in msg, (
            f"BUG: select_person_crop raised undocumented stdlib "
            f"ValueError ({msg!r}) on NaN bbox.x1. The fix must return "
            f"the input frame unchanged (graceful no-op) or raise a "
            f"typed exception — not the stdlib `cannot convert float "
            f"NaN to integer` which gives no hint the cause is non-"
            f"finite bbox coords."
        )
        # If it's a different ValueError, re-raise — that's an unrelated bug.
        raise
    else:
        # GREEN branch: fix returns the input frame unchanged.
        assert result is frame, (
            f"BUG: select_person_crop returned a crop ({result.shape}) "
            f"for a NaN bbox — must return the input frame unchanged."
        )


# --------------------------------------------------------------------------- #
# Observable 3: NaN bbox y1 → derived center_y/height are NaN → int(NaN).
# --------------------------------------------------------------------------- #


def test_nan_bbox_y1_does_not_crash_with_undocumented_valueerror():
    """Contract: NaN bbox.y1 must NOT crash with stdlib int(NaN) ValueError.
    See `test_nan_bbox_x1_...` for the same pattern on the y-axis.

    RED before fix: stdlib ValueError leaks. GREEN after fix: returns the
    input frame unchanged.
    """
    frame = _frame()
    nan_bbox = BoundingBox(x1=40.0, y1=float("nan"), x2=60.0, y2=60.0, confidence=0.9)
    try:
        result = select_person_crop(frame, nan_bbox)
    except ValueError as e:
        msg = str(e)
        assert "cannot convert float NaN to integer" not in msg, (
            f"BUG: select_person_crop raised undocumented stdlib "
            f"ValueError ({msg!r}) on NaN bbox.y1."
        )
        raise
    else:
        assert result is frame, (
            f"BUG: select_person_crop returned a crop ({result.shape}) "
            f"for a NaN bbox.y1 — must return the input frame unchanged."
        )


# --------------------------------------------------------------------------- #
# Observable 4: NaN padding → crop_w / crop_h become NaN → int(NaN) on
# lines 173/174.
# --------------------------------------------------------------------------- #


def test_nan_padding_does_not_crash_with_undocumented_valueerror():
    """Contract: NaN padding (the third positional arg, default 0.2) must
    NOT crash with stdlib int(NaN) ValueError. `bbox.width * (1 + 2 * NaN)`
    = NaN, then `int(NaN)` on line 173/174 raises ValueError.

    RED before fix: stdlib ValueError leaks. GREEN after fix: returns the
    input frame unchanged.
    """
    frame = _frame()
    bbox = _finite_bbox()
    try:
        result = select_person_crop(frame, bbox, padding=float("nan"))
    except ValueError as e:
        msg = str(e)
        assert "cannot convert float NaN to integer" not in msg, (
            f"BUG: select_person_crop raised undocumented stdlib "
            f"ValueError ({msg!r}) on NaN padding. The fix must guard "
            f"the int() calls so non-finite padding cannot propagate."
        )
        raise
    else:
        assert result is frame, (
            f"BUG: select_person_crop returned a crop ({result.shape}) "
            f"for NaN padding — must return the input frame unchanged."
        )


# --------------------------------------------------------------------------- #
# Regression guard: valid finite bbox must pass through and return a
# finite-shaped crop. The fix must NOT regress the valid path.
# --------------------------------------------------------------------------- #


def test_valid_bbox_returns_finite_crop():
    """Regression: a valid finite bbox (centered in a 100x100 frame,
    padding=0.2) must return a crop with finite shape — the int(...)
    math all the way through. Locks the post-fix contract on the
    happy path so the guard doesn't accidentally over-fire."""
    frame = _frame(h=100, w=100)
    bbox = _finite_bbox()  # x1=40, y1=40, x2=60, y2=60 → 20x20 center
    result = select_person_crop(frame, bbox, padding=0.2)
    # crop_w = int(20 * 1.4) = 28, crop_h = int(20 * 1.4) = 28
    assert result.shape == (28, 28, 3), (
        f"select_person_crop returned shape {result.shape}, expected "
        f"(28, 28, 3) for a 20x20 bbox with padding=0.2."
    )
    assert np.isfinite(result).all(), "select_person_crop produced non-finite values in the crop."
