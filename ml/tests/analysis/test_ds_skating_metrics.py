"""Tests for DS_Skating technique integration: rotation cross-check, leg angle metrics."""

import numpy as np
import pytest

from ml.tests.conftest import SyntheticPoseFactory
from src.analysis.element_defs import ElementDef
from src.types import ElementPhase, H36Key


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


class TestSpreadEagleAngle:
    """Tests for compute_spread_eagle_angle."""

    STEP_DEF = ElementDef(
        name="three_turn",
        name_ru="тройка",
        rotations=0,
        has_toe_pick=False,
        key_joints=[],
        ideal_metrics={},
    )

    def test_standing_pose_small_angle(self):
        """Standing pose: legs nearly parallel, angle < 15°."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
        analyzer = BiomechanicsAnalyzer(self.STEP_DEF)
        se_angle = analyzer.compute_spread_eagle_angle(poses)
        assert se_angle.shape == (10,)
        assert np.mean(se_angle) < 15

    def test_spread_eagle_160(self):
        """160° spread eagle pose: mean angle ≈ 160°."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_spread_eagle_pose(angle_deg=160, n_frames=10)
        analyzer = BiomechanicsAnalyzer(self.STEP_DEF)
        se_angle = analyzer.compute_spread_eagle_angle(poses)
        assert abs(np.mean(se_angle) - 160) < 5, f"Expected ~160°, got {np.mean(se_angle)}"

    def test_output_range(self):
        """All values in [0, 180]."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_spread_eagle_pose(angle_deg=170, n_frames=20)
        analyzer = BiomechanicsAnalyzer(self.STEP_DEF)
        se_angle = analyzer.compute_spread_eagle_angle(poses)
        assert np.all(se_angle >= 0)
        assert np.all(se_angle <= 180)

    def test_single_frame(self):
        """Single frame pose: returns single value."""
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_spread_eagle_pose(angle_deg=150, n_frames=1)
        analyzer = BiomechanicsAnalyzer(self.STEP_DEF)
        se_angle = analyzer.compute_spread_eagle_angle(poses)
        assert se_angle.shape == (1,)


class TestInaBauerScore:
    """Tests for compute_ina_bauer_score."""

    def test_standing_pose_low_score(self):
        """Standing pose: score should be low (no spread eagle, no lean, no asymmetry)."""
        from src.analysis.element_defs import ElementDef
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
        analyzer = BiomechanicsAnalyzer(
            ElementDef(
                name="three_turn",
                name_ru="Тройной поворот",
                rotations=0,
                has_toe_pick=False,
                key_joints=[],
                ideal_metrics={},
            )
        )
        score = analyzer.compute_ina_bauer_score(poses)
        assert score.shape == (10,)
        assert np.mean(score) < 0.3, f"Standing pose IB score too high: {np.mean(score)}"

    def test_ina_bauer_pose_moderate_score(self):
        """Ina Bauer pose: score should be > 0.3."""
        from src.analysis.element_defs import ElementDef
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_ina_bauer_pose(
            leg_spread_deg=160, lean_deg=30, knee_diff_deg=30, n_frames=10
        )
        analyzer = BiomechanicsAnalyzer(
            ElementDef(
                name="three_turn",
                name_ru="Тройной поворот",
                rotations=0,
                has_toe_pick=False,
                key_joints=[],
                ideal_metrics={},
            )
        )
        score = analyzer.compute_ina_bauer_score(poses)
        assert np.mean(score) > 0.3, f"IB pose score too low: {np.mean(score)}"

    def test_output_range_0_to_1(self):
        """Score values in [0, 1]."""
        from src.analysis.element_defs import ElementDef
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_ina_bauer_pose(
            leg_spread_deg=170, lean_deg=40, knee_diff_deg=35, n_frames=10
        )
        analyzer = BiomechanicsAnalyzer(
            ElementDef(
                name="three_turn",
                name_ru="Тройной поворот",
                rotations=0,
                has_toe_pick=False,
                key_joints=[],
                ideal_metrics={},
            )
        )
        score = analyzer.compute_ina_bauer_score(poses)
        assert np.all(score >= 0.0)
        assert np.all(score <= 1.0)

    def test_weights_sum_to_one(self):
        """Component weights 0.5 + 0.3 + 0.2 = 1.0."""
        assert abs(0.5 + 0.3 + 0.2 - 1.0) < 1e-10


class TestRotationCrossCheck:
    """Tests for rotation discrepancy detection in _analyze_jump."""

    def test_discrepancy_flag_on_disagreement(self):
        """When methods disagree by >0.5 rotation, rotation_discrepancy is True."""
        from unittest.mock import patch

        from src.analysis.metrics import BiomechanicsAnalyzer
        from src.types import ElementPhase

        element_def = ElementDef(
            name="lutz",
            name_ru="Лутц",
            rotations=3,
            has_toe_pick=True,
            key_joints=[],
            ideal_metrics={},
        )
        analyzer = BiomechanicsAnalyzer(element_def)

        poses_2d = SyntheticPoseFactory.make_standing_pose(n_frames=30)
        poses_3d = np.concatenate([poses_2d, np.zeros((30, 17, 1), dtype=np.float32)], axis=-1)
        phases = ElementPhase(name="lutz", start=0, takeoff=5, peak=15, landing=25, end=29)

        with patch.object(
            analyzer, "compute_total_rotation_from_poses", return_value=(1080.0, 3.0)
        ):
            with patch.object(
                analyzer,
                "compute_rotation_yaw_delta",
                return_value=(720.0, 2.0, np.array([], dtype=bool)),
            ):
                results = analyzer._analyze_jump(poses_2d, phases, fps=30.0, poses_3d=poses_3d)

        discrepancy_metrics = [r for r in results if r.name == "rotation_discrepancy"]
        assert len(discrepancy_metrics) == 1
        assert discrepancy_metrics[0].value is True

    def test_no_discrepancy_when_methods_agree(self):
        """When methods agree, rotation_discrepancy is False."""
        from unittest.mock import patch

        from src.analysis.metrics import BiomechanicsAnalyzer
        from src.types import ElementPhase

        element_def = ElementDef(
            name="lutz",
            name_ru="Лутц",
            rotations=3,
            has_toe_pick=True,
            key_joints=[],
            ideal_metrics={},
        )
        analyzer = BiomechanicsAnalyzer(element_def)

        poses_2d = SyntheticPoseFactory.make_standing_pose(n_frames=30)
        poses_3d = np.concatenate([poses_2d, np.zeros((30, 17, 1), dtype=np.float32)], axis=-1)
        phases = ElementPhase(name="lutz", start=0, takeoff=5, peak=15, landing=25, end=29)

        with patch.object(
            analyzer, "compute_total_rotation_from_poses", return_value=(1080.0, 3.0)
        ):
            with patch.object(
                analyzer,
                "compute_rotation_yaw_delta",
                return_value=(1050.0, 2.9, np.array([], dtype=bool)),
            ):
                results = analyzer._analyze_jump(poses_2d, phases, fps=30.0, poses_3d=poses_3d)

        discrepancy_metrics = [r for r in results if r.name == "rotation_discrepancy"]
        assert len(discrepancy_metrics) == 1
        assert discrepancy_metrics[0].value is False


class TestSpiralIndicator:
    """Tests for compute_spiral_indicator."""

    def test_standing_pose_low_indicator(self):
        """Both feet on ice: low foot Y difference."""
        from src.analysis.element_defs import ElementDef
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_standing_pose(n_frames=10)
        analyzer = BiomechanicsAnalyzer(
            ElementDef(
                name="three_turn",
                name_ru="Тройной поворот",
                rotations=0,
                has_toe_pick=False,
                key_joints=[],
                ideal_metrics={},
            )
        )
        indicator = analyzer.compute_spiral_indicator(poses)
        assert indicator.shape == (10,)
        assert np.mean(indicator) < 0.05


class TestStepAnalysisWithLegAngles:
    """Verify _analyze_step includes spread eagle and Ina Bauer metrics."""

    def test_step_analysis_includes_spread_eagle(self):
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_spread_eagle_pose(angle_deg=160, n_frames=30)
        phases = ElementPhase(name="three_turn", start=0, takeoff=5, peak=15, landing=25, end=29)
        element_def = ElementDef(
            name="three_turn",
            name_ru="Тройной поворот",
            rotations=0,
            has_toe_pick=False,
            key_joints=[],
            ideal_metrics={},
        )
        analyzer = BiomechanicsAnalyzer(element_def)
        results = analyzer._analyze_step(poses, phases, fps=30.0)
        metric_names = [r.name for r in results]
        assert "spread_eagle_angle" in metric_names, (
            f"Missing spread_eagle_angle. Got: {metric_names}"
        )

    def test_step_analysis_includes_ina_bauer(self):
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_ina_bauer_pose(
            leg_spread_deg=160, lean_deg=30, knee_diff_deg=30, n_frames=30
        )
        phases = ElementPhase(name="three_turn", start=0, takeoff=5, peak=15, landing=25, end=29)
        element_def = ElementDef(
            name="three_turn",
            name_ru="Тройной поворот",
            rotations=0,
            has_toe_pick=False,
            key_joints=[],
            ideal_metrics={},
        )
        analyzer = BiomechanicsAnalyzer(element_def)
        results = analyzer._analyze_step(poses, phases, fps=30.0)
        metric_names = [r.name for r in results]
        assert "ina_bauer_score" in metric_names, f"Missing ina_bauer_score. Got: {metric_names}"

    def test_step_analysis_includes_spiral_indicator(self):
        from src.analysis.metrics import BiomechanicsAnalyzer

        poses = SyntheticPoseFactory.make_standing_pose(n_frames=30)
        phases = ElementPhase(name="three_turn", start=0, takeoff=5, peak=15, landing=25, end=29)
        element_def = ElementDef(
            name="three_turn",
            name_ru="Тройной поворот",
            rotations=0,
            has_toe_pick=False,
            key_joints=[],
            ideal_metrics={},
        )
        analyzer = BiomechanicsAnalyzer(element_def)
        results = analyzer._analyze_step(poses, phases, fps=30.0)
        metric_names = [r.name for r in results]
        assert "spiral_indicator" in metric_names, f"Missing spiral_indicator. Got: {metric_names}"
