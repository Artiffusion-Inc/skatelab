"""RED repro for issues #809, #810, #812 — ml/src/tas/dataset.py.

Covers:
- #809 (Bug #176): OP25_TO_COCO17 mapping wrong (R/L swapped + chain shifted).
- #810 (Bug #177): normalize_poses uses COCO indices on H3.6M poses (root on shoulder).
- #812 (Bug #179): op25_to_coco17 midhip overwrites COCO LEFT_HIP slot (idx 11).

Loads dataset.py directly to dodge the cv2/numba import chain (same pattern as
ml/tests/tas/test_dataset.py).
"""

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np

# --- direct-load dataset.py (mirrors test_dataset.py bootstrap) -------------
H36M_PATH = Path(__file__).parent.parent / "src" / "pose_estimation" / "h36m.py"
h36m_spec = importlib.util.spec_from_file_location("h36m", H36M_PATH)
h36m_mod = importlib.util.module_from_spec(h36m_spec)
h36m_spec.loader.exec_module(h36m_mod)
sys.modules["h36m"] = h36m_mod

sys.modules.setdefault("types", __import__("types"))
ml_mod = types.ModuleType("ml")
ml_src_mod = types.ModuleType("ml.src")
ml_src_pose = types.ModuleType("ml.src.pose_estimation")
ml_src_tas = types.ModuleType("ml.src.tas")
sys.modules["ml"] = ml_mod
sys.modules["ml.src"] = ml_src_mod
sys.modules["ml.src.pose_estimation"] = ml_src_pose
sys.modules["ml.src.tas"] = ml_src_tas
sys.modules["ml.src.pose_estimation.h36m"] = h36m_mod
ml_src_pose.h36m = h36m_mod

data_spec = importlib.util.spec_from_file_location(
    "ml.src.tas.dataset", Path(__file__).parent.parent / "src" / "tas" / "dataset.py"
)
data_mod = importlib.util.module_from_spec(data_spec)
sys.modules["ml.src.tas.dataset"] = data_mod
data_spec.loader.exec_module(data_mod)

OP25_TO_COCO17 = data_mod.OP25_TO_COCO17
op25_to_coco17 = data_mod.op25_to_coco17
normalize_poses = data_mod.normalize_poses
coco_to_h36m_batch = h36m_mod.coco_to_h36m_batch

# H3.6M indices (per issue #810 / H36Key in h36m.py)
HIP_CENTER = 0
RHIP = 1
RKNEE = 2
RFOOT = 3
LHIP = 4
LKNEE = 5
LFOOT = 6
SPINE = 7
THORAX = 8
NECK = 9
HEAD = 10
LSHOULDER = 11
LELBOW = 12
LWRIST = 13
RSHOULDER = 14
RELBOW = 15
RWRIST = 16

# COCO indices (per _COCOKey in h36m.py)
COCO_NOSE = 0
COCO_LSHOULDER = 5
COCO_RSHOULDER = 6
COCO_LELBOW = 7
COCO_RELBOW = 8
COCO_LWRIST = 9
COCO_RWRIST = 10
COCO_LHIP = 11
COCO_RHIP = 12
COCO_LKNEE = 13
COCO_RKNEE = 14
COCO_LANKLE = 15
COCO_RANKLE = 16


# === #809: OP25_TO_COCO17 mapping ===========================================


def test_op25_to_coco17_correct_mapping_table():
    """Each OP25 index maps to the correct COCO index (issue #809)."""
    expected = {
        0: 0,  # Nose
        2: 6,  # RShoulder
        3: 8,  # RElbow
        4: 10,  # RWrist
        5: 5,  # LShoulder
        6: 7,  # LElbow
        7: 9,  # LWrist
        9: 12,  # RHip
        10: 14,  # RKnee
        11: 16,  # RAnkle
        12: 11,  # LHip
        13: 13,  # LKnee
        14: 15,  # LAnkle
    }
    for op_idx, coco_idx in expected.items():
        assert OP25_TO_COCO17[op_idx] == coco_idx, (
            f"OP25 {op_idx} -> COCO {OP25_TO_COCO17[op_idx]}, expected {coco_idx}"
        )


def test_op25_to_coco17_specific_joints_named():
    """Named spot-checks from the issue contract."""
    assert OP25_TO_COCO17[2] == 6  # RShoulder -> COCO RShoulder
    assert OP25_TO_COCO17[3] == 8  # RElbow   -> COCO RElbow
    assert OP25_TO_COCO17[4] == 10  # RWrist   -> COCO RWrist
    assert OP25_TO_COCO17[5] == 5  # LShoulder -> COCO LShoulder
    assert OP25_TO_COCO17[6] == 7  # LElbow   -> COCO LElbow
    assert OP25_TO_COCO17[7] == 9  # LWrist   -> COCO LWrist
    assert OP25_TO_COCO17[9] == 12  # RHip     -> COCO RHip
    assert OP25_TO_COCO17[12] == 11  # LHip     -> COCO LHip


