"""RED repro — TAS inference coarse/fine element_type inconsistency + hardcoded 1.0 confidence.

Covers #813 (Bug #180): when classifier is loaded, `element_type` is
overwritten from coarse ("Jump") to a fine label ("3Flip"); without a
classifier it stays coarse. Inconsistent return shape.
Covers #814 (Bug #181): without a classifier `confidence` is hardcoded to
1.0 — misleading 100% for every coarse-only segment.

Source: ml/src/tas/inference.py:113-135 (Tranche AL).
"""

import inspect
from pathlib import Path

import numpy as np
import torch

from src.tas.classifier import SegmentClassifier
from src.tas.inference import TASElementSegmenter
from src.tas.model import BiGRUTASRefiner

_COARSE = {"None", "Jump", "Spin", "Step"}


def _export_onnx(model: torch.nn.Module, path: str) -> None:
    """Export a BiGRUTASRefiner model to ONNX (legacy exporter)."""
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


def _make_segmenter(with_classifier: bool, onnx_path: str) -> TASElementSegmenter:
    """Build a segmenter that emits a long Jump segment, optionally with a classifier."""
    model = BiGRUTASRefiner(hidden_dim=32, num_layers=1, refiner_channels=16)
    model.eval()
    with torch.no_grad():
        model.refiner.classifier.bias.zero_()
        model.refiner.classifier.bias[1] = 10.0  # force all-Jump
    _export_onnx(model, onnx_path)

    classifier_path: str | None = None
    if with_classifier:
        clf = SegmentClassifier(n_estimators=10)
        clf.fit(
            [
                {
                    "features": {
                        "duration": 1.0,
                        "hip_y_range": 0.5,
                        "motion_energy": 0.1,
                        "rotation_speed": 200.0,
                        "num_frames": 30,
                    },
                    "label": "3Flip",
                }
            ]
        )
        classifier_path = "/tmp/test_tas_coarse_clf.joblib"
        import joblib

        joblib.dump(clf, classifier_path)

    return TASElementSegmenter(
        model_path=Path(onnx_path),
        classifier_path=classifier_path,
        device="cpu",
    )


def _jump_poses() -> np.ndarray:
    # 60 frames at 30fps = 2.0s > 0.5s Jump minimum -> kept
    return np.random.randn(60, 17, 2).astype(np.float32)


# ---------------------------------------------------------------------------
# #813 — coarse/fine element_type consistency
# ---------------------------------------------------------------------------


def test_inference_without_classifier_keeps_coarse_element_type():
    """Without classifier, element_type must be coarse (Jump/Spin/Step/None)."""
    seg = _make_segmenter(with_classifier=False, onnx_path="/tmp/test_tas_no_clf.onnx")
    segments = seg.segment(_jump_poses(), fps=30.0)
    assert len(segments) >= 1
    for s in segments:
        assert s["element_type"] in _COARSE, s
        # fine_label must exist and be None when no classifier
        assert "fine_label" in s, "fine_label field missing"
        assert s["fine_label"] is None, s


def test_inference_with_classifier_preserves_coarse_in_element_type():
    """With classifier, element_type stays coarse; fine label goes to fine_label."""
    seg = _make_segmenter(with_classifier=True, onnx_path="/tmp/test_tas_with_clf.onnx")
    segments = seg.segment(_jump_poses(), fps=30.0)
    assert len(segments) >= 1
    for s in segments:
        # element_type must stay coarse, NOT overwritten with fine label
        assert s["element_type"] in _COARSE, (
            f"element_type overwritten to fine label: {s['element_type']!r}"
        )
        # fine_label carries the classifier's fine prediction
        assert "fine_label" in s, "fine_label field missing"
        assert s["fine_label"] is not None, s


def test_inference_consistent_return_shape_both_paths():
    """Both classifier/no-classifier paths return the same set of keys."""
    seg_no_clf = _make_segmenter(with_classifier=False, onnx_path="/tmp/test_tas_a.onnx")
    seg_clf = _make_segmenter(with_classifier=True, onnx_path="/tmp/test_tas_b.onnx")
    poses = _jump_poses()

    no_clf_segs = seg_no_clf.segment(poses, fps=30.0)
    clf_segs = seg_clf.segment(poses, fps=30.0)
    assert no_clf_segs and clf_segs
    assert set(no_clf_segs[0].keys()) == set(clf_segs[0].keys()), (
        f"keys differ: no_clf={set(no_clf_segs[0].keys())} clf={set(clf_segs[0].keys())}"
    )


def test_inference_source_does_not_overwrite_element_type():
    """Source check: _try_add_segment must not assign a fine label to element_type."""
    src = inspect.getsource(TASElementSegmenter._try_add_segment)
    # The line that overwrites element_type with classifier output must NOT
    # assign back to element_type. The fix routes the fine label elsewhere.
    assert "element_type, confidence = self.classifier.predict" not in src, (
        "source still overwrites element_type with fine classifier label"
    )


# ---------------------------------------------------------------------------
# #814 — hardcoded confidence=1.0 without classifier
# ---------------------------------------------------------------------------


def test_inference_without_classifier_confidence_not_one():
    """Without classifier, confidence must NOT be the hardcoded 1.0."""
    seg = _make_segmenter(with_classifier=False, onnx_path="/tmp/test_tas_conf_no.onnx")
    segments = seg.segment(_jump_poses(), fps=30.0)
    assert len(segments) >= 1
    for s in segments:
        assert s["confidence"] != 1.0, (
            f"confidence hardcoded to 1.0 without classifier: {s['confidence']}"
        )
        assert 0.0 <= s["confidence"] <= 1.0, s


def test_inference_with_classifier_confidence_from_model():
    """With classifier, confidence comes from the classifier (in [0,1])."""
    seg = _make_segmenter(with_classifier=True, onnx_path="/tmp/test_tas_conf_yes.onnx")
    segments = seg.segment(_jump_poses(), fps=30.0)
    assert len(segments) >= 1
    for s in segments:
        assert 0.0 <= s["confidence"] <= 1.0, s
        # Single-class classifier is fully confident -> 1.0 is fine here,
        # this test only guards the range (model-derived).


def test_inference_source_no_hardcoded_one_confidence():
    """Source check: the literal `confidence = 1.0` default must be gone.

    Strip comments before checking — only the executable assignment matters.
    """
    import re

    src = inspect.getsource(TASElementSegmenter._try_add_segment)
    code_only = re.sub(r"#.*", "", src)
    assert "confidence = 1.0" not in code_only, (
        "source still hardcodes confidence = 1.0 as the no-classifier default"
    )


if __name__ == "__main__":
    # Standalone self-check — no pytest needed.
    test_inference_without_classifier_keeps_coarse_element_type()
    test_inference_with_classifier_preserves_coarse_in_element_type()
    test_inference_consistent_return_shape_both_paths()
    test_inference_source_does_not_overwrite_element_type()
    test_inference_without_classifier_confidence_not_one()
    test_inference_with_classifier_confidence_from_model()
    test_inference_source_no_hardcoded_one_confidence()
    print("ALL RED CHECKS RUN")
