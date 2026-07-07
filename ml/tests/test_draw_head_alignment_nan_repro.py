"""Repro / contract test for issue #1090 — `VerticalAxisLayer._draw_head_alignment`
crashes on NaN inputs and silently max-rewards.

`VerticalAxisLayer._draw_head_alignment` reads `head_pt`, `hip`, and
`spine_vector` and:
  1. computes `t = float(np.dot(head_pt - hip, spine_vector) / spine_len_sq)`;
     a NaN in any of those operands gives `t = NaN`.
  2. clamps `t = max(0.0, min(1.0, t))` — Python's `min(1.0, NaN) = 1.0`
     (first-arg wins), so a NaN `t` is silently promoted to `t = 1.0`
     (max projection onto spine, NaN rewarded).
  3. projects: `projection = hip + t * spine_vector` (finite when hip/spine
     are valid, NaN when any input is NaN).
  4. converts to ints: `hx, hy = int(head_pt[0]), int(head_pt[1])` and
     `px, py = int(projection[0]), int(projection[1])` — `int(float('nan'))`
     raises `ValueError: cannot convert float NaN to integer`.

Two failure modes (root cause: NO `math.isfinite` guard in the function):
  1. CRASH: NaN head/hip/spine_vector → `int(nan)` → `ValueError`. The whole
     `render` call aborts.
  2. SILENT MAX-REWARD: NaN `t` (from any NaN input) → `min(1.0, NaN) = 1.0`
     → `t = 1.0` → `projection = hip + 1.0 * spine_vector = shoulder` (the
     far end). The line is drawn from a phantom point to the shoulder.

The fix (NOT applied — repro only): a `math.isfinite` guard on
`head_pt`/`hip`/`shoulder` in `_draw_head_alignment` that returns early on
any non-finite input. Defense-in-depth: even if `render`'s `required_keys`
guard is bypassed (direct call, future refactor), the function is safe.

Correct contract: `_draw_head_alignment` must NOT crash on any NaN input and
must NOT silently max-reward a NaN `t`. It must return early when any
input is non-finite.

The function is pure-Python + cv2 (no GPU, no DB). Tests pass a numpy frame
and synthetic numpy inputs.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import numpy as np

from src.visualization.layers.vertical_axis_layer import VerticalAxisLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _frame(w: int = 640, h: int = 480) -> NDArray[np.uint8]:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _valid_hip() -> np.ndarray:
    return np.asarray([225.0, 350.0], dtype=np.float64)


def _valid_shoulder() -> np.ndarray:
    return np.asarray([225.0, 200.0], dtype=np.float64)


def _valid_head() -> np.ndarray:
    # Far enough from spine to exceed the 3px offset threshold.
    return np.asarray([400.0, 100.0], dtype=np.float64)


def _valid_spine() -> np.ndarray:
    return _valid_shoulder()[:2] - _valid_hip()[:2]


# --------------------------------------------------------------------------- #
# 1. NaN head_pt: must not crash, must not silently max-reward.
# --------------------------------------------------------------------------- #


def test_nan_head_does_not_crash():
    """A NaN head_pt must NOT crash `_draw_head_alignment` with
    `ValueError: cannot convert float NaN to integer`. The fix is a
    `math.isfinite` guard on `head_pt` that returns early.
    """
    layer = VerticalAxisLayer()
    frame = _frame()
    layer._draw_head_alignment(
        frame,
        _valid_hip(),
        _valid_shoulder(),
        np.asarray([np.nan, np.nan]),
        _valid_spine(),
    )


def test_nan_head_does_not_silently_max_reward():
    """A NaN head_pt must NOT cause `_draw_head_alignment` to draw a
    head-alignment indicator line at `t = 1.0` (max projection onto
    spine, the silent max-reward bug). The `min(1.0, NaN) = 1.0` arg-order
    trap (issue #454) silently promotes NaN `t` to the clamped value 1.0
    — the projection lands at the shoulder, and the line is drawn from a
    phantom point. A correct guard returns early instead.
    """
    layer = VerticalAxisLayer()
    frame = _frame()
    head_color = (180, 130, 255)  # the head-alignment indicator color (line 310)

    import src.visualization.layers.vertical_axis_layer as mod

    drawn_colors: list[tuple[int, int, int]] = []
    orig_line = mod.cv2.line

    def spy(img, p1, p2, color, thickness=None, *a: Any, **k: Any) -> Any:
        drawn_colors.append(tuple(color))  # type: ignore[arg-type]
        th = thickness if thickness is not None else 1
        return orig_line(img, p1, p2, color, th, *a, **k)

    mod.cv2.line = spy  # type: ignore[assignment]
    try:
        layer._draw_head_alignment(
            frame,
            _valid_hip(),
            _valid_shoulder(),
            np.asarray([np.nan, np.nan]),
            _valid_spine(),
        )
    finally:
        mod.cv2.line = orig_line

    n_head_lines = sum(1 for c in drawn_colors if c == head_color)
    assert n_head_lines == 0, (
        f"_draw_head_alignment drew {n_head_lines} head-alignment line(s) "
        f"for a NaN head_pt. The `min(1.0, NaN) = 1.0` arg-order trap "
        f"(issue #454) silently max-rewards NaN t to t=1.0 (projection "
        f"lands at the shoulder) and the line is drawn from a phantom "
        f"point — a silent wrong output, not a crash. The function must "
        f"return early on non-finite head_pt."
    )


# --------------------------------------------------------------------------- #
# 2. NaN shoulder_pt: must not crash (shoulder → spine_vector NaN).
# --------------------------------------------------------------------------- #


def test_nan_shoulder_does_not_crash():
    """A NaN shoulder_pt in pixel coords implies a NaN spine_vector
    (`spine_vector = mid_shoulder - mid_hip` at the caller). The function
    must NOT crash. `spine_len_sq = nan`, the LENGTH guard
    (`nan < 1.0` is False) is bypassed, `t = nan`, `min(1.0, NaN) = 1.0`,
    `projection = hip + 1.0 * nan = nan`, `int(nan)` raises ValueError.
    """
    layer = VerticalAxisLayer()
    frame = _frame()
    nan_shoulder = np.asarray([np.nan, np.nan], dtype=np.float64)
    # spine_vector must be consistent with mid_shoulder - mid_hip.
    nan_spine = nan_shoulder[:2] - _valid_hip()[:2]
    layer._draw_head_alignment(
        frame,
        _valid_hip(),
        nan_shoulder,
        _valid_head(),
        nan_spine,
    )


# --------------------------------------------------------------------------- #
# 3. NaN hip_pt: must not crash.
# --------------------------------------------------------------------------- #


def test_nan_hip_does_not_crash():
    """A NaN hip_pt must NOT crash `_draw_head_alignment`. `projection = hip
    + t * spine_vector` is NaN, then `int(nan)` raises ValueError.
    """
    layer = VerticalAxisLayer()
    frame = _frame()
    layer._draw_head_alignment(
        frame,
        np.asarray([np.nan, np.nan]),
        _valid_shoulder(),
        _valid_head(),
        _valid_spine(),
    )


# --------------------------------------------------------------------------- #
# 4. NaN spine_vector: must not crash.
# --------------------------------------------------------------------------- #


def test_nan_spine_vector_does_not_crash():
    """A NaN spine_vector must NOT crash `_draw_head_alignment`.
    `spine_len_sq = float(np.dot(spine_vector, spine_vector))` is NaN, the
    `spine_len_sq < 1.0` guard is `nan < 1.0 == False` (no skip),
    `t = ... / NaN = NaN`, then `int(nan)` raises ValueError.
    """
    layer = VerticalAxisLayer()
    frame = _frame()
    layer._draw_head_alignment(
        frame,
        _valid_hip(),
        _valid_shoulder(),
        _valid_head(),
        np.asarray([np.nan, np.nan]),
    )


# --------------------------------------------------------------------------- #
# 5. Valid finite regression: the indicator is still drawn.
# --------------------------------------------------------------------------- #


def test_valid_finite_still_draws_indicator():
    """Regression guard: a valid finite head/hip/shoulder/spine with a
    head offset > 3.0 from the spine must still draw the head-alignment
    indicator. The fix must not suppress the valid case.
    """
    layer = VerticalAxisLayer()
    frame = _frame()
    head_color = (180, 130, 255)  # the head-alignment indicator color

    import src.visualization.layers.vertical_axis_layer as mod

    drawn_colors: list[tuple[int, int, int]] = []
    orig_line = mod.cv2.line

    def spy(img, p1, p2, color, thickness=None, *a: Any, **k: Any) -> Any:
        drawn_colors.append(tuple(color))  # type: ignore[arg-type]
        th = thickness if thickness is not None else 1
        return orig_line(img, p1, p2, color, th, *a, **k)

    mod.cv2.line = spy  # type: ignore[assignment]
    try:
        layer._draw_head_alignment(
            frame,
            _valid_hip(),
            _valid_shoulder(),
            _valid_head(),
            _valid_spine(),
        )
    finally:
        mod.cv2.line = orig_line

    n_head_lines = sum(1 for c in drawn_colors if c == head_color)
    assert n_head_lines == 1, (
        f"_draw_head_alignment drew {n_head_lines} head-alignment line(s) "
        f"for a valid finite pose (offset > 3.0); expected exactly 1. "
        f"The NaN guard must not suppress the valid case."
    )


# --------------------------------------------------------------------------- #
# 6. Source check: isfinite guard is present in _draw_head_alignment.
# --------------------------------------------------------------------------- #


def test_draw_head_alignment_has_isfinite_guard_source():
    """Source check: `_draw_head_alignment` must guard its inputs with a
    `math.isfinite` (or equivalent `np.isfinite` / `not isnan`) check on
    `head_pt`, `hip`, and `shoulder` — and return early on any non-finite
    input. Without the guard, a NaN input causes either `int(nan)` to
    raise ValueError (crash) or `min(1.0, NaN) = 1.0` to silently max-reward
    the projection (silent wrong output).
    """
    head_src = inspect.getsource(VerticalAxisLayer._draw_head_alignment)

    # The guard must check all three points: head_pt, hip, shoulder.
    has_isfinite = "math.isfinite" in head_src or "np.isfinite" in head_src
    assert has_isfinite, (
        "_draw_head_alignment must guard head_pt, hip, and shoulder with "
        "a `math.isfinite` (or `np.isfinite`) check and return early on "
        "any non-finite input. Without it, NaN inputs cause int(nan) "
        "ValueError crashes and `min(1.0, NaN) = 1.0` silent max-reward "
        "of the projection parameter t. Issue #1090."
    )
    # The guard must skip the frame (`return`) — not silently fix.
    assert "return" in head_src, (
        "_draw_head_alignment must `return` early on non-finite inputs "
        "(skip the head-alignment indicator for the corrupted frame)."
    )
