"""Shared pytest fixtures and configuration."""

import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

# Fix tqdm.__spec__ missing in CI pytest collection.
# Must run BEFORE any import that transitively imports tqdm.
try:
    import tqdm

    if getattr(tqdm, "__spec__", None) is None:
        tqdm.__spec__ = ModuleSpec("tqdm", None)
        tqdm.__spec__.origin = None
        tqdm.__spec__.submodule_search_locations = None
except (ImportError, ValueError):
    # Create a mock tqdm module with __spec__ so downstream imports work.
    _fake_tqdm = types.ModuleType("tqdm")
    _fake_tqdm.__spec__ = ModuleSpec("tqdm", None)
    _fake_tqdm.__spec__.origin = None
    _fake_tqdm.__spec__.submodule_search_locations = None

    def _tqdm(iterable=None, **_kwargs):
        if iterable is not None:
            return iterable
        return type(
            "_TqdmMock",
            (),
            {
                "update": lambda *_a: None,
                "close": lambda *_a: None,
                "__enter__": lambda s: s,
                "__exit__": lambda *_a: None,
            },
        )()

    _fake_tqdm.tqdm = _tqdm
    sys.modules["tqdm"] = _fake_tqdm

# Add ml to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from src.types import H36Key


@pytest.fixture
def sample_frame():
    """Create a sample video frame (640x480x3 BGR)."""
    # Create gradient pattern
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    for i in range(480):
        frame[i, :] = i * 255 // 480
    return frame


@pytest.fixture
def sample_keypoints():
    """Create sample H3.6M 17-keypoint 3D pose for testing."""
    # 17 keypoints in simple T-pose configuration (x, y, z in meters)
    keypoints = np.zeros((1, 17, 3), dtype=np.float32)

    # Root/Hips
    keypoints[0, H36Key.HIP_CENTER, :] = [0.0, 0.0, 0.0]  # Origin
    keypoints[0, H36Key.RHIP, :] = [-0.1, 0.0, 0.0]
    keypoints[0, H36Key.LHIP, :] = [0.1, 0.0, 0.0]
    keypoints[0, H36Key.RKNEE, :] = [-0.1, -0.4, 0.0]
    keypoints[0, H36Key.LKNEE, :] = [0.1, -0.4, 0.0]
    keypoints[0, H36Key.RFOOT, :] = [-0.1, -0.8, 0.0]
    keypoints[0, H36Key.LFOOT, :] = [0.1, -0.8, 0.0]

    # Torso/Spine
    keypoints[0, H36Key.SPINE, :] = [0.0, 0.2, 0.0]
    keypoints[0, H36Key.THORAX, :] = [0.0, 0.3, 0.0]
    keypoints[0, H36Key.NECK, :] = [0.0, 0.4, 0.0]
    keypoints[0, H36Key.HEAD, :] = [0.0, 0.5, 0.0]

    # Arms (from thorax in H3.6M)
    keypoints[0, H36Key.RSHOULDER, :] = [-0.15, 0.3, 0.0]
    keypoints[0, H36Key.RELBOW, :] = [-0.2, 0.15, 0.0]
    keypoints[0, H36Key.RWRIST, :] = [-0.22, 0.0, 0.0]
    keypoints[0, H36Key.LSHOULDER, :] = [0.15, 0.3, 0.0]
    keypoints[0, H36Key.LELBOW, :] = [0.2, 0.15, 0.0]
    keypoints[0, H36Key.LWRIST, :] = [0.22, 0.0, 0.0]

    return keypoints


@pytest.fixture
def sample_normalized_poses():
    """Create sample normalized poses (T-pose, 3 frames) with 33 BlazePose keypoints."""
    poses = np.zeros((3, 33, 2), dtype=np.float32)

    # Centered at origin, scale = 1
    for i in range(3):
        # Hips at origin
        poses[i, H36Key.LEFT_HIP] = [-0.05, 0.0]
        poses[i, H36Key.RIGHT_HIP] = [0.05, 0.0]

        # Shoulders above (negative Y = up in image coords)
        poses[i, H36Key.LEFT_SHOULDER] = [-0.1, -0.3]
        poses[i, H36Key.RIGHT_SHOULDER] = [0.1, -0.3]

        # Elbows
        poses[i, H36Key.LEFT_ELBOW] = [-0.15, -0.5]
        poses[i, H36Key.RIGHT_ELBOW] = [0.15, -0.5]

        # Wrists
        poses[i, H36Key.LEFT_WRIST] = [-0.2, -0.7]
        poses[i, H36Key.RIGHT_WRIST] = [0.2, -0.7]

        # Knees
        poses[i, H36Key.LEFT_KNEE] = [-0.05, 0.3]
        poses[i, H36Key.RIGHT_KNEE] = [0.05, 0.3]

        # Ankles
        poses[i, H36Key.LEFT_ANKLE] = [-0.05, 0.6]
        poses[i, H36Key.RIGHT_ANKLE] = [0.05, 0.6]

        # Heels and foot index (for edge detection)
        poses[i, H36Key.LEFT_HEEL] = [-0.08, 0.6]
        poses[i, H36Key.RIGHT_HEEL] = [0.08, 0.6]
        poses[i, H36Key.LEFT_FOOT_INDEX] = [-0.02, 0.65]
        poses[i, H36Key.RIGHT_FOOT_INDEX] = [0.02, 0.65]

    return poses


