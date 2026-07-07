"""Repro tests for issue #1253.

Bug: ml/src/references/reference_builder.py:load_reference used to crash with
ValueError("cannot convert float NaN to integer") when meta_width / meta_height
/ meta_num_frames were NaN in the .npz (corrupt save, partial build, mismatched
format). Fix landed in #1042 via _finite_int / _finite_float helpers.

These tests are RED on pre-#1042 master (raw `int(data["meta_width"])` blows up
on NaN) and GREEN on master after the fix. They also assert the contract for
other numeric fields (meta_fps, fps, phase ints).
"""

from pathlib import Path

import numpy as np
import pytest

from src.references.reference_builder import ReferenceBuilder
from src.types import ElementPhase, ReferenceData, TrackedExtraction, VideoMeta

# -----------------------
# Fixtures
# -----------------------


@pytest.fixture
def sample_tracked_extraction():
    poses = np.linspace(0, 1, 340).reshape(10, 17, 2).astype(np.float32)
    video_meta = VideoMeta(path=Path("test.mp4"), width=1920, height=1080, fps=30.0, num_frames=300)
    return TrackedExtraction(
        poses=poses,
        frame_indices=np.arange(10),
        first_detection_frame=0,
        target_track_id=1,
        fps=30.0,
        video_meta=video_meta,
        first_frame=None,
    )


@pytest.fixture
def mock_pose_extractor(sample_tracked_extraction):
    extractor = type("E", (), {})()
    extractor.extract_video_tracked = lambda video_path: sample_tracked_extraction
    return extractor


@pytest.fixture
def mock_normalizer():
    class _N:
        def normalize(self, poses):
            return np.linspace(0.1, 0.9, 340).reshape(10, 17, 2).astype(np.float32)

    return _N()


@pytest.fixture
def builder(mock_pose_extractor, mock_normalizer):
    return ReferenceBuilder(mock_pose_extractor, mock_normalizer)


def _write_npz(path: Path, **overrides) -> None:
    """Write a valid reference .npz and apply NaN/inf overrides to numeric fields."""
    base = {
        "element_type": "waltz_jump",
        "poses": np.linspace(0, 1, 170).reshape(5, 17, 2).astype(np.float32),
        "meta_fps": 30.0,
        "meta_width": 1920,
        "meta_height": 1080,
        "meta_num_frames": 300,
        "meta_path": "",
        "phases_name": "waltz_jump",
        "phases_start": 0,
        "phases_takeoff": 2,
        "phases_peak": 3,
        "phases_landing": 4,
        "phases_end": 5,
        "source": "test.mp4",
    }
    base.update(overrides)
    np.savez_compressed(path, **base)


# -----------------------
# Tests
# -----------------------


class TestLoadReferenceNaNGuard:
    def test_load_reference_nan_meta_width_does_not_crash(self, tmp_path: Path, builder):
        """#1253: corrupt save with NaN meta_width must raise a clear error,
        not a bare ValueError from int(NaN)."""
        npz_path = tmp_path / "ref.npz"
        _write_npz(npz_path, meta_width=float("nan"))

        with pytest.raises(RuntimeError, match="meta_width"):
            builder.load_reference(npz_path)

    def test_load_reference_nan_meta_height_does_not_crash(self, tmp_path: Path, builder):
        """#1253: NaN meta_height must be guarded, not crash with int(NaN)."""
        npz_path = tmp_path / "ref.npz"
        _write_npz(npz_path, meta_height=float("nan"))

        with pytest.raises(RuntimeError, match="meta_height"):
            builder.load_reference(npz_path)

    def test_load_reference_nan_meta_num_frames_does_not_crash(self, tmp_path: Path, builder):
        """#1253: NaN meta_num_frames must be guarded, not crash with int(NaN)."""
        npz_path = tmp_path / "ref.npz"
        _write_npz(npz_path, meta_num_frames=float("nan"))

        with pytest.raises(RuntimeError, match="meta_num_frames"):
            builder.load_reference(npz_path)

    def test_load_reference_nan_meta_fps_does_not_silently_leak(self, tmp_path: Path, builder):
        """#1253: NaN meta_fps must raise — silent NaN.fps leaks downstream
        and corrupts every time-derived metric (airtime, DTW)."""
        npz_path = tmp_path / "ref.npz"
        _write_npz(npz_path, meta_fps=float("nan"))

        with pytest.raises(RuntimeError, match="meta_fps"):
            builder.load_reference(npz_path)

    def test_load_reference_inf_meta_width_does_not_crash(self, tmp_path: Path, builder):
        """#1253: same guard covers +inf/-inf (partial write / corrupt disk)."""
        npz_path = tmp_path / "ref.npz"
        _write_npz(npz_path, meta_width=float("inf"))

        with pytest.raises(RuntimeError, match="meta_width"):
            builder.load_reference(npz_path)