def test_op25_to_coco17_no_collisions():
    """No two OP25 indices map to the same COCO index."""
    targets = list(OP25_TO_COCO17.values())
    assert len(targets) == len(set(targets)), f"collision: {targets}"


def test_op25_to_coco17_covers_13_joints_within_17():
    """All mapped targets are within [0, 17) and we map 13 OP25 keypoints."""
    assert len(OP25_TO_COCO17) == 13
    for coco_idx in OP25_TO_COCO17.values():
        assert 0 <= coco_idx < 17


def test_op25_to_coco17_observable_rshoulder_lands_in_rshoulder_slot():
    """OP25 RShoulder value must land in COCO RShoulder slot, not LShoulder (#809)."""
    op25 = np.zeros((1, 25, 3), dtype=np.float64)
    op25[0, 2, :] = [1.0, 2.0, 1.0]  # OP25 RShoulder
    out = op25_to_coco17(op25)
    # COCO 6 = RShoulder must hold the OP25 RShoulder value
    np.testing.assert_allclose(out[0, COCO_RSHOULDER, :], [1.0, 2.0])
    # COCO 5 = LShoulder must NOT hold the RShoulder value (the bug did this)
    assert not np.allclose(out[0, COCO_LSHOULDER, :], [1.0, 2.0])


# === #812: midhip overwrite of COCO LEFT_HIP slot ============================


def test_op25_to_coco17_lhip_slot_not_overwritten_by_midhip():
    """COCO idx 11 (LHip) must hold the mapped LHip value, NOT the midhip average (#812)."""
    op25 = np.zeros((1, 25, 3), dtype=np.float64)
    op25[0, 9, :] = [1.0, 1.0, 1.0]  # OP25 RHip -> COCO 12
    op25[0, 12, :] = [-1.0, 1.0, 1.0]  # OP25 LHip -> COCO 11
    out = op25_to_coco17(op25)
    # COCO 11 = LEFT_HIP must hold the actual LHip value (-1.0, 1.0), not midhip avg (0.0, 1.0)
    np.testing.assert_allclose(out[0, COCO_LHIP, :], [-1.0, 1.0])
    # COCO 12 = RIGHT_HIP must hold the actual RHip value
    np.testing.assert_allclose(out[0, COCO_RHIP, :], [1.0, 1.0])


def test_op25_to_coco17_midhip_not_written_to_any_slot():
    """No COCO slot should hold the midhip average (1.0 + -1.0)/2 = 0.0 — the
    overwrite bug put it in idx 11. Verify no slot holds the avg x=0.0 while
    LHip/RHip hold distinct x values."""
    op25 = np.zeros((1, 25, 3), dtype=np.float64)
    op25[0, 9, :] = [2.0, 0.0, 1.0]  # RHip
    op25[0, 12, :] = [-2.0, 0.0, 1.0]  # LHip
    out = op25_to_coco17(op25)
    # midhip avg would be (0.0, 0.0); ensure neither hip slot is the midhip avg
    assert not np.allclose(out[0, COCO_LHIP, :], [0.0, 0.0])
    assert not np.allclose(out[0, COCO_RHIP, :], [0.0, 0.0])
    # And the actual values preserved
    np.testing.assert_allclose(out[0, COCO_LHIP, :], [-2.0, 0.0])
    np.testing.assert_allclose(out[0, COCO_RHIP, :], [2.0, 0.0])


def test_op25_to_coco17_downstream_h36m_hip_preserved():
    """coco_to_h36m_batch reads COCO LHip/RHip to build H3.6M LHIP/RHIP — ensure
    the actual hip values flow through (not midhip)."""
    op25 = np.zeros((1, 25, 3), dtype=np.float64)
    op25[0, 9, :] = [2.0, 0.0, 1.0]  # RHip
    op25[0, 12, :] = [-2.0, 0.0, 1.0]  # LHip
    coco = op25_to_coco17(op25)
    h36 = coco_to_h36m_batch(coco)
    np.testing.assert_allclose(h36[0, LHIP, :], [-2.0, 0.0])
    np.testing.assert_allclose(h36[0, RHIP, :], [2.0, 0.0])
    # HIP_CENTER is the midpoint, derived inside coco_to_h36m_batch
    np.testing.assert_allclose(h36[0, HIP_CENTER, :], [0.0, 0.0])


# === #810: normalize_poses uses H3.6M indices =================================


