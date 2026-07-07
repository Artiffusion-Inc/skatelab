"""RED→GREEN tests — `merge_coco_foot_keypoints` face-duplicate
section (ml/src/datasets/coco_builder.py, lines 122-129) had a
NaN-blind `pts[src_idx]` copy that silently propagated corrupted
NaN coords into the face dupe slot (vis=0.0, pts=[0,0])
indistinguishable from a dupe whose source was genuinely
missing.

Root cause (ml/src/datasets/coco_builder.py:123, pre-fix):
    for dup_idx, src_idx in _FACE_DUPE_SOURCE.items():
        pts[dup_idx] = pts[src_idx]   # NaN src → silent NaN→0
        vis[dup_idx] = 0.0

Fix: `math.isfinite(pts[src_idx, 0/1])` guard raises ValueError
on NaN/inf src, surfacing the corrupted upstream data instead
of silently zeroing.

These tests assert the GREEN contract: NaN src raises, valid
finite input unchanged.

Methodology (per audit reglement):
  3 observables  (NaN src raises ValueError)
  1 regression   (valid finite input unchanged)
  1 source check (math.isfinite(pts[src_idx]) guard present)
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from src.datasets.coco_builder import (
    _FACE_DUPE_SOURCE,
    merge_coco_foot_keypoints,
)

# =========================================================================== #
# Observable 1: NaN `coco_2d[1]` (leye, src for dupe 23) raises.
# =========================================================================== #


def test_face_dup_pts_nan_leye_raises():
    """GREEN contract: NaN `coco_2d[1]` (leye, source for face
    dupe 23) must raise ValueError, not silently zero `pts[23]`.

    Pre-fix: NaN src → silent zero copy, INDISTINGUISHABLE from
    a dupe whose source is genuinely missing.
    Post-fix: `math.isfinite(pts[src_idx, 0/1])` guard raises
    ValueError, surfacing the corrupted upstream data.
    """
    coco_2d = np.ones((17, 2), dtype=np.float64) * 0.5
    foot_2d = np.ones((6, 2), dtype=np.float32) * 0.5
    coco_2d[1] = np.nan  # leye is the source for face dupe 23

    with pytest.raises(ValueError, match=r"finite"):
        merge_coco_foot_keypoints(coco_2d, foot_2d)


# =========================================================================== #
# Observable 2: NaN `coco_2d[0]` (nose, src for dupe 25) raises.
# =========================================================================== #


def test_face_dup_pts_nan_nose_raises():
    """GREEN contract: NaN `coco_2d[0]` (nose, source for face
    dupe 25) must raise ValueError.
    """
    coco_2d = np.ones((17, 2), dtype=np.float64) * 0.5
    foot_2d = np.ones((6, 2), dtype=np.float32) * 0.5
    coco_2d[0] = np.nan  # nose is the source for face dupe 25

    with pytest.raises(ValueError, match=r"finite"):
        merge_coco_foot_keypoints(coco_2d, foot_2d)


# =========================================================================== #
# Observable 3: NaN `coco_2d[2]` (reye, src for dupe 24) raises.
# =========================================================================== #


def test_face_dup_pts_nan_reye_raises():
    """GREEN contract: NaN `coco_2d[2]` (reye, source for face
    dupe 24) must raise ValueError. Exhaustive coverage of all
    three face dupe sources (1, 2, 0).
    """
    coco_2d = np.ones((17, 2), dtype=np.float64) * 0.5
    foot_2d = np.ones((6, 2), dtype=np.float32) * 0.5
    coco_2d[2] = np.nan  # reye is the source for face dupe 24

    with pytest.raises(ValueError, match=r"finite"):
        merge_coco_foot_keypoints(coco_2d, foot_2d)


# =========================================================================== #
# Regression: valid finite input must produce the standard face
# dupe behavior — coord copied from src, vis=0.0 (unlabeled per
# #806).
# =========================================================================== #


def test_face_dup_pts_valid_unchanged():
    """REGRESSION: valid finite input (all keypoints present)
    must produce face dupe coords copied from src, vis=0.0
    (COCO unlabeled per #806). The fix must not change the
    typical case.
    """
    coco_2d = np.ones((17, 2), dtype=np.float64) * 0.5
    foot_2d = np.ones((6, 2), dtype=np.float32) * 0.5

    pts, vis = merge_coco_foot_keypoints(coco_2d, foot_2d)

    for dup_idx, src_idx in _FACE_DUPE_SOURCE.items():
        np.testing.assert_array_equal(
            pts[dup_idx],
            pts[src_idx],
            err_msg=(
                f"REGRESSION: pts[dup={dup_idx}] = {pts[dup_idx]} "
                f"but pts[src={src_idx}] = {pts[src_idx]} (expected equal — "
                f"face dupe must copy src coord for valid finite input)."
            ),
        )
        # #806: dupe vis is always 0.0 (unlabeled), regardless of src vis.
        assert vis[dup_idx] == 0.0, (
            f"REGRESSION: vis[dup={dup_idx}] = {vis[dup_idx]} "
            f"(expected 0.0 per #806 — face dupe is unlabeled)."
        )


# =========================================================================== #
# Source check: root cause fixed — `math.isfinite(pts[src_idx])`
# guard present in the face dupe section.
# =========================================================================== #


def test_coco_builder_face_dup_finite_guard_source():
    """SOURCE: the face dupe section has a `math.isfinite(
    pts[src_idx, ...])` guard. Pre-fix the guard was absent and
    `pts[dup_idx] = pts[src_idx]` silently copied NaN.
    """
    src = inspect.getsource(merge_coco_foot_keypoints)

    # The face dupe copy is still present.
    assert "pts[dup_idx] = pts[src_idx]" in src, (
        "REGRESSION: `pts[dup_idx] = pts[src_idx]` copy is missing from the face dupe section."
    )

    # The fix idiom must be present.
    assert "isfinite" in src and "pts[src_idx]" in src, (
        "BUG: `math.isfinite(pts[src_idx, ...])` guard missing from "
        "merge_coco_foot_keypoints face dupe section. NaN src coords "
        "would still propagate silently into face dupe slots."
    )
