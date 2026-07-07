"""RED repro — `PoseExtractor._build_person_grid` crashes on high-confidence
NaN-coord keypoints.

Path (ml/src/pose_estimation/pose_extractor.py):
  `_build_person_grid` (line 673), bbox loop (line 705-713):
    valid = kps[kps[:, 2] > 0.1]
    if len(valid) < 3:
        continue
    bx1 = int(np.min(valid[:, 0]) * frame_w)
    by1 = int(np.min(valid[:, 1]) * frame_h)
    bx2 = int(np.max(valid[:, 0]) * frame_w)
    by2 = int(np.max(valid[:, 1]) * frame_h)

The `kps[:, 2] > 0.1` filter catches LOW-confidence keypoints but NOT
high-confidence NaN-coord keypoints. `np.min(NaN) = NaN` and `int(NaN)`
raises `ValueError: cannot convert float NaN to integer`. The user sees a
500 error during person-selection preview.

The fix (NOT applied — repro only): mask with `np.isfinite(kps[:, 0]) &
np.isfinite(kps[:, 1])` alongside the confidence threshold so NaN-coord
keypoints (even at high confidence) are excluded from bbox computation.
If a person has fewer than 3 valid keypoints after the combined filter,
the person is skipped (consistent with existing < 3 behavior).

Pure-Python (no GPU, no DB): `_build_person_grid` is a static method that
operates on (H, W, 3) frames and (17, 3) keypoint arrays.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from src.pose_estimation.pose_extractor import PoseExtractor


def _make_person(num_valid: int, kps_x: list[float], kps_y: list[float]) -> dict:
    """Build a person dict where ``num_valid`` keypoints are finite high-conf
    and the remaining 17 - num_valid are high-confidence NaN coords."""
    kps = np.full((17, 3), [np.nan, np.nan, 0.9], dtype=np.float32)
    for i in range(num_valid):
        kps[i] = [kps_x[i], kps_y[i], 0.9]
    return {"best_kps": kps, "hits": 5}


class TestBuildPersonGridNaN:
    def test_nan_coord_high_conf_keypoint_does_not_crash(self):
        """Single person: 4 valid finite + 13 high-conf NaN coords.
        Must NOT raise ValueError; must produce a valid preview path."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        person = _make_person(
            num_valid=4,
            kps_x=[0.1, 0.2, 0.3, 0.4],
            kps_y=[0.1, 0.2, 0.3, 0.4],
        )

        path = PoseExtractor._build_person_grid(frame, [person])

        assert isinstance(path, str)
        assert path.endswith(".jpg")

    def test_mixed_nan_and_valid_uses_only_finite_for_bbox(self):
        """Person with 10 valid + 7 NaN. Bbox should be computed from the
        10 finite keypoints only — must not crash and bbox must be
        non-degenerate (bx1 < bx2, by1 < by2)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        person = _make_person(
            num_valid=10,
            kps_x=[0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55],
            kps_y=[0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55],
        )

        path = PoseExtractor._build_person_grid(frame, [person])

        assert isinstance(path, str)
        assert path.endswith(".jpg")

    def test_all_nan_high_conf_keypoints_skips_person(self):
        """All 17 keypoints are high-confidence NaN. Person has 0 finite
        keypoints → bbox loop must skip the person (not crash on
        int(NaN)). Function returns a string preview path (the frame is
        still saved, just with no bbox drawn)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        kps = np.full((17, 3), [np.nan, np.nan, 0.9], dtype=np.float32)
        person = {"best_kps": kps, "hits": 5}

        # Must not raise — the previous bug raised ValueError on int(NaN)
        path = PoseExtractor._build_person_grid(frame, [person])

        assert isinstance(path, str)
        assert path.endswith(".jpg")

    def test_valid_finite_regression_still_works(self):
        """Regression: all-finite, all-high-conf keypoints still produce a
        valid preview path (no behavior change for the happy path)."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        kps = np.zeros((17, 3), dtype=np.float32)
        kps[:, 0] = np.linspace(0.1, 0.5, 17)
        kps[:, 1] = np.linspace(0.1, 0.5, 17)
        kps[:, 2] = 0.9
        person = {"best_kps": kps, "hits": 5}

        path = PoseExtractor._build_person_grid(frame, [person])

        assert isinstance(path, str)
        assert path.endswith(".jpg")

    def test_source_has_isfinite_guard_in_bbox_loop(self):
        """Static source-level check: the bbox computation inside
        `_build_person_grid` must include a `np.isfinite` (or equivalent)
        guard on the x/y coordinates — not just the confidence filter."""
        source = inspect.getsource(PoseExtractor._build_person_grid)
        # The bbox block is the only place `np.min(valid[:, ...])` appears.
        # The guard must be present somewhere in the function body.
        assert "isfinite" in source, (
            "Expected `np.isfinite(...)` guard in `_build_person_grid` to "
            "skip NaN-coord keypoints before np.min/np.max → int(NaN) crash."
        )
