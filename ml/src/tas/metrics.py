"""Temporal segmentation evaluation metrics.

OverlapF1: F1 score where a predicted segment matches a true segment
if their IoU >= threshold and labels match.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.typing import NDArray


ID2LABEL = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}


def _extract_segments(labels: "NDArray", id2label: dict[int, str]) -> list[dict]:
    """Extract contiguous segments from frame-wise labels.

    Returns list of {label, start, end} dicts. Skips class 0 (None).
    """
    segments: list[dict] = []
    if len(labels) == 0:
        return segments
    current = int(labels[0])
    start = 0
    for i in range(1, len(labels)):
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

        matched_true: set[int] = set()
        matched_pred: set[int] = set()

        for pi, ps in enumerate(pred_segs):
            for ti, ts in enumerate(true_segs):
                if ti in matched_true:
                    continue
                if ps["label"] != ts["label"]:
                    continue
                iou = _segment_iou(ps, ts)
                if iou >= self.iou_threshold:
                    matched_pred.add(pi)
                    matched_true.add(ti)
                    break

        tp = len(matched_pred)
        fp = len(pred_segs) - tp
        fn = len(true_segs) - len(matched_true)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return {"f1": f1, "precision": precision, "recall": recall}


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
        """Compute OverlapF1 at multiple IoU thresholds."""
        pred_segs = _extract_segments(pred_labels, self.id2label)
        true_segs = _extract_segments(true_labels, self.id2label)

        result: dict[str, float] = {}
        for threshold in self.thresholds:
            tag = str(int(threshold * 100))
            metric = OverlapF1(iou_threshold=threshold, num_classes=self.num_classes)
            single = metric.compute(pred_labels, true_labels)
            result[f"f1@{tag}"] = single["f1"]
            result[f"precision@{tag}"] = single["precision"]
            result[f"recall@{tag}"] = single["recall"]
        return result


__all__ = ["MultiOverlapF1", "OverlapF1", "_extract_segments", "_segment_iou"]
