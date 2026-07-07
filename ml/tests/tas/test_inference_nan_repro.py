"""Regression tests for issue #1209: TASElementSegmenter._extract_segments NaN crash.

Original bug: `int(labels[i])` at lines 85/88/93 of `ml/src/tas/inference.py`
raised `ValueError: cannot convert float NaN to integer` when the BiGRU
classifier emitted NaN labels (degenerate confidence, NaN pose features,
padding frames). Guard every cast with `math.isfinite` so NaN/inf labels
are skipped, treating them as a 1-frame "not yet classified" gap inside
the current segment.

These tests exercise the public surface (segmenter.segment) and the
internal _extract_segments path directly with synthetic label arrays.
"""  # noqa: E501

from pathlib import Path

import numpy as np
import pytest
import torch

try:
    from ml.src.tas.inference import TASElementSegmenter
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from tas.inference import TASElementSegmenter

from src.tas.model import BiGRUTASRefiner


def _export_onnx(model: torch.nn.Module, path: str) -> None:
    """Export a BiGRUTASRefiner model to ONNX."""
    model.eval()
    dummy_poses = torch.randn(1, 50, 17, 2)
    dummy_lengths = torch.tensor([50], dtype=torch.long)
    torch.onnx.export(
        model,
        (dummy_poses, dummy_lengths),
        path,
        input_names=["poses", "lengths"],
        output_names=["logits"],
        dynamic_axes={
            "poses": {0: "batch", 1: "time"},
            "lengths": {0: "batch"},
            "logits": {0: "batch", 1: "time"},
        },
        opset_version=17,
        dynamo=False,
    )


@pytest.fixture
def segmenter():
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    onnx_path = "/tmp/test_tas_nan_repro.onnx"
    _export_onnx(model, onnx_path)
    return TASElementSegmenter(
        model_path=Path(onnx_path),
        classifier_path=None,
        device="cpu",
    )


def _make_poses(n_frames: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n_frames, 17, 2)).astype(np.float32)


# ---------- 1) Direct _extract_segments: NaN in middle of label stream ----------


def test_extract_segments_nan_in_middle_does_not_crash(segmenter):
    """Leading-NaN labels used to crash `int(labels[0])` at line 85.

    After fix: NaN labels are treated as 1-frame gaps inside the current
    segment. Leading NaN → no current segment yet, first finite label
    becomes a fresh start.
    """
    # 30 frames: 5 NaN, then 25 frames of class 1 (Jump).
    # 25 frames @ 30fps = 0.833s > 0.5s Jump min → kept.
    labels = np.array(
        [np.nan] * 5 + [1] * 25,
        dtype=np.float64,
    )
    poses = _make_poses(30)
    segs = segmenter._extract_segments(labels, poses, fps=30.0)
    assert isinstance(segs, list)
    # Should keep the Jump segment (1.0s after min-duration filter)
    assert any(s["element_type"] == "Jump" for s in segs)


def test_extract_segments_nan_at_end_does_not_crash(segmenter):
    """Trailing-NaN labels used to crash `int(labels[i])` at line 88/93."""
    # 50 frames of class 1, then 10 NaN at the end. The Jump segment
    # (50 frames @ 30fps = 1.667s) is valid; trailing NaN frames must
    # not crash and must not extend or break the segment.
    labels = np.array([1] * 50 + [np.nan] * 10, dtype=np.float64)
    poses = _make_poses(60)
    segs = segmenter._extract_segments(labels, poses, fps=30.0)
    assert any(s["element_type"] == "Jump" for s in segs)


# ---------- 2) Direct _extract_segments: infinity labels ----------


def test_extract_segments_inf_does_not_crash(segmenter):
    """Inf labels (e.g. logit overflow in upstream classifier) are also
    non-finite and must be skipped, not coerced to int.
    """
    labels = np.array([np.inf, 1, 1, 1, 1, 1, 1, 1, 1, 1, -np.inf], dtype=np.float64)
    poses = _make_poses(11)
    # Must not raise
    segs = segmenter._extract_segments(labels, poses, fps=30.0)
    assert isinstance(segs, list)


# ---------- 3) Public segment() entry point: NaN fed via internal model output ----------


def test_segment_returns_list_for_finite_input(segmenter):
    """Baseline: standard random poses produce a list (no crash, no NaN
    path triggered by the random model output here)."""
    poses = _make_poses(60, seed=42)
    segs = segmenter.segment(poses, fps=30.0)
    assert isinstance(segs, list)


# ---------- 4) Source-level check: math.isfinite present in _extract_segments ----------


def test_source_uses_math_isfinite_guard():
    """Regression guard: _extract_segments must call math.isfinite on
    every label before int() conversion. This locks in the fix so a
    refactor doesn't silently remove the NaN guard.
    """
    import inspect

    from ml.src.tas.inference import TASElementSegmenter  # noqa: F401

    src = inspect.getsource(TASElementSegmenter._extract_segments)
    assert "math.isfinite" in src, (
        "_extract_segments lost its math.isfinite NaN guard — "
        "NaN labels will crash int(labels[i]) again (issue #1209)"
    )


if __name__ == "__main__":
    print("run via: pytest ml/tests/tas/test_inference_nan_repro.py -v")
