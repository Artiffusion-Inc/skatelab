"""RED repro — `compute_spread_eagle_angle` silently propagated NaN to
the spread-eagle angle series when a leg keypoint (LHIP/LKNEE/RHIP/RKNEE)
was NaN. Closes #1261.

Bug pattern (pre-#976 fix in metrics.py:1543-1566):

    l_leg = poses[:, H36Key.LKNEE] - poses[:, H36Key.LHIP]
    r_leg = poses[:, H36Key.RKNEE] - poses[:, H36Key.RHIP]

    dot_prod = np.sum(l_leg * r_leg, axis=-1)
    norms = (
        np.linalg.norm(l_leg, axis=-1) * np.linalg.norm(r_leg, axis=-1)
        + 1e-8
    )
    cos_angle = np.clip(dot_prod / norms, -1.0, 1.0)
    return np.degrees(np.arccos(cos_angle))

Any NaN hip/knee -> NaN leg vector -> NaN dot_prod -> NaN norms ->
NaN cos -> np.clip(NaN) = NaN (numpy clip does NOT catch NaN) ->
np.arccos(NaN) = NaN -> np.degrees(NaN) = NaN.

NaN arccos silently leaks into the spread-eagle angle series, then into
the Ina Bauer composite score, then the step-element metrics, then the
user-visible feedback ("no spread-eagle feedback for corrupt pose").
No error, no log, no guard.

The fix (already on master via #976) wraps the leg-vector diff in
`np.nan_to_num(..., nan=0.0)` so NaN joints become zero legs (which
arccos to a defined 90° value at the trust boundary). This test
asserts the GREEN contract: NaN joints must NOT propagate NaN to the
output angle series.
"""

from __future__ import annotations

import math

import numpy as np

from src.analysis.element_defs import ElementDef

# --------------------------------------------------------------------------- #
# Minimal analyzer shim — we only need compute_spread_eagle_angle, but the
# function is a staticmethod on BiomechanicsAnalyzer, which requires an
# ElementDef-shaped object. A tiny fake suffices (mirrors the pattern in
# test_ds_skating_metrics.py::TestSpreadEagleAngle).
# --------------------------------------------------------------------------- #

_STEP_DEF = ElementDef(
    name="three_turn",
    name_ru="тройка",
    rotations=0,
    has_toe_pick=False,
    key_joints=[],
    ideal_metrics={},
)


# --------------------------------------------------------------------------- #
# Observable 1: single NaN leg keypoint -> angle series must be finite.
# --------------------------------------------------------------------------- #


def test_spread_eagle_single_nan_leg_keypoint_returns_finite():
    """Single NaN LHIP at frame 2 must NOT propagate NaN to angle series.

    RED pre-#976: cos = NaN -> np.clip(NaN) = NaN -> arccos(NaN) = NaN.
    GREEN post-#976: nan_to_num(NaN) = 0 -> leg vector (0,0) -> defined
    angle at the trust boundary.
    """
    from tests.conftest import SyntheticPoseFactory

    from src.analysis.metrics import BiomechanicsAnalyzer
    from src.types import H36Key

    poses = SyntheticPoseFactory.make_standing_pose(n_frames=5).copy()
    poses[2, H36Key.LHIP] = (np.nan, np.nan)
    result = BiomechanicsAnalyzer(_STEP_DEF).compute_spread_eagle_angle(poses)
    assert result.shape == (5,)
    assert np.all(np.isfinite(result)), (
        f"BUG: NaN leg keypoint at frame 2 silently propagated to angle "
        f"series {result!r}. np.clip(NaN, -1, 1) is a no-op, np.arccos(NaN) "
        f"= NaN. Expected finite value (nan_to_num guard at trust "
        f"boundary)."
    )


# --------------------------------------------------------------------------- #
# Observable 2: all-NaN hip+knee on one side -> defined angle series.
# --------------------------------------------------------------------------- #


