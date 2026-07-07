"""RED repro for issues #815 / #816 — ml/src/tas/metrics.py.

#815: OverlapF1 greedy matching must pick best-IoU, not first match.
#816: MultiOverlapF1 must extract segments ONCE, not N+1 times.
"""

import inspect

import numpy as np
import pytest

try:
    from ml.src.tas import metrics as tas_metrics
    from ml.src.tas.metrics import MultiOverlapF1, OverlapF1, _match_segments, _segment_iou
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from tas import metrics as tas_metrics  # type: ignore
    from tas.metrics import (  # type: ignore
        MultiOverlapF1,
        OverlapF1,
        _match_segments,
        _segment_iou,
    )


# ---------------------------------------------------------------------------
# #815 — best-IoU matching, not first-match
# ---------------------------------------------------------------------------


def test_overlapf1_source_no_break_uses_sorted_pairs():
    """The matching path (OverlapF1.compute + _match_segments) must not use
    first-match `break`; must build candidate pairs and sort by IoU descending
    (or use Hungarian)."""
    src = inspect.getsource(OverlapF1.compute) + inspect.getsource(_match_segments)
    assert "break" not in src, "OverlapF1 still uses first-match `break`"
    assert "sorted" in src or "argsort" in src or "linear_sum_assignment" in src, (
        "OverlapF1 matching must sort pairs by IoU desc or use Hungarian"
    )


def test_overlapf1_best_iou_selection_via_helper():
    """The matching path must select the higher-IoU pair when one pred matches
    two trues. We pass pre-extracted segments with true_A (lower IoU) listed
    FIRST, exposing the first-match bug directly.

    pred_A: overlaps true_A at 0.3 and true_B at 0.5.
    pred_B: overlaps ONLY true_A at 1.0.
    first-match: pred_A->true_A (first, 0.3>=thr). pred_B->true_A taken, no
      other -> FP. true_B unmatched -> FN. TP=1, precision=0.5, recall=0.5.
    best-IoU: pred_A->true_B (0.5>0.3). pred_B->true_A (1.0). TP=2, P=R=F1=1.0.
    """
    pred_segs = [
        {"label": "Jump", "start": 0, "end": 9},  # pred_A: IoU A=0.3, B=0.5
        {"label": "Jump", "start": 0, "end": 2},  # pred_B: IoU A=1.0, B=0
    ]
    true_segs = [
        {"label": "Jump", "start": 0, "end": 2},  # true_A (first, IoU 0.3 w/ pred_A)
        {"label": "Jump", "start": 5, "end": 9},  # true_B (IoU 0.5 w/ pred_A)
    ]
    assert _segment_iou(pred_segs[0], true_segs[0]) == pytest.approx(0.3)
    assert _segment_iou(pred_segs[0], true_segs[1]) == pytest.approx(0.5)
    assert _segment_iou(pred_segs[1], true_segs[0]) == pytest.approx(1.0)
    assert _segment_iou(pred_segs[1], true_segs[1]) == pytest.approx(0.0)

    r = _match_segments(pred_segs, true_segs, iou_threshold=0.3)
    assert r["precision"] == 1.0, f"best-IoU should match both preds: {r}"
    assert r["recall"] == 1.0, f"best-IoU should match both trues: {r}"
    assert r["f1"] == 1.0


def test_overlapf1_best_iou_vs_first_match_labels():
    """End-to-end via labels: one pred spanning two true segments of same label
    must match the higher-IoU true. Counts (TP/FP/FN) are invariant for a single
    pred, but the fix must not regress and must select the better pair.

    true: [1,1,1,0,0,1,1,1,1,1] -> true_A 0-2, true_B 5-9
    pred: [1,1,1,1,1,1,1,1,1,1] -> pred_A 0-9
    IoU(true_A)=3/10=0.3, IoU(true_B)=5/10=0.5, threshold=0.3.
    """
    true = np.array([1, 1, 1, 0, 0, 1, 1, 1, 1, 1])
    pred = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    metric = OverlapF1(iou_threshold=0.3)
    r = metric.compute(pred, true)
    # One pred, two matchable trues: TP=1, FP=0, FN=1.
    assert r["precision"] == 1.0
    assert r["recall"] == 0.5


# ---------------------------------------------------------------------------
# #816 — single extraction in MultiOverlapF1
# ---------------------------------------------------------------------------


def _make_counting_extract(monkeypatch):
    calls = {"count": 0}
    original = tas_metrics._extract_segments

    def counting_extract(labels, id2label):
        calls["count"] += 1
        return original(labels, id2label)

    monkeypatch.setattr(tas_metrics, "_extract_segments", counting_extract)
    return calls


def test_multioverlapf1_extracts_segments_once(monkeypatch):
    """3 thresholds -> exactly 2 _extract_segments calls (1 pred + 1 true),
    not 2 + 3*2 = 8."""
    calls = _make_counting_extract(monkeypatch)
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50], num_classes=4)
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2, 0, 1, 1])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2, 0, 1, 1])
    result = metric.compute(pred, true)
    assert calls["count"] == 2, (
        f"expected 2 _extract_segments calls, got {calls['count']} (N+1 bug: expected 8 on master)"
    )
    assert "f1@10" in result and "f1@25" in result and "f1@50" in result


def test_multioverlapf1_extracts_once_many_thresholds(monkeypatch):
    """Extraction count must NOT scale with number of thresholds."""
    calls = _make_counting_extract(monkeypatch)
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50, 0.75, 0.90], num_classes=4)
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2, 0, 1, 1])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2, 0, 1, 1])
    metric.compute(pred, true)
    assert calls["count"] == 2, (
        f"expected 2 calls for 5 thresholds, got {calls['count']} "
        f"(double-extraction: 2 + 5*2 = 12 expected on master)"
    )


def test_multioverlapf1_source_threads_segments():
    """MultiOverlapF1.compute must thread pre-extracted segments into the
    per-threshold path via _match_segments, not re-extract via
    OverlapF1().compute(raw labels)."""
    src = inspect.getsource(MultiOverlapF1.compute)
    assert "pred_segs" in src and "true_segs" in src
    assert "_match_segments" in src, (
        "MultiOverlapF1.compute must call _match_segments, not OverlapF1().compute(raw labels)"
    )


def test_overlapf1_uses_match_segments():
    """OverlapF1.compute must delegate to _match_segments (no first-match
    loop, no break)."""
    src = inspect.getsource(OverlapF1.compute)
    assert "_match_segments" in src, "OverlapF1.compute must call _match_segments"


# ---------------------------------------------------------------------------
# Regression — existing behaviour preserved
# ---------------------------------------------------------------------------


def test_overlapf1_perfect_match_unchanged():
    metric = OverlapF1(iou_threshold=0.5)
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    r = metric.compute(pred, true)
    assert r["f1"] == 1.0 and r["precision"] == 1.0 and r["recall"] == 1.0


def test_multioverlapf1_perfect_match_unchanged():
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50], num_classes=4)
    pred = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    true = np.array([0, 0, 1, 1, 1, 0, 2, 2])
    r = metric.compute(pred, true)
    assert r["f1@10"] == 1.0 and r["f1@25"] == 1.0 and r["f1@50"] == 1.0
