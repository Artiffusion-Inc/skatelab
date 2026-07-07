"""Temporal segmentation evaluation metrics.

OverlapF1: F1 score where a predicted segment matches a true segment
if their IoU >= threshold and labels match.
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.typing import NDArray


ID2LABEL = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}


def _extract_segments(labels: "NDArray", id2label: dict[int, str]) -> list[dict]:
    """Extract contiguous segments from frame-wise labels.

    Returns list of {label, start, end} dicts. Skips class 0 (None).

    #1094: NaN labels (missing GT annotation, blank cell in label CSV)
    used to crash `int(labels[i])` with ValueError. Guard every cast with
    `math.isfinite` — NaN/inf labels are skipped, treating them as a
    1-frame "not yet classified" gap inside the current segment.
    """
    segments: list[dict] = []
    if len(labels) == 0:
        return segments
    # #1094: NaN/inf labels are skipped — they become a 1-frame "not yet
    # classified" gap inside the current segment. Leading NaN means no
    # current segment yet; we start the loop with current=0 so the first
    # finite label is treated as a fresh start.
    start = 0
    current = 0 if not math.isfinite(labels[0]) else int(labels[0])
    for i in range(1, len(labels)):
        if not math.isfinite(labels[i]):
            continue  # NaN/inf frame — gap inside the current segment
        if int(labels[i]) != current:
            if current != 0:
                segments.append({"label": id2label[current], "start": start, "end": i - 1})
            current = int(labels[i])
            start = i
    # Last segment
    if current != 0:
        segments.append({"label": id2label[current], "start": start, "end": len(labels) - 1})
    return segments


def _segment_iou(seg1: dict, seg2: dict) -> float:
    """Compute IoU between two temporal segments."""
    s1, e1 = seg1["start"], seg1["end"]
    s2, e2 = seg2["start"], seg2["end"]
    inter_start = max(s1, s2)
    inter_end = min(e1, e2)
    inter = max(0, inter_end - inter_start + 1)
    union = (e1 - s1 + 1) + (e2 - s2 + 1) - inter
    return inter / union if union > 0 else 0.0


def _match_segments(
    pred_segs: list[dict],
    true_segs: list[dict],
    iou_threshold: float,
) -> dict[str, float]:
    """Match pred vs true segments by best IoU, return F1/precision/recall.

    Greedy by descending IoU: build all same-label candidate pairs above
    threshold, sort by IoU desc, assign while both sides are unmatched.
    Replaces the first-match-wins greedy that paired a pred with the FIRST
    unmatched true instead of the highest-IoU one (issue #815).
    Shared by OverlapF1 and MultiOverlapF1 so segments are extracted once
    (issue #816).
    """
    candidates: list[tuple[float, int, int]] = []
    for pi, ps in enumerate(pred_segs):
        for ti, ts in enumerate(true_segs):
            if ps["label"] != ts["label"]:
                continue
            iou = _segment_iou(ps, ts)
            if iou >= iou_threshold:
                candidates.append((iou, pi, ti))
    # ponytail: sorted-greedy by IoU desc — O(n log n), no scipy dep;
    # upgrade to linear_sum_assignment if pred/true counts grow large.
    candidates.sort(key=lambda c: c[0], reverse=True)

    matched_true: set[int] = set()
    matched_pred: set[int] = set()
    for _iou, pi, ti in candidates:
        if pi in matched_pred or ti in matched_true:
            continue
        matched_pred.add(pi)
        matched_true.add(ti)

    tp = len(matched_pred)
    fp = len(pred_segs) - tp
    fn = len(true_segs) - len(matched_true)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"f1": f1, "precision": precision, "recall": recall}


class OverlapF1:
    """Temporal segmentation evaluation: F1 with IoU >= threshold.

    Following AAAI 2021 MCFS paper.
    """

    def __init__(self, iou_threshold: float = 0.5, num_classes: int = 4) -> None:
        self.iou_threshold = iou_threshold
        self.num_classes = num_classes
        self.id2label = {i: ID2LABEL.get(i, f"Class{i}") for i in range(num_classes)}

    def compute(
        self,
        pred_labels: "NDArray",
        true_labels: "NDArray",
    ) -> dict[str, float]:
        """Compute OverlapF1 between predicted and true frame-wise labels.

        Args:
            pred_labels: (T,) predicted class indices
            true_labels: (T,) ground truth class indices

        Returns:
            Dict with 'f1', 'precision', 'recall'.
        """
        pred_segs = _extract_segments(pred_labels, self.id2label)
        true_segs = _extract_segments(true_labels, self.id2label)
        return _match_segments(pred_segs, true_segs, self.iou_threshold)


class MultiOverlapF1:
    """Evaluate at multiple IoU thresholds simultaneously.

    Returns F1, precision, recall at each threshold.
    """

    def __init__(self, thresholds: list[float] | None = None, num_classes: int = 4) -> None:
        self.thresholds = thresholds or [0.10, 0.25, 0.50]
        self.num_classes = num_classes
        self.id2label = {i: ID2LABEL.get(i, f"Class{i}") for i in range(num_classes)}

    def compute(
        self,
        pred_labels: "NDArray",
        true_labels: "NDArray",
    ) -> dict[str, float]:
        """Compute OverlapF1 at multiple IoU thresholds.

        Segments are extracted ONCE and reused across all thresholds (only the
        IoU threshold changes, not the segments).
        """
        pred_segs = _extract_segments(pred_labels, self.id2label)
        true_segs = _extract_segments(true_labels, self.id2label)

        result: dict[str, float] = {}
        for threshold in self.thresholds:
            tag = str(int(threshold * 100))
            single = _match_segments(pred_segs, true_segs, threshold)
            result[f"f1@{tag}"] = single["f1"]
            result[f"precision@{tag}"] = single["precision"]
            result[f"recall@{tag}"] = single["recall"]
        return result


__all__ = ["MultiOverlapF1", "OverlapF1", "_extract_segments", "_match_segments", "_segment_iou"]
