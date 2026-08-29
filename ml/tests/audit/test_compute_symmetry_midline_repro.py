"""Repro tests — compute_symmetry mirrors across x=0, not body midline (#852).

``compute_symmetry`` (metrics.py:1438) mirrors the left joints through the
world Y-axis (``mirrored_left[:, 0] = -left_joints[:, 0]``, i.e. x → -x about
x=0). That is only the body midline when the skater is centered on x=0. A body
that is bilaterally symmetric but translated/tilted — the common case — reads
as asymmetric because the mirror axis is wrong.

Consequences:
  - Symmetric-but-translated pose (midline at x=0.5, not 0) → symmetry < 1.
  - The fix mirrors each joint through the per-frame midline
    (``2*midline - left``), which is translation-invariant.

Tests:
  - observable: symmetric body translated to x=0.5 → symmetry ≈ 1.0
    (RED: ~0.0 because mirroring about x=0 doubles the offset).
  - observable: symmetric body tilted (both sides rotated same angle) →
    symmetry ≈ 1.0 (RED: < 1).
  - source-asserting: the mirror uses the per-frame midline, not x=0.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import ElementPhase, NormalizedPose


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(get_element_def("waltz_jump"))


def _symmetric_poses_translated() -> NormalizedPose:
    """Bilaterally symmetric body, midline at x=0.5 (not 0).

    Central joints (hip center, spine, thorax, neck) sit on x=0.5; every L/R
    pair is symmetric about x=0.5. Mirroring through x=0 (the bug) puts the
    mirrored left at x = -(0.5 - d), far from R at 0.5 + d → huge distance.
    """
    n = 2
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    from src.pose_estimation.h36m import H36Key

    mid = 0.5
    # Central structural joints define the body midline (all at x=mid).
    for central in (H36Key.HIP_CENTER, H36Key.SPINE, H36Key.THORAX, H36Key.NECK, H36Key.HEAD):
        poses[:, central, 0] = mid
        poses[:, central, 1] = 0.5

    for left_idx, right_idx in [
        (H36Key.LSHOULDER, H36Key.RSHOULDER),
        (H36Key.LELBOW, H36Key.RELBOW),
        (H36Key.LHIP, H36Key.RHIP),
        (H36Key.LKNEE, H36Key.RKNEE),
    ]:
        d = 0.1
        poses[:, left_idx, 0] = mid - d
        poses[:, right_idx, 0] = mid + d
        poses[:, left_idx, 1] = 0.5
        poses[:, right_idx, 1] = 0.5
    return poses  # type: ignore[return-value]


def _symmetric_poses_tilted(shift: float = 0.30) -> NormalizedPose:
    """Bilaterally symmetric body rigidly shifted along x by ``shift``.

    Per #852: a sideways body lean (Ina Bauer / spiral tilt / landing check)
    modeled as a rigid x-shift of an otherwise perfectly symmetric pose. Zero
    anatomical asymmetry, but the world-frame midline moves off x=0.
    """
    n = 2
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    from src.pose_estimation.h36m import H36Key

    # Central structural joints define the body midline, shifted to x=shift.
    for central in (H36Key.HIP_CENTER, H36Key.SPINE, H36Key.THORAX, H36Key.NECK, H36Key.HEAD):
        poses[:, central, 0] = shift
        poses[:, central, 1] = 0.5

    for left_idx, right_idx in [
        (H36Key.LSHOULDER, H36Key.RSHOULDER),
        (H36Key.LELBOW, H36Key.RELBOW),
        (H36Key.LHIP, H36Key.RHIP),
        (H36Key.LKNEE, H36Key.RKNEE),
    ]:
        d = 0.1
        poses[:, left_idx, 0] = shift - d
        poses[:, right_idx, 0] = shift + d
        poses[:, left_idx, 1] = 0.5
        poses[:, right_idx, 1] = 0.5
    return poses  # type: ignore[return-value]


def _phase(poses: NormalizedPose) -> ElementPhase:
    return ElementPhase(name="test", start=0, takeoff=0, peak=0, landing=0, end=len(poses))


def test_symmetric_translated_body_is_perfect_symmetry_repro():
    """#852: a symmetric body translated to x=0.5 → symmetry ≈ 1.0.

    RED without the fix: mirror about x=0 → distance ≈ 1.0 → symmetry ≈ 0.
    """
    analyzer = _analyzer()
    poses = _symmetric_poses_translated()
    score = analyzer.compute_symmetry(poses, _phase(poses))
    assert score > 0.95, (
        f"#852 RED: symmetric body translated to midline x=0.5 → symmetry={score} — "
        "mirroring about x=0 (not the body midline) reads a symmetric pose as asymmetric."
    )


def test_symmetric_tilted_body_is_perfect_symmetry_repro():
    """#852: a symmetric body rigidly tilted (x-shifted) by 0.30 → symmetry ≈ 1.0.

    RED without the fix: mirror about x=0 → symmetry ≈ 0.40 (per #852 repro).
    """
    analyzer = _analyzer()
    poses = _symmetric_poses_tilted(shift=0.30)
    score = analyzer.compute_symmetry(poses, _phase(poses))
    assert score > 0.95, (
        f"#852 RED: symmetric tilted body (shift=0.30) → symmetry={score} — "
        "mirroring about x=0 (not the per-frame midline) reads a tilted symmetric "
        "pose as asymmetric (expected ~0.40 on the bug, ~1.0 after the fix)."
    )


def test_symmetry_invariant_to_tilt_amount_repro():
    """#852: symmetry must NOT depend on the world-frame tilt amount.

    A symmetric body shifted by 0.0, 0.15, 0.30 must all score the same ≈1.0.
    RED without the fix: score falls as shift grows (0.0→1.0, 0.30→~0.40).
    """
    analyzer = _analyzer()
    scores = []
    for shift in (0.0, 0.15, 0.30):
        poses = _symmetric_poses_tilted(shift=shift)
        scores.append(analyzer.compute_symmetry(poses, _phase(poses)))
    spread = max(scores) - min(scores)
    assert spread < 0.05, (
        f"#852 RED: symmetry varies with tilt {scores} (spread={spread}) — "
        "score depends on world-frame position, not anatomical asymmetry."
    )
    assert min(scores) > 0.95, f"#852: lowest score {min(scores)} below 1.0 for symmetric pose."


def test_source_uses_midline_mirror_repro():
    """#852 GREEN: mirror must use the per-frame midline, not the world x=0."""
    src = inspect.getsource(BiomechanicsAnalyzer.compute_symmetry)
    # The bug mirrors through x=0 with a unary negation of the x column.
    # The fix derives the midline from the L/R joints and mirrors through it.
    assert "-left_joints[:, 0]" not in src, (
        "#852: still mirroring left through x=0 (unary negation). Mirror through "
        "the per-frame midline: midline = (left + right) / 2; mirrored = 2*midline - left."
    )
