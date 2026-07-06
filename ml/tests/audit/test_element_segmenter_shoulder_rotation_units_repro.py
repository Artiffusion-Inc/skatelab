"""Repro tests — element_segmenter shoulder rotation units + no-unwrap (#860).

``_compute_shoulder_rotation`` (element_segmenter.py:625) returns
``np.arctan2`` angles WITHOUT ``np.unwrap``, and ``_extract_features`` (line
484-491) takes ``np.gradient(angles) * fps`` in **rad/s** — but
``_classify_by_rules`` (line 518-529) compares ``rotation_speed_max`` against
deg/s-shaped thresholds (200/350/500). Two compounding defects:

1. No unwrap — arctan2 wraps to (-π, π]; a shoulder rotation past ±π produces a
   2π-per-frame gradient spike (physically impossible), so rotation_speed_max
   reflects the wrap artifact, not the spin rate.
2. rad/s vs deg/s mismatch — a real 1080 deg/s (18.85 rad/s) jump is BELOW the
   200 rad/s threshold (11459 deg/s, ~32 spins/s, unreachable), so every real
   jump falls through to ``"unknown"`` (0.3) and is silently dropped from the
   pipeline (no takeoff/peak/landing, no metrics, no XP/PR).

Fix (#860): ``np.unwrap`` the angles, convert rad/s → deg/s (×180/π) so
rotation_speed_max is in deg/s matching the classify thresholds.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key


def _segmenter() -> ElementSegmenter:
    return ElementSegmenter()


def _jump_pose(rotations: float, n: int = 30, fps: int = 30) -> np.ndarray:
    """30 frames, fps=30, single-rotation jump. Shoulders rotate `rotations`
    full turns over the flight window (frames 10..20). Hips rise then fall
    (jump pattern). Returns H3.6M (n, 17, 2) poses."""
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    t = np.linspace(0, 2 * np.pi * rotations, n)
    # Shoulder vector rotates: real 2D rotation (both x and y change).
    poses[:, H36Key.LSHOULDER, 0] = 0.5 + 0.1 * np.cos(t)
    poses[:, H36Key.LSHOULDER, 1] = 0.5 + 0.1 * np.sin(t)
    poses[:, H36Key.RSHOULDER, 0] = 0.5 - 0.1 * np.cos(t)
    poses[:, H36Key.RSHOULDER, 1] = 0.5 - 0.1 * np.sin(t)
    # Hip Y: rise for takeoff..peak (10..15) then fall (15..20) — jump pattern.
    hip_y = np.full(n, 0.5, dtype=np.float32)
    hip_y[10:16] = 0.5 + np.linspace(0, 0.3, 6)
    hip_y[16:21] = 0.5 + np.linspace(0.3, 0, 5)
    poses[:, H36Key.LHIP, 1] = hip_y
    poses[:, H36Key.RHIP, 1] = hip_y
    return poses


def test_real_jump_not_classified_unknown_repro():
    """#860: a real 1-rotation (1080 deg/s) jump must NOT be 'unknown'."""
    seg = _segmenter()
    poses = _jump_pose(rotations=1.0)
    features = seg._extract_segment_features(poses, fps=30.0)
    element_type, _conf = seg._classify_by_rules(features)
    assert element_type != "unknown", (
        f"#860 RED: real 1-rotation jump classified as 'unknown' — "
        f"rotation_speed_max={features.get('rotation_speed_max')} (rad/s + wrap "
        "artifact) is compared against deg/s thresholds (200/350/500), so 18.85 "
        "rad/s (1080 deg/s) falls through. Missing np.unwrap + rad/s→deg/s."
    )


def test_harder_jump_not_classified_unknown_repro():
    """#860: 2-3 rotation jumps (2160–3240 deg/s) must classify as a jump type."""
    seg = _segmenter()
    for rotations in (2.0, 3.0):
        poses = _jump_pose(rotations=rotations)
        features = seg._extract_segment_features(poses, fps=30.0)
        element_type, _conf = seg._classify_by_rules(features)
        assert element_type != "unknown", (
            f"#860 RED: {rotations}-rotation jump classified 'unknown' — "
            f"rotation_speed_max={features.get('rotation_speed_max')} in rad/s "
            "(wrap-inflated) vs deg/s thresholds. Real jumps never match."
        )


def test_rotation_speed_max_in_deg_per_sec_range_repro():
    """#860: rotation_speed_max must be in deg/s (~360 for 1 rotation/sec), not
    rad/s (~6.5) nor wrap-inflated (~10800)."""
    seg = _segmenter()
    poses = _jump_pose(rotations=1.0)
    features = seg._extract_segment_features(poses, fps=30.0)
    rsm = features.get("rotation_speed_max", 0.0)
    # 1 rotation over 30 frames @ 30 fps = 360 deg/s (linspace step artifact →
    # ~372). The observable: deg/s physical range, not rad/s (~6.5, below every
    # classify threshold) nor wrap-inflated rad→deg (~10800, a 2π-per-frame
    # spike × 30 × 180/π).
    assert 200.0 < rsm < 2000.0, (
        f"#860 RED: rotation_speed_max={rsm} — must be ~360 deg/s (1 rotation "
        "@30fps). rad/s reading gives ~6.5 (<200, no match); wrap-inflated "
        "rad→deg gives ~10800 (above band). Both indicate missing unwrap / "
        "missing deg/s conversion."
    )


def test_segment_still_returns_unknown_for_no_rotation_repro():
    """#860 regression guard: a no-rotation pose still segments as 'unknown'."""
    seg = _segmenter()
    poses = _jump_pose(rotations=0.0)
    features = seg._extract_segment_features(poses, fps=30.0)
    # No shoulder rotation → rotation_speed_max ~0 → no jump match → unknown or
    # three_turn. The guard: element_type is a valid string (segmenter did not
    # crash and produced a classification).
    element_type, _conf = seg._classify_by_rules(features)
    assert isinstance(element_type, str) and element_type, "segmenter must classify."


def test_shoulder_rotation_unwrap_and_deg_s_source_repro():
    """#860 GREEN source check: _compute_shoulder_rotation unwraps angles and
    _extract_features converts rad/s → deg/s."""
    rot_src = inspect.getsource(ElementSegmenter._compute_shoulder_rotation)
    assert "np.unwrap" in rot_src, (
        "#860: _compute_shoulder_rotation must np.unwrap arctan2 angles — "
        "without unwrap a rotation past ±π produces a 2π-per-frame gradient spike."
    )
    feat_src = inspect.getsource(ElementSegmenter._extract_segment_features)
    assert "180.0 / np.pi" in feat_src or "180 / np.pi" in feat_src, (
        "#860: rotation_speed must convert rad/s → deg/s (×180/π) to match the "
        "deg/s-shaped classify thresholds (200/350/500)."
    )
