"""RED repro — `ElementSegmenter._extract_segment_features`
(ml/src/analysis/element_segmenter.py:477) silently returns a WRONG
`hip_y_min_idx` when any hip-y frame is NaN.

Root cause (ml/src/analysis/element_segmenter.py:477):
    line 475:  hip_y = get_mid_hip(poses)[:, 1]               # NaN LHIP/RHIP → NaN Y
    line 477:  features["hip_y_min_idx"] = int(np.argmin(hip_y))  # NaN-bearing argmin

`np.argmin` on an array containing NaN treats NaN as the SMALLEST value
(NumPy NaN ordering) and returns the index of the FIRST NaN frame — NOT the
index of the real finite CoM peak. `int(np.argmin(...))` succeeds (no crash,
no NaN), so the wrong index is baked into the feature dict silently.

Consequence: a single occluded hip frame (common in spins/crossovers/fast
rotation, 3D-lift NaN, gap-fill miss) makes `hip_y_min_idx` point to the
occluded frame instead of the real CoM peak. The RF classifier
(`SegmentClassifier.predict`) then feeds on a misleading frame index.

The fix (NOT applied — repro only): use `np.nanargmin` guarded by an
`np.isfinite` mask (fallback to 0 when all-NaN), so the index points to the
real finite CoM peak and the all-NaN edge case returns a sentinel (0) instead
of crashing. Do NOT touch `_refine_boundaries` (sibling #972).
"""

import inspect

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key


def _make_poses(num_frames: int) -> np.ndarray:
    """Build (num_frames, 17, 2) normalized poses with a clear CoM peak."""
    poses = np.zeros((num_frames, 17, 2), dtype=np.float32)
    # Hips start low (y=0.6), peak at frame `peak` (y=0.3, lowest y = peak height),
    # then descend. `np.argmin` on hip_y returns the peak frame.
    peak = num_frames // 2
    for f in range(num_frames):
        # parabola centered at peak, amplitude 0.3
        delta = abs(f - peak)
        y = 0.6 - 0.3 * max(0.0, 1.0 - delta / max(peak, 1))
        poses[f, H36Key.LHIP] = [0.5, y]
        poses[f, H36Key.RHIP] = [0.5, y]
    return poses


def test_hip_y_min_idx_nan_frame_not_picked():
    """NaN hip on a non-peak frame must NOT become the argmin index."""
    poses = _make_poses(11).copy()
    peak = 5  # frame 5 has the lowest finite hip_y (real CoM peak)
    # NaN LHIP on frame 3 (non-peak) — `np.argmin` would return 3 (NaN wins)
    poses[3, H36Key.LHIP] = [np.nan, np.nan]
    poses[3, H36Key.RHIP] = [np.nan, np.nan]

    seg = ElementSegmenter()
    features = seg._extract_segment_features(poses, 30.0)
    idx = features["hip_y_min_idx"]

    assert idx == peak, (
        f"BUG #989: hip_y_min_idx={idx} points to NaN-frame, not real CoM peak "
        f"({peak}). np.argmin treats NaN as smallest → wrong index baked into "
        f"features silently. Expected nanargmin over finite hip_y → {peak}."
    )
    assert idx != 3, "hip_y_min_idx must NOT point to the NaN (occluded) frame."


def test_hip_y_min_idx_all_finite_unchanged():
    """All-finite input: same index as the old `np.argmin` (regression guard)."""
    poses = _make_poses(11)
    seg = ElementSegmenter()
    features = seg._extract_segment_features(poses, 30.0)
    hip_y = ((poses[:, H36Key.LHIP, :] + poses[:, H36Key.RHIP, :]) / 2)[:, 1]
    expected = int(np.argmin(hip_y))
    assert features["hip_y_min_idx"] == expected, (
        f"Regression: all-finite hip_y_min_idx={features['hip_y_min_idx']} "
        f"differs from np.argmin={expected}. The fix must not change behavior "
        f"on finite input."
    )


def test_hip_y_min_idx_all_nan_no_crash():
    """All-NaN edge case: returns a sentinel (0), no ValueError crash."""
    poses = _make_poses(11)
    poses[:, H36Key.LHIP] = [np.nan, np.nan]
    poses[:, H36Key.RHIP] = [np.nan, np.nan]

    seg = ElementSegmenter()
    raised = False
    exc: BaseException | None = None
    idx: int = -999
    try:
        features = seg._extract_segment_features(poses, 30.0)
        idx = int(features["hip_y_min_idx"])
    except (ValueError, IndexError) as e:  # noqa: B017 — bug-hunt repro
        raised = True
        exc = e
    assert not raised, (
        f"BUG #989: all-NaN hip_y raised {type(exc).__name__}: {exc}. "
        f"np.nanargmin raises ValueError on all-NaN — must be guarded with "
        f"isfinite mask + sentinel fallback (e.g. 0)."
    )
    assert idx == 0, f"all-NaN hip_y_min_idx must return sentinel 0, got {idx}."


def test_hip_y_min_idx_source_uses_nanargmin_or_isfinite():
    """Source-check: the fix uses nanargmin or isfinite mask (root-cause lock)."""
    src = inspect.getsource(ElementSegmenter._extract_segment_features)
    # The old `int(np.argmin(hip_y))` line must be replaced with a NaN-aware form.
    assert "np.argmin(hip_y)" not in src, (
        "BUG #989 not fixed: source still contains bare `np.argmin(hip_y)` — "
        "NaN-bearing argmin. Must use np.nanargmin(hip_y) guarded by isfinite "
        "(fallback to 0 on all-NaN)."
    )
    assert "nanargmin" in src or "isfinite" in src or "isnan" in src, (
        "BUG #989 not fixed: source has no NaN-aware guard (nanargmin / "
        "isfinite / isnan) for hip_y_min_idx."
    )


def test_hip_y_min_idx_does_not_touch_refine_boundaries():
    """Scope guard: this fix must NOT touch `_refine_boundaries` (sibling #972)."""
    src_refine = inspect.getsource(ElementSegmenter._refine_boundaries)
    # `_refine_boundaries` still uses its own argmin on window velocity — leave it
    # for the sibling worker. We only assert the function still exists unchanged
    # in spirit (uses np.argmin on velocity, not touched by this fix).
    assert "np.argmin" in src_refine, (
        "_refine_boundaries source unexpectedly changed — this fix must NOT "
        "touch _refine_boundaries (sibling #972 owns it)."
    )