def test_normalize_poses_roots_at_hip_not_shoulder():
    """normalize_poses is called on H3.6M poses; root must be the hip, not the
    shoulder (#810). Place a unique marker at HIP_CENTER and check it lands at
    origin after normalization."""
    poses = np.zeros((1, 17, 2), dtype=np.float32)
    # H3.6M: 0=HIP_CENTER, 1=RHIP, 4=LHIP — put hip at a known point
    poses[0, HIP_CENTER, :] = [3.0, 4.0]
    poses[0, RHIP, :] = [3.0, 4.0]
    poses[0, LHIP, :] = [3.0, 4.0]
    # Put shoulders far away so a shoulder-rooted bug would NOT zero the hip
    poses[0, LSHOULDER, :] = [10.0, 20.0]
    poses[0, RSHOULDER, :] = [10.0, 20.0]
    out = normalize_poses(poses)
    # After centering on hip, HIP_CENTER should map to (0,0) (within scale)
    # If rooted on shoulder instead, HIP_CENTER would be far from origin.
    np.testing.assert_allclose(out[0, HIP_CENTER, :], [0.0, 0.0], atol=1e-5)


def test_normalize_poses_spine_from_hip_to_thorax_not_leg():
    """The scale (spine length) must come from hip->thorax/neck, not a leg
    segment (#810). Construct a pose where hip->thorax distance differs from
    leg distance and verify the scale is the spine distance."""
    poses = np.zeros((1, 17, 2), dtype=np.float32)
    # Hip at origin
    poses[0, HIP_CENTER, :] = [0.0, 0.0]
    poses[0, RHIP, :] = [0.0, 0.0]
    poses[0, LHIP, :] = [0.0, 0.0]
    # THORAX at distance 2.0 (this is the real spine length)
    poses[0, THORAX, :] = [0.0, 2.0]
    poses[0, NECK, :] = [0.0, 2.0]
    # Knees/feet at a DIFFERENT distance (5.0) — bug used LKNEE/LFOOT as spine
    poses[0, LKNEE, :] = [0.0, 5.0]
    poses[0, LFOOT, :] = [0.0, 5.0]
    poses[0, RKNEE, :] = [0.0, 5.0]
    poses[0, RFOOT, :] = [0.0, 5.0]
    out = normalize_poses(poses)
    # If spine=2.0 (correct), THORAX normalized to y=1.0
    # If spine=5.0 (bug: leg), THORAX normalized to y=0.4
    np.testing.assert_allclose(out[0, THORAX, 1], 1.0, atol=1e-5)


def test_normalize_poses_bug_observable_shoulder_root_fails():
    """The exact RED scenario from the issue: hip at origin, shoulder at (5,5),
    leg at y=-2..-3. The bug centered on mean(11,12)=(5,5) (shoulder/elbow) and
    scaled by leg length. After fix, hip lands at origin."""
    poses = np.zeros((1, 17, 2), dtype=np.float32)
    poses[0, HIP_CENTER, :] = [0.0, 0.0]
    poses[0, RHIP, :] = [0.0, 0.0]
    poses[0, LHIP, :] = [0.0, 0.0]
    # Bug indexed COCO 11:13 = H3.6M LSHOULDER, LELBOW
    poses[0, LSHOULDER, :] = [5.0, 5.0]
    poses[0, LELBOW, :] = [5.0, 5.0]
    # Bug indexed COCO 5:7 = H3.6M LKNEE, LFOOT
    poses[0, LKNEE, :] = [0.0, -2.0]
    poses[0, LFOOT, :] = [0.0, -3.0]
    out = normalize_poses(poses)
    # With the fix, hip is root -> HIP_CENTER at origin
    np.testing.assert_allclose(out[0, HIP_CENTER, :], [0.0, 0.0], atol=1e-5)


# === source-checks (root-cause lock) ========================================


def test_source_no_coco_midhip_overwrite_line():
    """The destructive `out[:, 11, :] = midhip.squeeze(1)` line must be gone."""
    import inspect

    src = inspect.getsource(op25_to_coco17)
    assert "out[:, 11, :] = midhip.squeeze(1)" not in src
    # The wrong comment must also be gone
    assert "COCO index 11 is mid-hip" not in src


def test_source_normalize_poses_uses_h36m_hip_indices():
    """normalize_poses must reference H3.6M hip (idx 0 or 1+4), not COCO 11:13."""
    import inspect

    src = inspect.getsource(normalize_poses)
    # The buggy COCO-style slice on H3.6M must be gone
    assert "11:13" not in src
    assert "5:7" not in src
    # And must use a real H3.6M hip index (0, or 1+4 midpoint)
    assert "0" in src  # HIP_CENTER or slice containing it


def test_normalize_poses_all_finite():
    """Regression: finite input -> finite output (no NaN/inf leak)."""
    rng = np.random.default_rng(42)
    poses = rng.standard_normal((8, 17, 2)).astype(np.float32)
    out = normalize_poses(poses)
    assert np.all(np.isfinite(out)), "normalize_poses produced non-finite output"


def test_op25_to_coco17_all_finite():
    """Regression: finite OP25 input -> finite COCO output."""
    rng = np.random.default_rng(7)
    op25 = rng.standard_normal((8, 25, 3)).astype(np.float64)
    out = op25_to_coco17(op25)
    assert np.all(np.isfinite(out)), "op25_to_coco17 produced non-finite output"
