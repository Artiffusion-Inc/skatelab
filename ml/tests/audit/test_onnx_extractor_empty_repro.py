"""RED repro: ONNXPoseExtractor.estimate_3d crashes on empty (0,17,2) poses.

Bug: estimate_3d (n_frames=0 <= temporal_window=81) → _infer_window →
np.concatenate([poses_2d, np.tile(poses_2d[-1:], (81,1,1))], axis=0).
poses_2d[-1:] is (0,17,2) (empty) → np.tile → (0,17,2) → concatenate
dimension mismatch ValueError.

Reachable via pose_preparation.py:155 + pipeline.py:243,1082 (no try/except)
on zero-valid-frame video → arq worker crash → 500 on /process.

TCPFormerExtractor.extract_sequence delegates to estimate_3d → same crash.
"""

import numpy as np

from src.pose_3d.onnx_extractor import ONNXPoseExtractor


def test_estimate_3d_empty_poses_no_crash():
    """estimate_3d must not crash on empty (0,17,2) input (zero valid frames)."""
    # Bypass __init__ (no ONNX model needed — crash is in pre-processing numpy,
    # at np.concatenate/np.tile BEFORE session.run is reached).
    extractor = ONNXPoseExtractor.__new__(ONNXPoseExtractor)
    extractor.temporal_window = 81
    extractor.session = None
    extractor.input_name = "x"

    empty = np.zeros((0, 17, 2), dtype=np.float32)

    raised = False
    exc: Exception | None = None
    try:
        result = extractor.estimate_3d(empty)
    except (ValueError, IndexError) as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG #1: ONNXPoseExtractor.estimate_3d crashes on empty (0,17,2) poses: "
        f"{type(exc).__name__ if exc else '?'}: {exc}. "
        f"_infer_window (onnx_extractor.py:184) np.concatenate([poses_2d, "
        f"np.tile(poses_2d[-1:], (81,1,1))], axis=0) — poses_2d[-1:] empty when "
        f"n_frames=0 → tile (0,17,2) → concatenate dimension mismatch ValueError. "
        f"Reachable via pose_preparation.py:155 / pipeline.py:243,1082 "
        f"(no try/except) on zero-valid-frame video → 500 on /process."
    )