@pytest.fixture
def temp_video_file(tmp_path: Path):
    """Create a temporary test video file path."""
    return tmp_path / "test_video.mp4"


@pytest.fixture
def temp_output_dir(tmp_path: Path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


class SyntheticPoseFactory:
    """Create H3.6M 17kp poses with analytically known angles."""

    @staticmethod
    def make_standing_pose(n_frames: int = 10) -> np.ndarray:
        """Standing pose: straight legs (180°), upright trunk. Shape: (n_frames, 17, 2)."""
        poses = np.zeros((n_frames, 17, 2), dtype=np.float32)
        poses[:, H36Key.HIP_CENTER] = [0.5, 0.5]
        poses[:, H36Key.RHIP] = [0.48, 0.52]
        poses[:, H36Key.RKNEE] = [0.48, 0.62]
        poses[:, H36Key.RFOOT] = [0.48, 0.72]
        poses[:, H36Key.LHIP] = [0.52, 0.52]
        poses[:, H36Key.LKNEE] = [0.52, 0.62]
        poses[:, H36Key.LFOOT] = [0.52, 0.72]
        poses[:, H36Key.SPINE] = [0.5, 0.45]
        poses[:, H36Key.THORAX] = [0.5, 0.4]
        poses[:, H36Key.NECK] = [0.5, 0.35]
        poses[:, H36Key.HEAD] = [0.5, 0.3]
        poses[:, H36Key.LSHOULDER] = [0.45, 0.4]
        poses[:, H36Key.LELBOW] = [0.43, 0.48]
        poses[:, H36Key.LWRIST] = [0.42, 0.55]
        poses[:, H36Key.RSHOULDER] = [0.55, 0.4]
        poses[:, H36Key.RELBOW] = [0.57, 0.48]
        poses[:, H36Key.RWRIST] = [0.58, 0.55]
        return poses

    @staticmethod
    def make_rotation_sequence(
        n_rotations: float = 2.0, n_frames: int = 120, fps: int = 30
    ) -> np.ndarray:
        """3D poses with constant shoulder-axis rotation. Shape: (n_frames, 17, 3)."""
        poses = np.zeros((n_frames, 17, 3), dtype=np.float32)
        total_angle = n_rotations * 2 * np.pi
        for f in range(n_frames):
            t = f / max(n_frames - 1, 1)
            angle = total_angle * t
            cx, cz = 0.0, 0.0
            shoulder_half = 0.2
            l_sho_x = cx - shoulder_half * np.cos(angle)
            l_sho_z = cz - shoulder_half * np.sin(angle)
            r_sho_x = cx + shoulder_half * np.cos(angle)
            r_sho_z = cz + shoulder_half * np.sin(angle)
            poses[f, H36Key.LSHOULDER] = [l_sho_x, 0.4, l_sho_z]
            poses[f, H36Key.RSHOULDER] = [r_sho_x, 0.4, r_sho_z]
            poses[f, H36Key.HIP_CENTER] = [0, 0.5, 0]
            poses[f, H36Key.RHIP] = [-0.02, 0.52, 0]
            poses[f, H36Key.RKNEE] = [-0.02, 0.62, 0]
            poses[f, H36Key.RFOOT] = [-0.02, 0.72, 0]
            poses[f, H36Key.LHIP] = [0.02, 0.52, 0]
            poses[f, H36Key.LKNEE] = [0.02, 0.62, 0]
            poses[f, H36Key.LFOOT] = [0.02, 0.72, 0]
            poses[f, H36Key.SPINE] = [0, 0.45, 0]
            poses[f, H36Key.THORAX] = [0, 0.4, 0]
            poses[f, H36Key.NECK] = [0, 0.35, 0]
            poses[f, H36Key.HEAD] = [0, 0.3, 0]
            poses[f, H36Key.LELBOW] = [l_sho_x - 0.02, 0.48, l_sho_z]
            poses[f, H36Key.LWRIST] = [l_sho_x - 0.03, 0.55, l_sho_z]
            poses[f, H36Key.RELBOW] = [r_sho_x + 0.02, 0.48, r_sho_z]
            poses[f, H36Key.RWRIST] = [r_sho_x + 0.03, 0.55, r_sho_z]
        return poses

    @staticmethod
    def make_spread_eagle_pose(angle_deg: float = 160.0, n_frames: int = 10) -> np.ndarray:
        """Pose with specific bilateral leg angle. Shape: (n_frames, 17, 2)."""
        poses = np.zeros((n_frames, 17, 2), dtype=np.float32)
        half_angle = np.radians(angle_deg / 2)
        leg_len = 0.1
        hip_center = np.array([0.5, 0.5])
        poses[:, H36Key.RHIP] = hip_center + np.array([-0.02, 0.02])
        poses[:, H36Key.RKNEE] = poses[:, H36Key.RHIP] + np.array(
            [leg_len * np.sin(half_angle), leg_len * np.cos(half_angle)]
        )
        poses[:, H36Key.RFOOT] = poses[:, H36Key.RKNEE] + np.array(
            [leg_len * np.sin(half_angle) * 0.5, leg_len * np.cos(half_angle) * 0.5]
        )
        poses[:, H36Key.LHIP] = hip_center + np.array([0.02, 0.02])
        poses[:, H36Key.LKNEE] = poses[:, H36Key.LHIP] + np.array(
            [-leg_len * np.sin(half_angle), leg_len * np.cos(half_angle)]
        )
        poses[:, H36Key.LFOOT] = poses[:, H36Key.LKNEE] + np.array(
            [-leg_len * np.sin(half_angle) * 0.5, leg_len * np.cos(half_angle) * 0.5]
        )
        poses[:, H36Key.HIP_CENTER] = hip_center
        poses[:, H36Key.SPINE] = hip_center + np.array([0, -0.05])
        poses[:, H36Key.THORAX] = hip_center + np.array([0, -0.1])
        poses[:, H36Key.NECK] = hip_center + np.array([0, -0.15])
        poses[:, H36Key.HEAD] = hip_center + np.array([0, -0.2])
        poses[:, H36Key.LSHOULDER] = poses[:, H36Key.THORAX] + np.array([-0.05, 0])
        poses[:, H36Key.RSHOULDER] = poses[:, H36Key.THORAX] + np.array([0.05, 0])
        poses[:, H36Key.LELBOW] = poses[:, H36Key.LSHOULDER] + np.array([-0.02, 0.08])
        poses[:, H36Key.LWRIST] = poses[:, H36Key.LELBOW] + np.array([0, 0.07])
        poses[:, H36Key.RELBOW] = poses[:, H36Key.RSHOULDER] + np.array([0.02, 0.08])
        poses[:, H36Key.RWRIST] = poses[:, H36Key.RELBOW] + np.array([0, 0.07])
        return poses

    @staticmethod
    def make_ina_bauer_pose(
        leg_spread_deg: float = 160.0,
        lean_deg: float = 30.0,
        knee_diff_deg: float = 30.0,
        n_frames: int = 10,
    ) -> np.ndarray:
        """Ina Bauer pose with backward lean, one knee bent. Shape: (n_frames, 17, 2)."""
        poses = SyntheticPoseFactory.make_spread_eagle_pose(
            angle_deg=leg_spread_deg, n_frames=n_frames
        )
        knee_angle_rad = np.radians(180 - knee_diff_deg)
        r_knee = poses[0, H36Key.RKNEE].copy()
        r_foot_base = poses[0, H36Key.RFOOT].copy()
        knee_to_foot = r_foot_base - r_knee
        cos_a = np.cos(knee_angle_rad)
        sin_a = np.sin(knee_angle_rad)
        rotated = np.array(
            [
                knee_to_foot[0] * cos_a - knee_to_foot[1] * sin_a,
                knee_to_foot[0] * sin_a + knee_to_foot[1] * cos_a,
            ]
        )
        for f in range(n_frames):
            poses[f, H36Key.RFOOT] = poses[f, H36Key.RKNEE] + rotated
        lean_rad = np.radians(lean_deg)
        hip_center = poses[0, H36Key.HIP_CENTER].copy()
        trunk_lean = np.array([0.1 * np.sin(lean_rad), -0.1 * np.cos(lean_rad)])
        for f in range(n_frames):
            poses[f, H36Key.THORAX] = hip_center + trunk_lean
            poses[f, H36Key.NECK] = poses[f, H36Key.THORAX] + trunk_lean * 0.5
            poses[f, H36Key.HEAD] = poses[f, H36Key.NECK] + trunk_lean * 0.3
            poses[f, H36Key.LSHOULDER] = poses[f, H36Key.THORAX] + np.array([-0.05, 0])
            poses[f, H36Key.RSHOULDER] = poses[f, H36Key.THORAX] + np.array([0.05, 0])
        return poses
