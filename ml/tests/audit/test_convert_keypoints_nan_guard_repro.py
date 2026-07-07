"""RED repro — FrameProcessor.convert_keypoints unguarded /w and /h poisons
normalized coords with inf/NaN/negative when frame_width or frame_height is
zero, negative, or non-finite (#1045).

`ml/src/pose_estimation/_frame_processor.py:28, 34-35` does
`w, h = float(frame_width), float(frame_height)` then `coco[:, 0] /= w;
coco[:, 1] /= h` with NO guard. NumPy returns inf on /0, sign-flips on /-1,
and propagates NaN on /NaN — silently producing garbage normalized coords
that propagate downstream into downstream metrics and DTW alignment.
Asymmetric poison (one axis inf, other finite) is the worst case because
`assert_pose_format` only validates ranges, not axis sanity.

Bug class: divide-by-zero / unguarded-float / sibling of #1036 (stale
post-resize w/h) and #1039 (np.where NaN-blind guard).

These tests MUST fail (RED) against the current code. Repros, not fixes.
After the fix, the assertions flip to GREEN (NaN/inf/negative dims raise
ValueError or are replaced with finite fallbacks; finite dims unchanged).
"""

import inspect

import numpy as np
import pytest

from src.pose_estimation._frame_processor import FrameProcessor


def _kps():
    # (1, 17, 2) pixel coords — one person, 17 COCO keypoints
    return np.array([[[100.0, 200.0]] * 17], dtype=np.float32)


def _scores():
    return np.array([[0.9] * 17], dtype=np.float32)


# ---------------------------------------------------------------------------
# Bug 1: frame_width=0 poisons normalized x with inf
# ---------------------------------------------------------------------------


def test_convert_keypoints_frame_width_zero_no_inf_poison():
    """frame_width=0 must not produce inf in normalized x coords.

    convert_keypoints at `_frame_processor.py:34` does `coco[:, 0] /= w`
    with `w = float(0) = 0.0`. NumPy `x / 0.0` returns `inf` (with a
    RuntimeWarning) — no exception, no guard. The output's x coords become
    inf and propagate silently into downstream consumers (H3.6M conversion
    → normalization → DTW alignment → metrics).

    Strict fix: raises ValueError. Lenient fix: returns finite (e.g. 0.0
    for the x axis). Either way, `np.isinf(out[:, :, 0])` must be False.
    """
    fp = FrameProcessor(output_format="normalized")
    with np.errstate(divide="raise", invalid="raise"):
        try:
            out = fp.convert_keypoints(_kps(), _scores(), frame_width=0, frame_height=1080)
        except (ValueError, FloatingPointError) as e:
            # STRICT fix: explicit ValueError is acceptable. Lock root cause.
            assert "frame_width" in str(e).lower() or "width" in str(e).lower(), (
                f"convert_keypoints raised on frame_width=0 with unexpected "
                f"message: {e!r}. #1045 prefers ValueError naming the bad "
                f"dimension."
            )
            return

    assert not np.any(np.isinf(out[:, :, 0])), (
        f"BUG 1: convert_keypoints(frame_width=0) produced inf in normalized "
        f"x coords. out[:, :, 0].max()={np.nanmax(out[:, :, 0])}. "
        f"_frame_processor.py:34 `coco[:, 0] /= w` with w=0.0 → inf. "
        f"Asymmetric poison: x is inf, y is finite. Silent — no exception, "
        f"only a RuntimeWarning. #1045 sibling of #1036 (#1036 fixed the "
        f"post-resize w/h re-read; this is the unguarded-divisor family)."
    )


# ---------------------------------------------------------------------------
# Bug 2: frame_height=0 poisons normalized y with inf (independent of x)
# ---------------------------------------------------------------------------


