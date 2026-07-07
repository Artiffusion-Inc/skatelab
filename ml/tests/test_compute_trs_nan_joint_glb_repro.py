"""RED repro — `_compute_trs` (ml/src/visualization/export_3d_animated.py:222-273)
builds the per-bone TRS (translation, rotation quaternion, scale) for a 3D
skeleton bone cylinder. A NaN joint coordinate (3D lift NaN on an occluded
keypoint — MotionAGFormer/TCPFormer emits NaN) propagates silently:

    bone_vec = end_pos - start_pos                  # NaN
    bone_length = np.linalg.norm(bone_vec)          # NaN
    if bone_length < 1e-6:                          # NaN < 1e-6 == False → guard BYPASSED
        return (translation, identity_quat, unit_scale)
    bone_dir = bone_vec / bone_length               # NaN / NaN = NaN
    rotation = R.align_vectors([bone_dir], [y_axis])[0]  # scipy propagates NaN
    quaternion = rotation.as_quat()                 # [nan, nan, nan, nan]
    scale = np.array([bone_radius, bone_length / 2, bone_radius])  # NaN scale

NaN < 1e-6 is False, so the degenerate-bone guard (designed for zero-length
bones) is bypassed for the strictly-worse NaN case → NaN quaternion + NaN
scale baked into the animated .glb. Sibling of the NaN-comparison family
(#971 / #972 / #973). Contract: NaN joint must NOT produce NaN quaternion or
scale in animated GLB. Root-cause fix: an `np.isfinite` guard at the entry of
`_compute_trs` (NaN joint → degenerate identity-quat unit-scale bone).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

# Add ml to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.visualization.export_3d_animated import _compute_trs


def _all_finite(arr: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(arr)))


def test_compute_trs_source_has_isfinite_nan_guard() -> None:
    """Source-check: `_compute_trs` contains an np.isfinite guard on joint
    coords (root-cause NaN guard, not a bare `< 1e-6` length check)."""
    source = inspect.getsource(_compute_trs)
    assert "np.isfinite" in source, (
        "_compute_trs must guard joint coords with np.isfinite "
        "(NaN < 1e-6 is False; length-only guard is bypassed by NaN)"
    )


def test_nan_bone_length_does_not_bypass_degenerate_guard() -> None:
    """NaN joint → bone_length NaN. `NaN < 1e-6` is False on master, bypassing
    the degenerate guard. After fix the NaN must be caught and routed to the
    degenerate path (finite identity quat + unit scale), NOT a NaN quat."""
    nan_start = np.array([np.nan, 0.0, 0.0])
    finite_end = np.array([0.0, 1.0, 0.0])
    bone_length = float(np.linalg.norm(finite_end - nan_start))
    assert np.isnan(bone_length), "prerequisite: NaN joint → NaN bone_length"
    # NaN < 1e-6 is False — the broken guard is bypassed
    assert not (bone_length < 1e-6), "prerequisite: NaN < 1e-6 is False"

    trans, quat, scale = _compute_trs(nan_start, finite_end, 0.012)
    assert _all_finite(quat), f"NaN joint must not leak NaN into quaternion: {quat}"
    assert _all_finite(scale), f"NaN joint must not leak NaN into scale: {scale}"
    assert _all_finite(trans), f"NaN joint must not leak NaN into translation: {trans}"


def test_compute_trs_nan_joint_returns_finite_quaternion_and_scale() -> None:
    """Full TRS on a NaN joint: translation, quaternion, scale must all be
    finite (no NaN). The degenerate identity-quat unit-scale bone is the
    expected fallback."""
    nan_start = np.array([np.nan, np.nan, np.nan])
    finite_end = np.array([0.0, 1.0, 0.0])
    trans, quat, scale = _compute_trs(nan_start, finite_end, 0.012)
    assert _all_finite(trans), f"translation contains NaN: {trans}"
    assert _all_finite(quat), f"quaternion contains NaN: {quat}"
    assert _all_finite(scale), f"scale contains NaN: {scale}"
    assert quat.shape == (4,), f"quaternion must be (4,), got {quat.shape}"
    assert scale.shape == (3,), f"scale must be (3,), got {scale.shape}"


def test_compute_trs_both_joints_nan_returns_finite_trs() -> None:
    """Both endpoints NaN (e.g. whole-limb occlusion): TRS must still be
    finite — degenerate identity-quat unit-scale bone."""
    nan_start = np.array([np.nan, np.nan, np.nan])
    nan_end = np.array([np.nan, np.nan, np.nan])
    trans, quat, scale = _compute_trs(nan_start, nan_end, 0.012)
    assert _all_finite(trans), f"translation contains NaN: {trans}"
    assert _all_finite(quat), f"quaternion contains NaN: {quat}"
    assert _all_finite(scale), f"scale contains NaN: {scale}"


def test_finite_bone_produces_finite_quaternion_and_scale() -> None:
    """Regression: finite joints must keep producing a finite, non-trivial
    quaternion and a scale whose Y component equals half the bone length."""
    start_pos = np.array([0.0, 0.0, 0.0])
    end_pos = np.array([0.0, 2.0, 0.0])
    bone_radius = 0.012
    trans, quat, scale = _compute_trs(start_pos, end_pos, bone_radius)
    assert _all_finite(trans), f"translation contains NaN: {trans}"
    assert _all_finite(quat), f"quaternion contains NaN: {quat}"
    assert _all_finite(scale), f"scale contains NaN: {scale}"
    # Y-aligned bone → identity quaternion [1,0,0,0]
    np.testing.assert_allclose(quat, np.array([1.0, 0.0, 0.0, 0.0]))
    np.testing.assert_allclose(scale, np.array([bone_radius, 1.0, bone_radius]))
    np.testing.assert_allclose(trans, np.array([0.0, 1.0, 0.0]))
