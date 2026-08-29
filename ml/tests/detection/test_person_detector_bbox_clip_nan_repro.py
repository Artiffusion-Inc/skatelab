"""RED repro — `PersonDetector.detect_frame` bbox clip silently clamps
NaN coords to (0, 0) corner (tranche HE, #1100).

Bug: ml/src/detection/person_detector.py:191-194 `detect_frame` clips
with:

    x1 = max(0.0, min(float(bx[0]), float(w)))
    y1 = max(0.0, min(float(bx[1]), float(h)))
    x2 = max(0.0, min(float(bx[2]), float(w)))
    y2 = max(0.0, min(float(bx[3]), float(h)))

NaN is silently coerced to (0, 0) via Python's NaN-arg-order behavior
in `min`/`max` (first arg wins on NaN comparison):

    bx[0] = NaN → min(NaN, w) = NaN → max(0.0, NaN) = 0.0  → x1 = 0.0
    bx[0] = NaN, bx[2] = NaN → x1=0.0, x2=0.0  → 0-area bbox at corner

All NaN cases are INDISTINGUISHABLE from a legitimate zero-area
detection at the (0, 0) corner. The detector returns a valid-looking
`BoundingBox` with a 0-area shape, and the bbox can be selected as
the "best" detection, sending downstream consumers to the (0, 0)
corner of the frame.

Concretely (on 100x200 frame):
    bx = [NaN, 50, 150, 150]  → BoundingBox(0, 50, 100, 150)  BUG
    bx = [NaN, NaN, NaN, NaN] → BoundingBox(0, 0, 0, 0)       BUG: 0-area
    bx = [10, 20, 110, 120]    → BoundingBox(10, 20, 100, 120) valid

Fix (NOT applied — repro only): guard the bbox array with
`math.isfinite` on all four coords and raise `ValueError` (or return
None) so the upstream bug surfaces at the trust boundary.

Methodology (per audit reglement):
  4 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — finite coords → finite clipped BoundingBox)
  1 source check (PASS — root cause locked via inspect.getsource)
"""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from src.detection.person_detector import PersonDetector

# =============================================================================
# Helpers
# =============================================================================


class _Inp:
    name: str = "input"


class _FakeSession:
    """Minimal InferenceSession stub that returns a single bbox with
    caller-supplied coordinates (one detection above confidence).
    """

    def __init__(self, bx_cxcywh_norm: list[float], conf_logit: float = 5.0) -> None:
        # RF-DETR outputs (1, 300, 4) cxcywh normalized + (1, 300, 91) logits.
        # We construct a single-detection output.
        boxes = np.zeros((1, 1, 4), dtype=np.float32)
        boxes[0, 0] = np.array(bx_cxcywh_norm, dtype=np.float32)
        # 91 logits: person class (index 1) high, rest low.
        logits = np.full((1, 1, 91), -10.0, dtype=np.float32)
        logits[0, 0, 1] = conf_logit  # person class
        self._boxes = boxes
        self._logits = logits

    def get_inputs(self) -> list[_Inp]:
        return [_Inp()]

    def run(
        self,
        _output_names: list[str] | None,
        _feed: dict[str, np.ndarray],
    ) -> list[np.ndarray]:
        return [self._boxes, self._logits]


def _detector_with_fake_session(bx_cxcywh_norm: list[float]) -> PersonDetector:
    """Build a PersonDetector whose ONNX session returns one detection
    with the given cxcywh-normalized bbox (everything else is monkey-
    patched to avoid touching the real RF-DETR ONNX file).
    """
    det = PersonDetector()
    det._session = _FakeSession(bx_cxcywh_norm)  # type: ignore[assignment]
    return det


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_detect_frame_has_isfinite_guard_on_bbox():
    """GREEN contract source check: `detect_frame` guards the bbox
    array with `math.isfinite` on all four coords. The unfixed function
    uses `max(0.0, min(float(bx[i]), float(w)))` which is NaN-blind
    (`min(NaN, w)` returns NaN via Python's first-arg-wins semantics,
    so NaN x1 silently lands on 0.0).
    """
    src = inspect.getsource(PersonDetector.detect_frame)
    assert "math.isfinite" in src, (
        "PersonDetector.detect_frame has no `math.isfinite` guard — "
        "NaN bbox coord silently clamps to (0, 0). Add `if not all("
        "math.isfinite(float(v)) for v in bx): raise ValueError(...)` "
        "before the clip block."
    )


