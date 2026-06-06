"""Tests for DS_Skating technique integration: rotation cross-check, leg angle metrics."""

import numpy as np
import pytest

from ml.tests.conftest import SyntheticPoseFactory
from src.analysis.element_defs import ElementDef
from src.types import H36Key


class TestSyntheticPoseFactory:
    """Verify factory produces poses with analytically known angles."""

    def test_standing_pose_shape(self):
        poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
        assert poses.shape == (10, 17, 2)

    def test_standing_pose_knees_straight(self):
        poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
        # Standing: LHIP-LKNEE-LFOOT should be ~180 degrees
        for i in range(10):
            hip = poses[i, H36Key.LHIP]
            knee = poses[i, H36Key.LKNEE]
            foot = poses[i, H36Key.LFOOT]
            angle = _angle_deg(hip, knee, foot)
            assert 170 <= angle <= 180, f"Frame {i}: knee angle {angle}"

    def test_standing_pose_legs_parallel(self):
        poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
        se_angle = _compute_se_angle_manual(poses)
        assert np.mean(se_angle) < 15, "Standing pose should have small spread eagle angle"

    def test_rotation_sequence_shape(self):
        poses = SyntheticPoseFactory.make_rotation_sequence(n_rotations=2, n_frames=120, fps=30)
        assert poses.shape == (120, 17, 3)

    def test_rotation_sequence_known_total(self):
        poses = SyntheticPoseFactory.make_rotation_sequence(n_rotations=2, n_frames=120, fps=30)
        l_sho = poses[:, H36Key.LSHOULDER]
        r_sho = poses[:, H36Key.RSHOULDER]
        yaw = np.arctan2(r_sho[:, 2] - l_sho[:, 2], r_sho[:, 0] - l_sho[:, 0])
        unwrapped = np.unwrap(yaw)
        total_deg = abs(unwrapped[-1] - unwrapped[0]) * 180 / np.pi
        assert abs(total_deg - 720) < 20, f"Expected ~720°, got {total_deg}"

    def test_spread_eagle_pose_known_angle(self):
        poses = SyntheticPoseFactory.make_spread_eagle_pose(angle_deg=160, n_frames=10)
        se_angle = _compute_se_angle_manual(poses)
        assert abs(np.mean(se_angle) - 160) < 5, f"Expected 160°, got {np.mean(se_angle)}"

    def test_ina_bauer_pose_shape(self):
        poses = SyntheticPoseFactory.make_ina_bauer_pose(
            leg_spread_deg=160, lean_deg=30, knee_diff_deg=30, n_frames=10
        )
        assert poses.shape == (10, 17, 2)


def _angle_deg(a, b, c):
    """3-point angle in degrees."""
    ba = a - b
    bc = c - b
    cos_val = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return np.degrees(np.arccos(np.clip(cos_val, -1, 1)))


def _compute_se_angle_manual(poses):
    """Manual spread eagle angle for testing."""
    l_leg = poses[:, H36Key.LKNEE] - poses[:, H36Key.LHIP]
    r_leg = poses[:, H36Key.RKNEE] - poses[:, H36Key.RHIP]
    cos_a = np.sum(l_leg * r_leg, axis=-1) / (
        np.linalg.norm(l_leg, axis=-1) * np.linalg.norm(r_leg, axis=-1) + 1e-8
    )
    return np.degrees(np.arccos(np.clip(cos_a, -1, 1)))


class TestRotationYawDelta:
    """Tests for compute_rotation_yaw_delta with physiological clamping."""

    LUTZ_DEF = ElementDef(
        name="lutz", name_ru="люц", rotations=3, has_toe_pick=True, key_joints=[], ideal_metrics={}
    )

    def test_known_rotation_single(self):
        """Single rotation (360 deg) from synthetic poses."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_rotation_sequence(n_rotations=1, n_frames=60, fps=30)
        flight_indices = np.arange(len(poses))
        analyzer = BiomechanicsAnalyzer(self.LUTZ_DEF)
        total_deg, rot_count, clamped = analyzer.compute_rotation_yaw_delta(
            poses, flight_indices, fps=30
        )
        assert abs(total_deg - 360) < 30, f"Expected ~360 deg, got {total_deg}"
        assert abs(rot_count - 1.0) < 0.1
        assert clamped.sum() == 0

    def test_known_rotation_triple(self):
        """Triple rotation (1080 deg) from synthetic poses."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_rotation_sequence(n_rotations=3, n_frames=90, fps=30)
        flight_indices = np.arange(len(poses))
        analyzer = BiomechanicsAnalyzer(self.LUTZ_DEF)
        total_deg, _rot_count, clamped = analyzer.compute_rotation_yaw_delta(
            poses, flight_indices, fps=30
        )
        assert abs(total_deg - 1080) < 50, f"Expected ~1080 deg, got {total_deg}"
        assert clamped.sum() == 0

    def test_physiological_clamping(self):
        """Frame with >720 deg/s rotation gets clamped."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_rotation_sequence(n_rotations=1, n_frames=60, fps=30)
        # Inject a huge jump at frame 30
        poses[30, H36Key.RSHOULDER, 0] += 5.0
        flight_indices = np.arange(len(poses))
        analyzer = BiomechanicsAnalyzer(self.LUTZ_DEF)
        _total_deg, _rot_count, clamped = analyzer.compute_rotation_yaw_delta(
            poses, flight_indices, fps=30
        )
        assert clamped.sum() >= 1, "Physiologically impossible frame should be clamped"

    def test_empty_flight_indices(self):
        """Empty flight indices returns 0."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_rotation_sequence(n_rotations=1, n_frames=60)
        analyzer = BiomechanicsAnalyzer(self.LUTZ_DEF)
        total_deg, rot_count, clamped = analyzer.compute_rotation_yaw_delta(
            poses, np.array([], dtype=int), fps=30
        )
        assert total_deg == 0.0
        assert rot_count == 0.0
        assert len(clamped) == 0

    def test_near_zero_shoulder_length(self):
        """All-zero poses: shoulder length near-zero returns 0."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = np.zeros((10, 17, 3), dtype=np.float32)
        analyzer = BiomechanicsAnalyzer(self.LUTZ_DEF)
        total_deg, rot_count, _clamped = analyzer.compute_rotation_yaw_delta(
            poses, np.arange(10), fps=30
        )
        assert total_deg == 0.0
        assert rot_count == 0.0
