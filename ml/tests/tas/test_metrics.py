"""Tests for TAS metrics."""

import numpy as np
import pytest

try:
    from ml.src.tas.metrics import OverlapF1, _extract_segments, _segment_iou
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from tas.metrics import OverlapF1, _extract_segments, _segment_iou


def test_extract_segments_basic():
    labels = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    id2label = {0: "None", 1: "Jump", 2: "Spin"}
    segs = _extract_segments(labels, id2label)
    assert len(segs) == 2
    assert segs[0] == {"label": "Jump", "start": 2, "end": 4}
    assert segs[1] == {"label": "Spin", "start": 6, "end": 7}


def test_extract_segments_empty():
    assert _extract_segments(np.array([], dtype=np.int64), {0: "None"}) == []


def test_extract_segments_all_none():
    labels = np.array([0, 0, 0, 0])
    id2label = {0: "None", 1: "Jump"}
    segs = _extract_segments(labels, id2label)
    assert segs == []


def test_segment_iou_perfect():
    s1 = {"start": 2, "end": 5, "label": "Jump"}
    s2 = {"start": 2, "end": 5, "label": "Jump"}
    assert _segment_iou(s1, s2) == 1.0


def test_segment_iou_partial():
    s1 = {"start": 2, "end": 5, "label": "Jump"}  # 4 frames
    s2 = {"start": 3, "end": 6, "label": "Jump"}  # 4 frames
    # inter: 3-5 = 3 frames, union: 4+4-3 = 5
    assert _segment_iou(s1, s2) == 3 / 5


def test_segment_iou_no_overlap():
    s1 = {"start": 0, "end": 2, "label": "Jump"}
    s2 = {"start": 5, "end": 8, "label": "Jump"}
    assert _segment_iou(s1, s2) == 0.0


def test_overlapf1_perfect_match():
    metric = OverlapF1(iou_threshold=0.5)
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    result = metric.compute(pred, true)
    assert result["f1"] == 1.0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0


def test_overlapf1_partial_iou():
    metric = OverlapF1(iou_threshold=0.5)
    # True: Jump frames 2-6 (5 frames)
    # Pred: Jump frames 4-5 (2 frames), IoU = 2/5 = 0.4 < 0.5 -> no match
    pred = np.array([0, 0, 0, 0, 1, 1, 0, 0])
    true = np.array([0, 0, 1, 1, 1, 1, 1, 0])
    result = metric.compute(pred, true)
    assert result["f1"] < 1.0
    assert result["precision"] < 1.0
    assert result["recall"] < 1.0


def test_overlapf1_wrong_label():
    metric = OverlapF1(iou_threshold=0.5)
    pred = np.array([0, 0, 2, 2, 2, 0, 0])  # Spin
    true = np.array([0, 0, 1, 1, 1, 0, 0])  # Jump
    result = metric.compute(pred, true)
    assert result["f1"] == 0.0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0


def test_multi_overlap_f1():
    from ml.src.tas.metrics import MultiOverlapF1

    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    result = metric.compute(pred, true)
    assert "f1@10" in result
    assert "f1@25" in result
    assert "f1@50" in result
    assert result["f1@10"] == 1.0
    assert result["f1@25"] == 1.0
    assert result["f1@50"] == 1.0


def test_multi_overlap_f1_partial():
    from ml.src.tas.metrics import MultiOverlapF1

    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])
    pred = np.array([0, 0, 0, 0, 1, 1, 0, 0])
    true = np.array([0, 0, 1, 1, 1, 1, 1, 0])
    result = metric.compute(pred, true)
    # F1@10 should be higher than or equal to F1@50 (looser threshold)
    assert result["f1@10"] >= result["f1@50"]


if __name__ == "__main__":
    test_extract_segments_basic()
    print("✓ extract_segments_basic OK")
    test_extract_segments_empty()
    print("✓ extract_segments_empty OK")
    test_extract_segments_all_none()
    print("✓ extract_segments_all_none OK")
    test_segment_iou_perfect()
    print("✓ segment_iou_perfect OK")
    test_segment_iou_partial()
    print("✓ segment_iou_partial OK")
    test_segment_iou_no_overlap()
    print("✓ segment_iou_no_overlap OK")
    test_overlapf1_perfect_match()
    print("✓ overlapf1_perfect_match OK")
    test_overlapf1_partial_iou()
    print("✓ overlapf1_partial_iou OK")
    test_overlapf1_wrong_label()
    print("✓ overlapf1_wrong_label OK")
    print("ALL METRIC TESTS PASSED")
