"""RED repro for #811 (COCO indices on H3.6M) and #817 (dur B=1 normalize).

Both bugs live in ml/src/tas/classifier.py.
"""

import inspect

import numpy as np
import pytest

from src.tas.classifier import Skeleton1DCNN, extract_segment_features

# H3.6M 17kp indices (src/types.py H36Key).
RHIP, LHIP = 1, 4
LSHOULDER, RSHOULDER = 11, 14


# ---------------------------------------------------------------------------
# #811: extract_segment_features uses COCO indices on H3.6M poses.
# ---------------------------------------------------------------------------


def test_extract_segment_features_uses_h36m_hip_indices():
    """hip_y_range must come from RHIP+LHIP (idx 1+4), not LSHOULDER+LELBOW."""
    # Pose where hips Y vary but shoulders Y are flat.
    poses = np.zeros((5, 17, 2), dtype=np.float32)
    poses[:, RHIP, 1] = [0.0, 0.25, 0.5, 0.25, 0.0]  # RHIP Y moves
    poses[:, LHIP, 1] = [0.0, 0.25, 0.5, 0.25, 0.0]  # LHIP Y moves
    # Shoulders flat at Y=0.9 (so old COCO-idx bug reading idx 11:13 would see flat).
    poses[:, LSHOULDER, 1] = 0.9
    poses[:, RSHOULDER, 1] = 0.9

    feats = extract_segment_features(poses, fps=30.0)
    # Real hip Y range = 0.5, not 0.0.
    assert feats["hip_y_range"] == pytest.approx(0.5, abs=1e-4)


def test_extract_segment_features_uses_h36m_shoulder_indices():
    """rotation_speed must come from LSHOULDER+RSHOULDER (idx 11+14), not LKNEE/LFOOT."""
    # Pose where shoulder vector angle changes over frames; knees/feet flat.
    T = 8
    poses = np.zeros((T, 17, 2), dtype=np.float32)
    # LSHOULDER fixed left.
    poses[:, LSHOULDER, :] = [0.0, 0.9]
    # RSHOULDER sweeps in a circle around LSHOULDER → angle changes.
    angles = np.linspace(0.0, np.pi / 2, T)
    poses[:, RSHOULDER, 0] = 0.5 * np.cos(angles)
    poses[:, RSHOULDER, 1] = 0.9 + 0.5 * np.sin(angles)
    # Old COCO bug read idx [5,6] = LKNEE, LFOOT — keep them flat so bug gives 0.
    poses[:, 5, :] = [0.1, 0.1]
    poses[:, 6, :] = [0.2, 0.1]

    feats = extract_segment_features(poses, fps=30.0)
    # Real shoulder vector rotates → rot_speed > 0. Old bug → 0.
    assert feats["rotation_speed"] > 0.0


def test_extract_segment_features_wrong_joints_observable():
    """The exact repro from #811: shoulder Y rising must NOT be read as hip Y."""
    poses = np.zeros((5, 17, 2), dtype=np.float32)
    poses[:, RHIP, 1] = 0.0  # real hips flat
    poses[:, LHIP, 1] = 0.0
    # Old bug indices 11:13 (LSHOULDER, LELBOW) Y rising.
    poses[:, LSHOULDER, 1] = [0.0, 0.5, 1.0, 1.5, 2.0]
    poses[:, 12, 1] = [0.0, 0.5, 1.0, 1.5, 2.0]  # LELBOW

    feats = extract_segment_features(poses, fps=30.0)
    # Fixed: real hips flat → hip_y_range == 0.0. Old bug: 2.0.
    assert feats["hip_y_range"] == pytest.approx(0.0, abs=1e-6)


def test_extract_segment_features_source_uses_h36m_indices():
    """Source-check: extract_segment_features indexes [1,4] and [11,14]."""
    src = inspect.getsource(extract_segment_features)
    assert "[1, 4]" in src  # hip indices RHIP+LHIP
    assert "[11, 14]" in src  # shoulder indices LSHOULDER+RSHOULDER


# ---------------------------------------------------------------------------
# #817: Skeleton1DCNN dur = lengths / lengths.max() collapses at B=1.
# ---------------------------------------------------------------------------


def test_dur_single_sample_observable():
    """Bare tensor math from #817: lengths/lengths.max() is always 1.0 at B=1."""
    import torch

    for L in [5, 30, 120]:
        lengths = torch.tensor([L], dtype=torch.float)
        buggy = (lengths / lengths.max()).unsqueeze(1)
        assert buggy.item() == pytest.approx(1.0)  # the bug


def test_skeleton1dcnn_dur_single_sample_discriminates():
    """Skeleton1DCNN forward must use a fixed reference, not lengths.max()."""
    # Strip comments so the bug pattern in a docstring/comment doesn't false-pass.
    src = "\n".join(
        line
        for line in inspect.getsource(Skeleton1DCNN.forward).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "lengths.max()" not in src
    assert "max_seq_len" in src  # fixed reference


def test_skeleton1dcnn_dur_values_differ_b1():
    """dur must differ between L=5 and L=120 at B=1 under the model's reference."""
    import torch

    model = Skeleton1DCNN(input_dim=34, num_classes=1)
    ref = float(model.max_seq_len)
    durs = []
    for L in [5, 120]:
        lengths = torch.tensor([L], dtype=torch.float)
        durs.append((lengths.float() / ref).unsqueeze(1).item())
    assert durs[0] != durs[1]
    assert durs[0] < durs[1]


def test_skeleton1dcnn_has_fixed_max_len_attr():
    """Skeleton1DCNN must expose a fixed-reference normalization attribute."""
    import torch

    model = Skeleton1DCNN(input_dim=34, num_classes=1)
    # Either an explicit attribute or a module-level constant.
    has_attr = hasattr(model, "max_seq_len") or hasattr(model, "max_frames")
    src = inspect.getsource(Skeleton1DCNN.forward)
    has_fixed_in_src = "max_seq_len" in src or "max_frames" in src or "/ fps" in src
    assert has_attr or has_fixed_in_src


# ---------------------------------------------------------------------------
# Regression: all-finite output + NaN guard preserved.
# ---------------------------------------------------------------------------


def test_extract_segment_features_all_finite():
    """All-finite regression — NaN guard from #979 must stay intact."""
    poses = np.random.default_rng(0).standard_normal((10, 17, 2)).astype(np.float32)
    feats = extract_segment_features(poses, fps=30.0)
    for k, v in feats.items():
        assert np.isfinite(v), f"{k} not finite: {v}"


def test_extract_segment_features_nan_guard_present():
    """The #979 nan_to_num guard must remain at the top of the function."""
    src = inspect.getsource(extract_segment_features)
    assert "nan_to_num" in src
