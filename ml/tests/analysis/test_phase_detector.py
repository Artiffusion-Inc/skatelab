"""Tests for automatic phase detection."""

import numpy as np

from src.analysis.metrics import PhaseDetectionResult
from src.analysis.phase_detector import PhaseDetector, count_rotations
from src.types import ElementPhase, H36Key


class TestPhaseDetector:
    """Test PhaseDetector."""

    def test_detector_initialization(self):
        """Should initialize without errors."""
        detector = PhaseDetector()

        assert detector is not None

    def test_detect_jump_phases_simple(self):
        """Should detect jump phases from simple trajectory."""
        detector = PhaseDetector()

        # Create simple jump trajectory: baseline -> peak -> baseline
        poses = np.zeros((50, 17, 2), dtype=np.float32)

        # Set hip Y to simulate jump with clear phases
        for i in range(50):
            if i < 10:
                poses[i, H36Key.LHIP, 1] = 0.3  # left_hip baseline
                poses[i, H36Key.RHIP, 1] = 0.3  # right_hip baseline
            elif i < 20:
                # Rising phase (10 frames)
                progress = (i - 10) / 10
                poses[i, H36Key.LHIP, 1] = 0.3 - 0.2 * progress
                poses[i, H36Key.RHIP, 1] = 0.3 - 0.2 * progress
            elif i < 30:
                # Hang time at peak (10 frames)
                poses[i, H36Key.LHIP, 1] = 0.1  # peak height
                poses[i, H36Key.RHIP, 1] = 0.1
            else:
                # Landing phase (20 frames)
                progress = (i - 30) / 20
                poses[i, H36Key.LHIP, 1] = 0.1 + 0.2 * progress
                poses[i, H36Key.RHIP, 1] = 0.1 + 0.2 * progress

        result = detector.detect_jump_phases(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing
        assert result.confidence > 0

    def test_detect_three_turn_phases(self):
        """Should detect three-turn phases."""
        detector = PhaseDetector()

        # Create simple trajectory with edge change
        # H3.6M 17 format
        poses = np.zeros((50, 17, 2), dtype=np.float32)

        result = detector.detect_three_turn_phases(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.end < len(poses)

    def test_detect_phases_jump(self):
        """Should route jump elements correctly."""
        detector = PhaseDetector()

        poses = np.zeros((50, 17, 2), dtype=np.float32)

        result = detector.detect_phases(poses, fps=30.0, element_type="waltz_jump")

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.name == "jump"

    def test_detect_phases_three_turn(self):
        """Should route step elements correctly."""
        detector = PhaseDetector()

        poses = np.zeros((50, 17, 2), dtype=np.float32)

        result = detector.detect_phases(poses, fps=30.0, element_type="three_turn")

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.name == "three_turn"

    def test_detect_phases_unknown_element(self):
        """Should handle unknown elements gracefully."""
        detector = PhaseDetector()

        poses = np.zeros((50, 17, 2), dtype=np.float32)

        result = detector.detect_phases(poses, fps=30.0, element_type="unknown")

        assert isinstance(result, PhaseDetectionResult)
        # Should return default phases with low confidence
        assert result.confidence == 0

    def test_find_takeoff_before_peak(self):
        """Should find takeoff frame before peak."""
        detector = PhaseDetector()

        derivative = np.array([0, 0, -0.1, -0.1, -0.05, 0, 0])
        peak_idx = 5

        takeoff = detector._find_takeoff(derivative, peak_idx)

        assert takeoff < peak_idx
        assert takeoff >= 0

    def test_find_landing_after_peak(self):
        """Should find landing frame after peak."""
        detector = PhaseDetector()

        hip_y = np.array([0.3, 0.2, 0.1, 0.2, 0.3, 0.3])
        peak_idx = 2
        takeoff_idx = 0

        landing = detector._find_landing(hip_y, peak_idx, takeoff_idx)

        assert landing > peak_idx
        assert landing < len(hip_y)


class TestPhaseDetectionResult:
    """Test PhaseDetectionResult dataclass."""

    def test_phase_detection_result_creation(self):
        """Should create result correctly."""
        phases = ElementPhase(
            name="test",
            start=0,
            takeoff=10,
            peak=20,
            landing=30,
            end=40,
        )

        result = PhaseDetectionResult(phases=phases, confidence=0.8)

        assert result.phases == phases
        assert result.confidence == 0.8


class TestParabolicFlightDetector:
    """Test parabolic CoM fitting for jump phase detection."""

    @staticmethod
    def _make_jump_poses(
        n_frames: int,
        takeoff_frame: int,
        landing_frame: int,
        peak_y: float = 0.1,
        baseline_y: float = 0.4,
    ) -> np.ndarray:
        """Create normalized poses with a parabolic CoM trajectory.

        Uses image coordinates: lower Y = higher person.
        During flight the CoM follows a parabola opening upward.
        """
        poses = np.full((n_frames, 17, 2), baseline_y, dtype=np.float32)
        # Put all keypoints at baseline so CoM ≈ baseline
        # During jump, shift PELVIS/HIP/KNEE to simulate CoM rising

        flight_start = takeoff_frame
        flight_end = landing_frame
        peak_frame = (flight_start + flight_end) // 2

        for f in range(flight_start, flight_end + 1):
            # Parabolic: y = a*(t-t0)^2 + peak_y, opens upward
            t = f - peak_frame
            half_span = max(1, (flight_end - flight_start) / 2.0)
            a = (baseline_y - peak_y) / (half_span**2)
            y = a * (t**2) + peak_y
            # Set all keypoints to this y to make CoM ≈ y
            poses[f, :, 1] = y
            # Keep x at baseline (doesn't affect CoM Y)
            poses[f, :, 0] = 0.5

        return poses

    def test_parabolic_detects_clean_jump(self):
        """Parabolic method should detect takeoff < peak < landing for clean jump."""
        detector = PhaseDetector()

        # 60-frame sequence with jump in frames 15-45
        poses = self._make_jump_poses(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
            peak_y=0.1,
            baseline_y=0.4,
        )

        result = detector._detect_jump_phases_parabolic(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing
        # Peak should be roughly in the middle of the jump
        assert 20 <= result.phases.peak <= 40

    def test_parabolic_ignores_prep_movement(self):
        """Parabolic method should ignore prep movements and find real jump.

        Frames 10-25: shoulder lean (flat CoM, not parabolic).
        Frames 40-55: real parabolic jump.
        Takeoff should be well past the prep (>= 30).
        """
        n = 70
        poses = np.full((n, 17, 2), 0.4, dtype=np.float32)
        poses[:, :, 0] = 0.5  # constant x

        # Preparation: frames 10-25 — slight shoulder lean but flat CoM
        for f in range(10, 26):
            # Move shoulders but keep hips (majority mass) at baseline
            poses[f, H36Key.LSHOULDER, 1] = 0.38
            poses[f, H36Key.RSHOULDER, 1] = 0.38
            poses[f, H36Key.LELBOW, 1] = 0.37
            poses[f, H36Key.RELBOW, 1] = 0.37
            # Hips, knees, feet stay at baseline → CoM barely moves

        # Real jump: frames 40-55 — parabolic CoM
        peak_y = 0.1
        baseline_y = 0.4
        flight_start, flight_end = 40, 55
        peak_frame = (flight_start + flight_end) // 2
        for f in range(flight_start, flight_end + 1):
            t = f - peak_frame
            half_span = max(1, (flight_end - flight_start) / 2.0)
            a = (baseline_y - peak_y) / (half_span**2)
            y = a * (t**2) + peak_y
            poses[f, :, 1] = y

        detector = PhaseDetector()
        result = detector._detect_jump_phases_parabolic(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        # Takeoff should be well past prep (frame 25)
        assert result.phases.takeoff >= 30
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing

    def test_parabolic_fallback_on_no_jump(self):
        """Flat poses should fallback to velocity method and still return a result."""
        detector = PhaseDetector()

        # Completely flat poses — no jump at all
        poses = np.full((50, 17, 2), 0.4, dtype=np.float32)
        poses[:, :, 0] = 0.5

        result = detector._detect_jump_phases_parabolic(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        # Should still return a valid result (fallback kicks in)
        assert result.phases is not None

    def test_parabolic_short_sequence(self):
        """Very short sequence should not crash."""
        detector = PhaseDetector()

        # Only 10 frames — too short for any real jump
        poses = np.full((10, 17, 2), 0.4, dtype=np.float32)
        poses[:, :, 0] = 0.5

        result = detector._detect_jump_phases_parabolic(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases is not None


class TestPhaseDetector3D:
    """Test PhaseDetector with 3D poses (Z-axis height)."""

    @staticmethod
    def _make_jump_poses_3d(
        n_frames: int,
        takeoff_frame: int,
        landing_frame: int,
        peak_z: float = 0.3,
        baseline_z: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Create 2D + 3D poses with a parabolic Z trajectory (height above ice).

        Z increases with height. During flight, CoM Z follows a parabola
        opening downward (gravity).
        """
        poses_2d = np.full((n_frames, 17, 2), 0.4, dtype=np.float32)
        poses_2d[:, :, 0] = 0.5

        poses_3d = np.zeros((n_frames, 17, 3), dtype=np.float32)
        poses_3d[:, :, 0] = 0.5  # x
        poses_3d[:, :, 1] = 0.4  # y (image coords, constant)
        poses_3d[:, :, 2] = baseline_z  # z (height)

        peak_frame = (takeoff_frame + landing_frame) // 2
        for f in range(takeoff_frame, landing_frame + 1):
            t = f - peak_frame
            half_span = max(1, (landing_frame - takeoff_frame) / 2.0)
            # Parabola opening downward: z = -a*t^2 + peak_z
            a = (peak_z - baseline_z) / (half_span**2)
            z = -a * (t**2) + peak_z
            poses_3d[f, :, 2] = z

        return poses_2d, poses_3d

    def test_3d_jump_phases_detected(self):
        """3D poses should detect jump phases using Z-axis height."""
        detector = PhaseDetector()

        poses_2d, poses_3d = self._make_jump_poses_3d(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
            peak_z=0.3,
            baseline_z=0.0,
        )

        result = detector.detect_jump_phases(poses_2d, fps=30.0, poses_3d=poses_3d)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing
        # Peak should be roughly in the middle
        assert 20 <= result.phases.peak <= 40

    def test_3d_improves_over_2d_flat_2d(self):
        """3D should work even when 2D Y-coords are flat (camera angle issue).

        In real skating videos, the camera may be at ice level, making Y-coords
        unreliable for height estimation. Z-axis from 3D lift fixes this.
        """
        detector = PhaseDetector()

        # 2D: completely flat Y (camera at ice level — no Y movement)
        poses_2d = np.full((60, 17, 2), 0.4, dtype=np.float32)
        poses_2d[:, :, 0] = 0.5

        # 3D: clear parabolic Z trajectory
        _, poses_3d = self._make_jump_poses_3d(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
            peak_z=0.3,
            baseline_z=0.0,
        )

        # With 3D, should detect the jump despite flat 2D
        result = detector.detect_jump_phases(poses_2d, fps=30.0, poses_3d=poses_3d)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing

    def test_detect_phases_passes_3d_to_jump(self):
        """detect_phases() should forward poses_3d to detect_jump_phases."""
        detector = PhaseDetector()

        poses_2d, poses_3d = self._make_jump_poses_3d(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
        )

        result = detector.detect_phases(poses_2d, fps=30.0, element_type="axel", poses_3d=poses_3d)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak


class TestCountRotations:
    """Test count_rotations standalone helper."""

    def test_count_rotations_from_flight_trajectory(self):
        """3 full turns over flight window should return 3."""
        angles = np.linspace(0, 3 * 2 * np.pi, 60)
        assert count_rotations(angles) == 3

    def test_count_rotations_zero_for_short(self):
        """Less than one full turn should return 0."""
        angles = np.linspace(0, 0.3 * 2 * np.pi, 30)
        assert count_rotations(angles) == 0

    def test_count_rotations_two_turns_negative_direction(self):
        """Counter-clockwise rotation should still count absolute turns."""
        angles = np.linspace(0, -2 * 2 * np.pi, 40)
        assert count_rotations(angles) == 2

    def test_count_rotations_with_wraparound(self):
        """Rotation crossing pi boundary should not be lost."""
        angles = np.array([3.0, 3.1, 3.2, -3.1, -3.0, -2.9])  # crosses +pi/-pi
        # unwrap fixes the discontinuity
        assert count_rotations(angles) == 0  # not even one full turn


class TestRotationCountingInJumpDetection:
    """Test that PhaseDetector correctly counts rotations during jumps."""

    @staticmethod
    def _make_rotating_jump_poses(
        n_frames: int = 60,
        takeoff_frame: int = 15,
        landing_frame: int = 45,
        rotations: int = 2,
        peak_y: float = 0.1,
        baseline_y: float = 0.4,
    ) -> np.ndarray:
        """Create normalized poses with parabolic CoM and shoulder rotation over detected flight window.

        Builds a base parabolic jump, detects the flight window, then overlays
        exactly `rotations` full shoulder turns over that detected window.
        This makes the test self-consistent regardless of the exact detector heuristics.
        """
        # Base parabolic jump
        poses = TestParabolicFlightDetector._make_jump_poses(
            n_frames=n_frames,
            takeoff_frame=takeoff_frame,
            landing_frame=landing_frame,
            peak_y=peak_y,
            baseline_y=baseline_y,
        )

        # Detect flight window on base poses
        detector = PhaseDetector()
        result = detector._detect_jump_phases_parabolic(poses, fps=30.0)
        t_off = result.phases.takeoff
        l_off = result.phases.landing

        # Overlay shoulder rotation over the detected flight window
        flight_indices = np.arange(t_off, l_off)
        if len(flight_indices) < 2:
            return poses

        rotation_angles = np.linspace(0, rotations * 2 * np.pi, len(flight_indices))
        shoulder_len = 0.15

        for idx, f in enumerate(flight_indices):
            theta = rotation_angles[idx]
            cx = 0.5
            cy = (poses[f, H36Key.LHIP, 1] + poses[f, H36Key.RHIP, 1]) / 2.0
            # Left shoulder
            poses[f, H36Key.LSHOULDER, 0] = cx - (shoulder_len / 2) * np.cos(theta)
            poses[f, H36Key.LSHOULDER, 1] = cy - (shoulder_len / 2) * np.sin(theta)
            # Right shoulder
            poses[f, H36Key.RSHOULDER, 0] = cx + (shoulder_len / 2) * np.cos(theta)
            poses[f, H36Key.RSHOULDER, 1] = cy + (shoulder_len / 2) * np.sin(theta)

        return poses

    def test_rotations_detected_for_double_jump(self):
        """A jump with 2 full shoulder rotations should report rotations=2."""
        detector = PhaseDetector()
        poses = self._make_rotating_jump_poses(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
            rotations=2,
        )

        result = detector.detect_jump_phases(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing
        assert result.rotations == 2

    def test_rotations_detected_for_single_jump(self):
        """A jump with 1 full shoulder rotation should report rotations=1."""
        detector = PhaseDetector()
        poses = self._make_rotating_jump_poses(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
            rotations=1,
        )

        result = detector.detect_jump_phases(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.phases.takeoff < result.phases.peak
        assert result.phases.peak < result.phases.landing
        assert result.rotations == 1

    def test_rotations_zero_for_non_rotating_jump(self):
        """A jump with no shoulder rotation should report rotations=0."""
        detector = PhaseDetector()
        # Reuse parabolic fixture (no rotation)
        from tests.analysis.test_phase_detector import TestParabolicFlightDetector

        poses = TestParabolicFlightDetector._make_jump_poses(
            n_frames=60,
            takeoff_frame=15,
            landing_frame=45,
        )

        result = detector.detect_jump_phases(poses, fps=30.0)

        assert isinstance(result, PhaseDetectionResult)
        assert result.rotations == 0

    def test_rotations_populated_in_detect_phases(self):
        """detect_phases() should surface rotations for jump element types."""
        detector = PhaseDetector()
        poses = self._make_rotating_jump_poses(rotations=3)

        result = detector.detect_phases(poses, fps=30.0, element_type="lutz")

        assert isinstance(result, PhaseDetectionResult)
        assert result.rotations == 3


# --- prod-ready-audit repro (M2) ---
# This test is RED-by-design: it proves the parabolic segment-merge in
# _detect_jump_phases_parabolic (ml/src/analysis/phase_detector.py:339)
# uses the WRONG metric. The comment at line ~330 says "gap < 3 frames" but
# the expression `(i - segments[-1][1]) < 3` measures
# (first_non_elevated_frame - last_segment_end) = gap + 1 + current_run_length,
# which is NEVER < 3 for any non-trivial run. So two close elevated segments
# separated by a 1-frame dip that should be ONE flight arc stay separate.
#
# Consequence: the detector fits a parabola to each short half separately
# instead of the full merged arc, so the detected flight window is too short.
# The test asserts the flight window spans BOTH segments (merged-arc length);
# with the bug it only spans one half -> RED.


class TestParabolicSegmentMergeGapMetric:
    """M2: parabolic segment-merge conflates gap+run length."""

    @staticmethod
    def _make_split_arc_poses(
        n_frames: int = 60,
        baseline_y: float = 0.40,
        peak_y: float = 0.10,
        seg1: tuple[int, int] = (10, 18),
        dip_frame: int = 19,
        seg2: tuple[int, int] = (20, 28),
    ) -> np.ndarray:
        """Two elevated runs of a single parabolic arc separated by a 1-frame dip.

        All 17 keypoints share the same Y per frame so CoM == that Y. The
        full arc is a parabola peaking at the centre of [seg1.start, seg2.end];
        the dip frame is exactly at baseline so it is NOT 'elevated' and
        triggers the merge branch.
        """
        poses = np.full((n_frames, 17, 2), baseline_y, dtype=np.float32)
        poses[:, :, 0] = 0.5

        full_start = seg1[0]
        full_end = seg2[1]
        peak_frame = (full_start + full_end) / 2.0
        half_span = max(1.0, (full_end - full_start) / 2.0)
        a = (baseline_y - peak_y) / (half_span**2)

        for f in range(full_start, full_end + 1):
            if f == dip_frame:
                # Exactly at baseline -> not elevated (the "gap" frame).
                y = baseline_y
            else:
                y = a * ((f - peak_frame) ** 2) + peak_y
            poses[f, :, 1] = y
        return poses

    def test_m2_close_elevated_segments_merge_into_one_flight(self):
        """M2: two elevated runs split by 1 frame must merge into ONE jump.

        With the bug, the merge check `(i - segments[-1][1]) < 3` evaluates to
        `(20 - 18) = 2 < 3`?? Wait: i is the FIRST non-elevated frame after the
        second run (i = seg2.end + 1 = 29), and segments[-1][1] is the end of
        the FIRST run (18). So `(29 - 18) = 11`, NOT < 3 -> segments stay
        separate. The detector fits a parabola to each ~8-frame half and the
        best one yields a short flight window. The merged arc would span
        ~18 frames (seg1.start..seg2.end). Assert airtime >= 14 frames.
        """
        detector = PhaseDetector()
        fps = 30.0
        poses = self._make_split_arc_poses(
            n_frames=60,
            baseline_y=0.40,
            peak_y=0.10,
            seg1=(10, 18),
            dip_frame=19,
            seg2=(20, 28),
        )

        result = detector._detect_jump_phases_parabolic(poses, fps=fps)

        assert isinstance(result, PhaseDetectionResult)
        airtime_frames = result.phases.landing - result.phases.takeoff
        # Merged arc spans frames 10..28 (18 frames). The 0.3s minimum-airtime
        # gate at fps=30 requires >= 9 frames, so a properly merged parabola
        # passes. Each separate half is ~8 frames (< 9) and would be rejected
        # by the airtime gate, forcing a fallback result with airtime < 14.
        assert airtime_frames >= 14, (
            f"M2: two elevated segments split by a 1-frame dip should merge "
            f"into one flight arc of >=14 frames, but the detector returned "
            f"airtime={airtime_frames} (takeoff={result.phases.takeoff}, "
            f"landing={result.phases.landing}). The segment-merge metric "
            f"`(i - segments[-1][1]) < 3` measures gap+run, not the pure gap."
        )


# --------------------------------------------------------------------------- #
# #425 — confidence inflated on flat/no-jump input (vy_std=0 -> NaN -> 0.5)
# --------------------------------------------------------------------------- #
class TestPhaseDetectorConfidenceInflate:
    def test_flat_input_zero_confidence_not_half(self):
        """A flat/no-jump input must report ~0 confidence, not 0.5.

        _detect_jump_phases_com_improved computed vy_std = std(vy) and divided
        by it. When vy is flat, vy_std == 0 -> 0/0 = NaN -> min(1.0, NaN) = 1.0
        in Python -> NaN-weighted velocity terms inflated to full weight ->
        ~0.5 confidence on a video with no jump. Sibling parabolic path
        guards with a 1e-6 threshold; the velocity-confidence path did not. #425
        """
        import warnings

        detector = PhaseDetector()
        # Flat poses with a tiny x drift (still no jump — com_y stays constant).
        poses = np.full((40, 17, 2), 0.5, dtype=np.float32)
        poses[:, :, 0] = np.tile(np.linspace(0.3, 0.7, 40)[:, None], (1, 17))

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = detector.detect_jump_phases(poses, fps=30.0)

        assert result.confidence < 0.1, (
            f"flat/no-jump input reports confidence={result.confidence} "
            "(vy_std=0 -> NaN-division -> min(1.0,NaN)=1.0 inflates terms); "
            "expected <0.1 since there is no jump"
        )