def test_spread_eagle_all_nan_one_leg_returns_finite():
    """All-NaN left leg across all frames must NOT propagate NaN."""
    from tests.conftest import SyntheticPoseFactory

    from src.analysis.metrics import BiomechanicsAnalyzer
    from src.types import H36Key

    poses = SyntheticPoseFactory.make_standing_pose(n_frames=5).copy()
    poses[:, H36Key.LHIP] = (np.nan, np.nan)
    poses[:, H36Key.LKNEE] = (np.nan, np.nan)
    result = BiomechanicsAnalyzer(_STEP_DEF).compute_spread_eagle_angle(poses)
    assert np.all(np.isfinite(result)), (
        f"BUG: all-NaN left leg silently produced {result!r}. Expected "
        f"finite values (nan_to_num guard converts NaN joints to 0.0)."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN-via-inf-inf arithmetic chain (NaN == inf - inf).
# --------------------------------------------------------------------------- #


def test_spread_eagle_nan_via_chain_returns_finite():
    """NaN propagated via inf-inf arithmetic must NOT leak into output."""
    from tests.conftest import SyntheticPoseFactory

    from src.analysis.metrics import BiomechanicsAnalyzer
    from src.types import H36Key

    poses = SyntheticPoseFactory.make_standing_pose(n_frames=3).copy()
    nan_via_chain = math.inf - math.inf
    assert math.isnan(nan_via_chain)
    poses[1, H36Key.RKNEE] = (nan_via_chain, nan_via_chain)
    result = BiomechanicsAnalyzer(_STEP_DEF).compute_spread_eagle_angle(poses)
    assert np.all(np.isfinite(result)), (
        f"BUG: NaN-via-chain at frame 1 silently produced {result!r}. "
        f"np.nan_to_num at the trust boundary catches this."
    )


# --------------------------------------------------------------------------- #
# Regression guard: a clean standing pose must still report a small spread.
# --------------------------------------------------------------------------- #


def test_spread_eagle_clean_standing_pose_small_angle():
    """Valid standing pose -> spread-eagle angle is finite and small.

    The fix must not corrupt the happy path: clean poses still produce
    a defined, near-zero angle (parallel legs = small spread).
    """
    from tests.conftest import SyntheticPoseFactory

    from src.analysis.metrics import BiomechanicsAnalyzer

    poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
    result = BiomechanicsAnalyzer(_STEP_DEF).compute_spread_eagle_angle(poses)
    assert np.all(np.isfinite(result))
    assert np.max(result) < 30.0, (
        f"Regression: clean standing pose produced max={np.max(result)}°, "
        f"expected < 30° (parallel legs)."
    )


# --------------------------------------------------------------------------- #
# Source check: the unguarded cos = np.clip(dot/norms) pattern is now
# preceded by nan_to_num on both leg vectors. The fix idiom is locked.
# --------------------------------------------------------------------------- #


def test_spread_eagle_source_uses_nan_to_num_guard():
    """Source check: compute_spread_eagle_angle uses np.nan_to_num guard.

    Locks the GREEN contract: any future regression that removes the
    nan_to_num wrapper will flip this test to RED, signalling the
    observable tests above will start silently leaking NaN.
    """
    from pathlib import Path

    src_path = Path(__file__).parent.parent.parent / "src" / "analysis" / "metrics.py"
    src = src_path.read_text(encoding="utf-8")
    assert "def compute_spread_eagle_angle" in src, (
        "compute_spread_eagle_angle not found in metrics.py"
    )
    # Both leg vectors must be wrapped in nan_to_num at the trust boundary.
    assert "nan_to_num(poses[:, H36Key.LKNEE] - poses[:, H36Key.LHIP]" in src, (
        "BUG: LLEG nan_to_num guard missing in compute_spread_eagle_angle. "
        "NaN hip/knee will silently leak NaN through the angle series."
    )
    assert "nan_to_num(poses[:, H36Key.RKNEE] - poses[:, H36Key.RHIP]" in src, (
        "BUG: RLEG nan_to_num guard missing in compute_spread_eagle_angle. "
        "NaN hip/knee will silently leak NaN through the angle series."
    )
