"""RED repro — `ElementSegmenter._refine_boundaries`
(ml/src/analysis/element_segmenter.py:372,387) silently snaps a segment
boundary to a NaN-poisoned frame when a hip keypoint is NaN inside the
boundary search window.

Root cause (ml/src/analysis/element_segmenter.py:356-388):
    line 356:  hip_y = get_mid_hip(poses)[:, 1]              # (LHIP+RHIP)/2
    line 357:  velocity = np.gradient(hip_y)                 # NaN hip → NaN velocity
    line 358:  velocity_mag = np.abs(velocity)               # NaN propagates
    line 372:  min_idx = np.argmin(window_vel)               # NaN-unsafe argmin
    line 387:  min_idx = np.argmin(window_vel)               # same, end boundary

`np.argmin` on an array containing NaN treats NaN as the SMALLEST value
(NumPy NaN ordering) and returns the index of the FIRST NaN frame — NOT
the index of the real finite velocity minimum. A NaN LHIP/RHIP in the
search window (occluded hip — hands cross hips, loose top, MogaNet
dropout) snaps the boundary to the NaN frame. Wrong boundary → wrong
per-element metric frame range → silently wrong biomechanics report.

Sibling to #989 (hip_y_min_idx, same file, already merged). This fix
targets ONLY `_refine_boundaries`; do NOT touch the hip_y_min_idx site
(line ~475-481).

The fix (NOT applied — repro only): replace `np.argmin(window_vel)` with
`np.nanargmin(window_vel)` guarded by `np.isfinite(window_vel).any()`
(fallback to 0 / coarse value on all-NaN). Mirror the #989 pattern
(nanargmin + isfinite guard).
"""

import inspect

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key

# Test geometry: n=42 frames, parabola peak (real velocity-zero / boundary
# frame) at frame 22. Coarse segment (20, 40) with boundary_window=10.
# Start refinement: start=20 > window=10 → search [10, 30); peak 22 is in
# window (slice idx 12), real argmin. NaN hip injected at frame 15 (slice
# idx 5) — inside the same window, NOT the real minimum frame.
N = 42
PEAK = 22
NAN_FRAME = 15
COARSE_SEG = (20, 40)


def _make_poses(num_frames: int, peak: int) -> np.ndarray:
    """Build (num_frames, 17, 2) normalized poses with a clear hip-Y
    parabola. The hip-Y minimum (real velocity-zero / boundary frame)
    is at `peak`. `np.gradient` is zero at the parabola apex."""
    poses = np.zeros((num_frames, 17, 2), dtype=np.float32)
    for f in range(num_frames):
        delta = abs(f - peak)
        y = 0.6 - 0.3 * max(0.0, 1.0 - delta / max(peak, 1))
        poses[f, H36Key.LHIP] = [0.5, y]
        poses[f, H36Key.RHIP] = [0.5, y]
    return poses


def test_refine_boundaries_nan_hip_not_snapped_to_nan_frame():
    """NaN hip on a non-boundary frame in the search window must NOT
    become the refined boundary (NaN wins np.argmin → wrong snap)."""
    poses = _make_poses(N, peak=PEAK).copy()
    # NaN LHIP+RHIP on frame 15 (inside the start-boundary window [10,30),
    # NOT the real minimum frame 22).
    poses[NAN_FRAME, H36Key.LHIP] = [np.nan, np.nan]
    poses[NAN_FRAME, H36Key.RHIP] = [np.nan, np.nan]

    seg = ElementSegmenter(boundary_window=10)
    refined = seg._refine_boundaries(poses, [COARSE_SEG])
    assert len(refined) == 1, f"expected 1 refined segment, got {len(refined)}"
    new_start, _new_end = refined[0]

    assert new_start != NAN_FRAME, (
        f"BUG #972: start boundary snapped to NaN frame {NAN_FRAME} "
        f"(NaN wins argmin), new_start={new_start}. Must use nanargmin over "
        f"finite frames → real velocity minimum at {PEAK}."
    )
    assert new_start == PEAK, (
        f"BUG #972: start boundary {new_start} != real finite velocity min "
        f"{PEAK}. nanargmin over finite hip_y must find the parabola apex."
    )