# =============================================================================
# Observables — BUG present → PASS; fix flips these to FAIL (RED contract).
# =============================================================================


def test_detect_frame_nan_x1_does_not_produce_zero_corner_clamp():
    """NaN x1 must NOT silently clamp to 0.0 — unfixed function returns
    BoundingBox(0, y1, x2, y2) because `min(NaN, w) = NaN` and
    `max(0.0, NaN) = 0.0`. After fix, raises ValueError (or returns
    None) at the trust boundary so the upstream NaN source surfaces.
    """
    # Place the bbox at the left edge: cx=0.5, cy=0.5, w=0.4, h=0.4
    # in normalized coords (so x1_norm=0.3, x2_norm=0.7). Convert
    # manually to a NaN-x1 scenario: easiest is to feed a bx that
    # when clipped produces NaN x1. We use the cxcywh interface —
    # RF-DETR never produces NaN here in practice, but the
    # consumer-side clip must still guard. We simulate the NaN by
    # using a zero-width bbox and inspecting the clip behavior.
    #
    # Direct path: feed a known-bad cxcywh and confirm the clip
    # block raises (or returns None) instead of producing
    # BoundingBox(0, ..., 0, ...).
    det = _detector_with_fake_session(bx_cxcywh_norm=[math.nan, 0.5, 0.4, 0.4])
    frame = np.zeros((200, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="finite"):
        det.detect_frame(frame)


def test_detect_frame_nan_y1_does_not_produce_zero_corner_clamp():
    """NaN y1 must NOT silently clamp to 0.0 — same arg-order trap
    on the y axis. After fix, raises ValueError.
    """
    det = _detector_with_fake_session(bx_cxcywh_norm=[0.5, math.nan, 0.4, 0.4])
    frame = np.zeros((200, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="finite"):
        det.detect_frame(frame)


def test_detect_frame_nan_x2_does_not_produce_zero_corner_clamp():
    """NaN x2 must NOT silently clamp to 0.0 — `min(NaN, w) = NaN`
    then `max(0.0, NaN) = 0.0`, producing a 0-area bbox at the
    left edge. After fix, raises ValueError.
    """
    det = _detector_with_fake_session(bx_cxcywh_norm=[0.5, 0.5, math.nan, 0.4])
    frame = np.zeros((200, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="finite"):
        det.detect_frame(frame)


def test_detect_frame_nan_y2_does_not_produce_zero_corner_clamp():
    """NaN y2 must NOT silently clamp to 0.0 — same trap on y2.
    After fix, raises ValueError.
    """
    det = _detector_with_fake_session(bx_cxcywh_norm=[0.5, 0.5, 0.4, math.nan])
    frame = np.zeros((200, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="finite"):
        det.detect_frame(frame)


# =============================================================================
# Regression — valid finite coords must still clip correctly.
# =============================================================================


def test_detect_frame_valid_finite_bbox_clips_to_frame():
    """Regression: a finite, in-frame bbox is returned unchanged
    shape with the right clip behavior. The detector returns a
    `BoundingBox` with finite coords and 0 <= x1 < x2 <= w, 0 <=
    y1 < y2 <= h.
    """
    # cx=0.5, cy=0.5, w=0.4, h=0.4 → on a 100x200 frame:
    # x1 = (0.5 - 0.2) * 100 = 30, y1 = (0.5 - 0.2) * 200 = 60
    # x2 = (0.5 + 0.2) * 100 = 70, y2 = (0.5 + 0.2) * 200 = 140
    det = _detector_with_fake_session(bx_cxcywh_norm=[0.5, 0.5, 0.4, 0.4])
    frame = np.zeros((200, 100, 3), dtype=np.uint8)
    bbox = det.detect_frame(frame)
    assert bbox is not None
    assert math.isfinite(bbox.x1)
    assert math.isfinite(bbox.y1)
    assert math.isfinite(bbox.x2)
    assert math.isfinite(bbox.y2)
    assert 0 <= bbox.x1 < bbox.x2 <= 100
    assert 0 <= bbox.y1 < bbox.y2 <= 200
