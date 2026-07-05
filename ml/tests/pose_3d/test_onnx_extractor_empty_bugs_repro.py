"""Repro tests for #622: ONNXPoseExtractor crashes on empty input.

Bug: _infer_window([]) and _infer_batch([[]]) raise ValueError because
padded array is shape (0, 17, 2) but conf is (w, 17, 1) — concat fails
on different length axes.

Contract: empty input must return empty output (N=0) without raising.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

# Load onnx_extractor directly to avoid pulling in cv2/numba chain
_HERE = Path(__file__).resolve()
_SRC_FILE = _HERE.parents[2] / "src" / "pose_3d" / "onnx_extractor.py"
_spec = importlib.util.spec_from_file_location("onnx_extractor_under_test", _SRC_FILE)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["onnx_extractor_under_test"] = _mod
_spec.loader.exec_module(_mod)
ONNXPoseExtractor = _mod.ONNXPoseExtractor


def _make_extractor(window: int = 27) -> ONNXPoseExtractor:
    """Build an extractor with a mocked ONNX session (no GPU/ort needed)."""
    extractor = ONNXPoseExtractor.__new__(ONNXPoseExtractor)
    extractor.temporal_window = window
    extractor.input_name = "input"

    # Mock session.run to return correct shape for (1, w, 17, 3)
    def fake_run(_outputs, _inputs):
        # Detect batch size and window from input
        inp = _inputs["input"]
        bsz, w_dim = inp.shape[0], inp.shape[1]
        return [np.zeros((bsz, w_dim, 17, 3), dtype=np.float32)]

    extractor.session = MagicMock()
    extractor.session.run.side_effect = fake_run
    return extractor


def test_infer_window_empty_returns_empty():
    """_infer_window([]) must return (0, 17, 3) without raising."""
    extractor = _make_extractor(window=27)
    out = extractor._infer_window(np.zeros((0, 17, 2), dtype=np.float32))
    assert out.shape == (0, 17, 3)
    assert out.dtype == np.float32


def test_infer_batch_with_empty_window():
    """_infer_batch([[]]) must return list with one (0, 17, 3) array."""
    extractor = _make_extractor(window=27)
    out = extractor._infer_batch([np.zeros((0, 17, 2), dtype=np.float32)])
    assert len(out) == 1
    assert out[0].shape == (0, 17, 3)


def test_estimate_3d_empty_returns_empty():
    """estimate_3d of empty array must return empty array."""
    extractor = _make_extractor(window=27)
    out = extractor.estimate_3d(np.zeros((0, 17, 2), dtype=np.float32))
    assert out.shape == (0, 17, 3)
