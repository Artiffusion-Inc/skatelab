"""RED repro — tas.extract_segment_features crashes on a single-frame segment.

BUG (MEDIUM — empty-input crash / unhandled edge):
    ml/src/tas/classifier.py:39
        rot_speed = float(np.max(np.abs(np.gradient(angles)) * fps))
    `np.gradient` on a 1-element array raises
    `ValueError: Shape of array too small to calculate a numerical gradient`.

    Secondary: classifier.py:33
        motion_energy = float(np.mean(np.linalg.norm(diff, axis=(1, 2))))
    `diff = np.diff(poses, axis=0)` on a 1-frame segment is shape (0, 17, 2) →
    `np.linalg.norm(...)` is empty → `np.mean([])` → NaN (RuntimeWarning).

    No `T < 2` guard at the top of `extract_segment_features`.

Reachability:
    `extract_segment_features` is public (ml/src/tas/__init__.py exports it) and
    consumed by ml/src/tas/inference.py:123 inside
    `TASElementSegmenter._maybe_add_segment`:
        seg_poses = poses[start:end]            # inference.py:119
        features = extract_segment_features(seg_poses, fps)   # inference.py:123
    The duration filter at inference.py:114-117 is
        duration = (end - start) / fps
        if duration < MIN_DURATION.get(element_type, self.min_segment_duration): return None
    with MIN_DURATION = {"Jump": 0.5, "Spin": 2.0, "Step": 3.0} and default
    min_segment_duration=0.5. At fps <= 2.0 a single-frame Jump segment
    (end - start == 1) has duration 1/2 = 0.5s which is NOT < 0.5 → passes the
    filter → `extract_segment_features(ones((1,17,2)), fps=2.0)` → crash.

This test asserts the function does NOT crash on a single-frame input. It currently
raises ValueError → `assert not raised` FAILS → RED.
"""

import numpy as np
import pytest

from src.tas.classifier import extract_segment_features

_FEATURE_KEYS = ("duration", "hip_y_range", "motion_energy", "rotation_speed", "num_frames")


def test_extract_segment_features_single_frame_no_crash():
    poses = np.ones((1, 17, 2), dtype=np.float32)
    raised = False
    exc: BaseException | None = None
    try:
        feats = extract_segment_features(poses, fps=2.0)
    except (ValueError, RuntimeWarning) as e:  # noqa: B017 — bug-hunt repro
        raised = True
        exc = e
    assert not raised, (
        f"BUG #2: extract_segment_features crashes on single-frame segment: "
        f"{type(exc).__name__}: {exc}. np.gradient on 1-element array raises "
        f"ValueError; reachable via inference.py:123 on low-fps (<=2.0) video "
        f"where a 1-frame Jump passes MIN_DURATION 0.5s filter "
        f"(duration = 1/fps = 0.5s, not < 0.5)."
    )
    # If it didn't crash, assert finite features.
    for k in _FEATURE_KEYS:
        assert np.isfinite(feats[k]), f"{k} not finite for T=1: {feats[k]}"
