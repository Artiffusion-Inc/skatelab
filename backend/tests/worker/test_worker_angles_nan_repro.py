"""RED repro — compute_angles_batch silently propagates NaN via np.clip.

Bug (backend/app/worker.py:128-158, _compute_frame_metrics inner cosine):

    cos = np.clip(dot / (norm1 * norm2 + 1e-8), -1, 1)
    angles = np.degrees(np.arccos(cos))

If any keypoint in (a, b, c) is NaN, vec1/vec2 NaN → norm1/norm2 NaN → dot NaN
→ cos = NaN/(NaN*NaN+1e-8) = NaN → ``np.clip(NaN, -1, 1) = NaN`` silently.
Numpy clip does NOT catch NaN (unlike Python min/max). The post-mask at
worker.py:155-156 catches it downstream, but the inner math chain silently
propagates non-finite values through clip and arccos. Any future caller that
forgets the post-mask, or any intermediate debug print, leaks corrupt
values.

Fix: add an ``np.isfinite`` guard on the cosine term so the NaN handling is
explicit at the source, not deferred to a downstream mask. Same fix catches
degenerate (zero-norm) inputs that would otherwise produce a fake 90° from
``clip(0, -1, 1) = 0`` → ``arccos(0) = 90°``.

These tests are RED on master (clip silently masks NaN; degenerate input
produces fake 90°). GREEN after the isfinite guard is added.
"""

from __future__ import annotations

import sys
import warnings
from unittest.mock import MagicMock

import numpy as np
import pytest

# Mock aiobotocore before importing app.worker (which imports app.storage)
_mock_aiobotocore = MagicMock()
_mock_aiobotocore_session = MagicMock()
sys.modules["aiobotocore"] = _mock_aiobotocore
sys.modules["aiobotocore.session"] = _mock_aiobotocore_session

from app.worker import _compute_frame_metrics  # noqa: E402

from src.types import H36Key  # noqa: E402


def _make_poses(n_frames: int) -> np.ndarray:
    """Random valid (N, 17, 3) poses."""
    return np.random.rand(n_frames, 17, 3).astype(np.float32)


class TestComputeAnglesNaNGuard:
    """RED tests: NaN keypoints must propagate as NaN, not silent 90°."""

    def test_nan_keypoint_in_knee_produces_nan_angle(self):
        """NaN in RKNEE must yield NaN knee angle for that frame, not 90°.

        On master: cos = NaN via silent clip → arccos(NaN) = NaN → post-mask
        sets angle to NaN. PASS today. Kept as a baseline regression.
        """
        poses = _make_poses(3)
        poses[0, H36Key.RKNEE] = np.nan

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning becomes a failure
            result = _compute_frame_metrics(poses)

        # Frame 0: NaN keypoint -> NaN angle
        assert result["knee_angles_r"][0] is None
        # Other frames: valid
        assert result["knee_angles_r"][1] is not None
        assert result["knee_angles_r"][2] is not None

    def test_nan_in_hip_keypoint_does_not_silently_inject_into_angles(self):
        """A NaN in one chain must not contaminate the OTHER chain's angle.

        The post-mask is per-call. If hip_angles_r and hip_angles_l are
        computed separately, a NaN in thorax should NaN BOTH. We assert that
        no angle silently becomes a non-NaN finite value when ANY input
        keypoint for that angle is NaN.
        """
        poses = _make_poses(2)
        # NaN in thorax affects both hip_angles_r and hip_angles_l
        poses[0, H36Key.THORAX] = np.nan

        result = _compute_frame_metrics(poses)

        # Frame 0: thorax NaN -> both hip angles NaN
        assert result["hip_angles_r"][0] is None
        assert result["hip_angles_l"][0] is None
        # Frame 1: valid
        assert result["hip_angles_r"][1] is not None
        assert result["hip_angles_l"][1] is not None

    def test_degenerate_zero_norm_input_produces_nan_not_fake_90(self):
        """RED: b == a (zero-norm vec1) must yield NaN, not 90°.

        On master: vec1 = (0,0,0), norm1=0, dot=0,
        cos = 0 / (0*norm2 + 1e-8) = 0,
        np.clip(0, -1, 1) = 0, arccos(0) = 90° -> fake straight angle.

        After fix: isfinite guard on cos -> NaN -> NaN angle.
        """
        poses = np.zeros((1, 17, 3), dtype=np.float32)
        # Degenerate right knee: hip == knee -> vec1 = 0
        poses[0, H36Key.RHIP] = [0.0, 0.0, 0.0]
        poses[0, H36Key.RKNEE] = [0.0, 0.0, 0.0]  # same as hip
        poses[0, H36Key.RFOOT] = [0.0, -1.0, 0.0]
        # Left leg: valid straight line
        poses[0, H36Key.LHIP] = [0.0, 0.0, 0.0]
        poses[0, H36Key.LKNEE] = [0.0, -1.0, 0.0]
        poses[0, H36Key.LFOOT] = [0.0, -2.0, 0.0]

        result = _compute_frame_metrics(poses)

        # RED: master returns 90.0 here (fake). GREEN: None (NaN).
        assert result["knee_angles_r"][0] is None, (
            f"Degenerate input produced {result['knee_angles_r'][0]}° "
            "instead of NaN — np.clip(0) silently yields 90°."
        )
        # Valid leg unaffected
        assert result["knee_angles_l"][0] == pytest.approx(0.0, abs=1.0)

    def test_nan_does_not_trigger_arccos_runtime_warning(self):
        """RED: NaN propagation through arccos must not raise RuntimeWarning.

        On master: when keypoint is NaN, cos is NaN, arccos(NaN) returns
        NaN. With the fix (isfinite guard masking cos to NaN before arccos),
        behavior is identical but the source is explicit.
        """
        poses = _make_poses(2)
        poses[0, H36Key.RHIP] = np.nan

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _compute_frame_metrics(poses)

        # No angle is silently non-NaN for the corrupt frame
        assert result["knee_angles_r"][0] is None
        # No runtime warnings from arccos/divide
        for w in caught:
            assert not issubclass(w.category, RuntimeWarning), (
                f"arccos/divide emitted RuntimeWarning on NaN input: {w.message}"
            )

    def test_all_nan_keypoints_propagate_as_nan(self):
        """All-NaN pose yields NaN for all dependent metrics, not 90°/0°."""
        poses = np.full((2, 17, 3), np.nan, dtype=np.float32)

        result = _compute_frame_metrics(poses)

        for key in (
            "knee_angles_r",
            "knee_angles_l",
            "hip_angles_r",
            "hip_angles_l",
        ):
            for i in range(2):
                assert result[key][i] is None, f"{key}[{i}] = {result[key][i]} for all-NaN input"