def test_refine_boundaries_all_finite_unchanged():
    """All-finite input: nanargmin == argmin (regression guard)."""
    poses = _make_poses(N, peak=PEAK)
    seg = ElementSegmenter(boundary_window=10)
    refined = seg._refine_boundaries(poses, [COARSE_SEG])
    new_start, _new_end = refined[0]

    # Compute the expected finite argmin independently over the same window.
    hip_y = ((poses[:, H36Key.LHIP, :] + poses[:, H36Key.RHIP, :]) / 2)[:, 1]
    velocity_mag = np.abs(np.gradient(hip_y))
    # Start window for segment (20,40) with window=10: [10, 30).
    expected_start = 10 + int(np.argmin(velocity_mag[10:30]))
    assert new_start == expected_start, (
        f"Regression: all-finite new_start={new_start} differs from "
        f"np.argmin={expected_start}. The fix must not change finite behavior."
    )


def test_refine_boundaries_all_nan_no_crash():
    """All-NaN hip in the search window: must not raise / crash.
    Either keep the coarse boundary (fail closed) or sentinel; no
    ValueError from np.nanargmin on all-NaN."""
    poses = _make_poses(N, peak=PEAK).copy()
    poses[:, H36Key.LHIP] = [np.nan, np.nan]
    poses[:, H36Key.RHIP] = [np.nan, np.nan]

    seg = ElementSegmenter(boundary_window=10)
    raised = False
    exc: BaseException | None = None
    refined: list[tuple[int, int]] = []
    try:
        refined = seg._refine_boundaries(poses, [COARSE_SEG])
    except (ValueError, IndexError) as e:  # noqa: B017 — bug-hunt repro
        raised = True
        exc = e
    assert not raised, (
        f"BUG #972: all-NaN hip raised {type(exc).__name__}: {exc}. "
        f"np.nanargmin raises ValueError on all-NaN — must be guarded with "
        f"isfinite + sentinel/coarse fallback."
    )
    # Fail closed: must NOT return a NaN-snapped frame; either keeps the
    # coarse boundary or returns a finite sentinel. No crash is the
    # primary contract.
    if refined:
        assert all(np.isfinite(s) and np.isfinite(e) for s, e in refined), (
            f"all-NaN edge: refined contains non-finite boundary: {refined}"
        )


def test_refine_boundaries_source_uses_nanargmin_or_isfinite():
    """Source-check: the boundary argmin site must use nanargmin or an
    isfinite mask (root-cause lock). Bare np.argmin(window_vel) is the
    bug."""
    src = inspect.getsource(ElementSegmenter._refine_boundaries)
    assert "np.argmin(window_vel)" not in src, (
        "BUG #972 not fixed: source still contains bare "
        "`np.argmin(window_vel)` — NaN-bearing argmin. Must use "
        "np.nanargmin(window_vel) guarded by isfinite (fallback on all-NaN)."
    )
    assert "nanargmin" in src or "isfinite" in src or "isnan" in src, (
        "BUG #972 not fixed: _refine_boundaries has no NaN-aware guard "
        "(nanargmin / isfinite / isnan) at the boundary-argmin site."
    )


def test_refine_boundaries_does_not_touch_hip_y_min_idx():
    """Scope guard: this fix must NOT touch the hip_y_min_idx site
    (sibling #989, already merged at line ~475-481)."""
    src_features = inspect.getsource(ElementSegmenter._extract_segment_features)
    assert "nanargmin" in src_features, (
        "Scope leak: hip_y_min_idx site (#989) lost its nanargmin guard. "
        "This fix must NOT touch _extract_segment_features."
    )