def test_convert_keypoints_frame_height_zero_no_inf_poison():
    """frame_height=0 must not produce inf in normalized y coords.

    Same root cause as Bug 1 but on the y axis (`coco[:, 1] /= h` at line
    35). The two-axis independence is the important contract: a fix that
    only guards w (or only h) leaves the other axis unguarded. Verifies
    the fix is applied symmetrically to both dimensions.
    """
    fp = FrameProcessor(output_format="normalized")
    with np.errstate(divide="raise", invalid="raise"):
        try:
            out = fp.convert_keypoints(_kps(), _scores(), frame_width=1920, frame_height=0)
        except (ValueError, FloatingPointError) as e:
            assert "frame_height" in str(e).lower() or "height" in str(e).lower(), (
                f"convert_keypoints raised on frame_height=0 with unexpected "
                f"message: {e!r}. #1045 prefers ValueError naming the bad "
                f"dimension."
            )
            return

    assert not np.any(np.isinf(out[:, :, 1])), (
        "BUG 2: convert_keypoints(frame_height=0) produced inf in normalized "
        "y coords. _frame_processor.py:35 `coco[:, 1] /= h` with h=0.0 → "
        "inf. Independent of x axis (line 34 with finite w is fine). "
        "Verifies the fix is symmetric on both axes."
    )


# ---------------------------------------------------------------------------
# Bug 3: negative frame_width flips sign of normalized coords (silent)
# ---------------------------------------------------------------------------


def test_convert_keypoints_frame_width_negative_no_neg_poison():
    """frame_width=-1 must not produce negative normalized coords.

    NumPy `100.0 / -1.0 = -100.0` — sign flip is silent, no exception, no
    warning. A negative `frame_width` is a caller bug (width can never be
    negative in a real frame) but the silent sign-flip produces coords
    outside the [0,1] normalized range that downstream consumers treat as
    valid. Strict fix raises ValueError; lenient fix clamps to a positive
    value. Either way, no negative normalized x in the output.
    """
    fp = FrameProcessor(output_format="normalized")
    with np.errstate(divide="raise", invalid="raise"):
        try:
            out = fp.convert_keypoints(_kps(), _scores(), frame_width=-1, frame_height=480)
        except (ValueError, FloatingPointError) as e:
            assert "frame_width" in str(e).lower() or "width" in str(e).lower(), (
                f"convert_keypoints raised on frame_width=-1 with unexpected "
                f"message: {e!r}. #1045 prefers ValueError naming the bad "
                f"dimension."
            )
            return

    assert not np.any(out[:, :, 0] < 0.0) and np.all(np.isfinite(out[:, :, 0])), (
        f"BUG 3: convert_keypoints(frame_width=-1) produced negative/inf "
        f"normalized x coords. 100.0 / -1.0 = -100.0 (silent sign-flip). "
        f"out[:, :, 0].min()={out[:, :, 0].min()}, finite={np.all(np.isfinite(out[:, :, 0]))}. "
        f"_frame_processor.py:34 `coco[:, 0] /= w` with w=-1.0 → negative "
        f"output. No exception, no warning. Downstream treats negative "
        f"normalized coords as valid and computes garbage metrics."
    )


# ---------------------------------------------------------------------------
# Bug 4: NaN frame_width poisons the entire pose with NaN
# ---------------------------------------------------------------------------


def test_convert_keypoints_frame_width_nan_no_nan_poison():
    """frame_width=NaN must not produce NaN in normalized x coords.

    NumPy `100.0 / NaN = NaN` — propagates through the whole pose. One
    NaN input → all NaN output. Same for the y axis with NaN height. This
    is the worst-case silent poison: structurally valid array (right
    shape, right dtype), every value is NaN, no exception, no warning.
    """
    fp = FrameProcessor(output_format="normalized")
    with np.errstate(divide="raise", invalid="raise"):
        try:
            out = fp.convert_keypoints(_kps(), _scores(), frame_width=np.nan, frame_height=720)
        except (ValueError, FloatingPointError) as e:
            assert (
                "frame_width" in str(e).lower()
                or "width" in str(e).lower()
                or "nan" in str(e).lower()
            ), (
                f"convert_keypoints raised on frame_width=NaN with unexpected "
                f"message: {e!r}. #1045 prefers ValueError naming the bad "
                f"dimension."
            )
            return

    assert np.all(np.isfinite(out[:, :, 0])), (
        f"BUG 4: convert_keypoints(frame_width=NaN) produced NaN in "
        f"normalized x coords. 100.0 / NaN = NaN (silent propagation). "
        f"out[:, :, 0] is all-NaN: {np.all(np.isnan(out[:, :, 0]))}. "
        f"_frame_processor.py:34 `coco[:, 0] /= w` with w=NaN → NaN. "
        f"Structurally valid output (correct shape, correct dtype) but "
        f"every value is NaN. Worst-case silent poison."
    )


# ---------------------------------------------------------------------------
# Regression: valid finite dims must remain byte-identical
# ---------------------------------------------------------------------------


def test_convert_keypoints_finite_dims_unchanged():
    """Valid finite frame_width/frame_height must produce identical output.

    Regression guard: the fix must not perturb the all-valid path. With
    frame_width=1920, frame_height=1080, keypoint (100, 200) normalizes
    to (100/1920, 200/1080) = (0.05208, 0.18519) and lands at H3.6M
    index 0 (RHIP) with a known position. If the fix accidentally
    short-circuits valid input (e.g. via a wrong clamp), this test
    catches it.
    """
    fp = FrameProcessor(output_format="normalized")
    out = fp.convert_keypoints(_kps(), _scores(), frame_width=1920, frame_height=1080)
    assert out.shape == (1, 17, 3)
    # COCO index 0 = nose, but coco_to_h36m maps to a specific H3.6M index.
    # The exact H3.6M target doesn't matter — what matters is that the
    # normalized value 100/1920 = 0.0520833... appears in the x-coords.
    assert np.any(np.isclose(out[:, :, 0], 100.0 / 1920.0, atol=1e-4)), (
        f"convert_keypoints(finite dims) output x-coords do not contain "
        f"100/1920 = {100.0 / 1920.0:.6f}. out[:, :, 0]={out[:, :, 0]}. "
        f"Fix may have broken the all-valid path."
    )
    assert np.any(np.isclose(out[:, :, 1], 200.0 / 1080.0, atol=1e-4)), (
        f"convert_keypoints(finite dims) output y-coords do not contain "
        f"200/1080 = {200.0 / 1080.0:.6f}. out[:, :, 1]={out[:, :, 1]}."
    )


# ---------------------------------------------------------------------------
# Source check: fix must use isfinite / nan_to_num guard at the trust boundary
# ---------------------------------------------------------------------------


def test_convert_keypoints_source_has_nan_or_isfinite_guard():
    """The fix must guard w, h at the trust boundary with isfinite or
    nan_to_num (mirror of #1036 / #1039 patterns).

    `inspect.getsource` on the live method is the lock. After the fix,
    the source MUST contain at least one of: `np.isfinite`, `nan_to_num`,
    or an explicit `raise ValueError`. The bare `float(frame_width)` +
    `coco[:, 0] /= w` unguarded path is the root cause and MUST be
    replaced.
    """
    src = inspect.getsource(FrameProcessor.convert_keypoints)
    has_guard = "np.isfinite" in src or "nan_to_num" in src or "isfinite(" in src
    has_raise = "raise" in src and "ValueError" in src
    assert has_guard or has_raise, (
        f"convert_keypoints source has no isfinite/nan_to_num/raise "
        f"guard. Root cause is unguarded `coco[:, 0] /= w` with "
        f"non-positive or non-finite w. Mirror #1036 (#1036 fix added a "
        f"re-read of h, w after resize; #1039 fix added isfinite-guarded "
        f"spine_length). #1045 must add an isfinite or nan_to_num guard "
        f"at the trust boundary where frame_width/frame_height enter the "
        f"function, or raise ValueError explicitly. Source:\n{src}"
    )
