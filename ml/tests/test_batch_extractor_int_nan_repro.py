"""RED repro for issue #1199: `BatchPoseExtractor._detect_and_crop`
(batch_extractor.py:147-150) crashes with
`ValueError: cannot convert float NaN to integer` when the person
detection's bbox fields (x1, y1, x2, y2) are NaN.

Root cause:
    bw = detection.x2 - detection.x1
    bh = detection.y2 - detection.y1
    pad_x = bw * 0.1
    pad_y = bh * 0.1
    x1 = max(0, int(detection.x1 - pad_x))   # 147-150 — stdlib int(NaN)
    y1 = max(0, int(detection.y1 - pad_y))
    x2 = min(w, int(detection.x2 + pad_x))
    y2 = min(h, int(detection.y2 + pad_y))
`int(float('nan'))` raises `ValueError: cannot convert float NaN to
integer` (Python stdlib contract, verified). NaN detection fields
arrive via corrupt YOLO output or upstream NaN propagation. No
`math.isfinite` / `np.isfinite` / `math.isnan` / `np.isnan` /
`np.nan_to_num` guard exists before the int() conversions, so the
stdlib ValueError escapes — undocumented, no field name, no graceful
degradation (a single corrupt detection halts the whole batch).

Sibling of `test_batch_extractor_nan_repro.py` (issue #1160, resize
guard at line 208). That test covers NaN h/w in the per-frame
resize block. THIS test covers NaN detection bbox fields in
`_detect_and_crop` at lines 147-150. Two distinct crash sites,
same root cause (missing isfinite guard before int() conversion),
same fix pattern (math.isfinite guard at the top of the block).

The issue's "Fix (suggested)" calls for `math.isfinite` guards for
detection x1/y1/x2/y2 at the top of the crop logic, and for h/w at
the top of the resize. The h/w guard is already applied (line 209-212,
#1160); this test pins the remaining detection-field guard.

Contract: NaN detection bbox fields must NOT propagate to `int(NaN)`.
The function must produce a clean signal (skip the corrupt detection,
return empty crops/bboxes, similar to the `detection is None` path at
line 139). Valid finite detection fields must continue to produce
correct crops/bboxes — the regression test.

Pure-Python: `cv2.VideoCapture` and `cv2.resize` mocked — no real
video, no GPU, no DB. The mock detector returns a BBox with NaN
fields to drive the exact code path the issue names.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.pose_estimation.batch_extractor import BatchPoseExtractor


def _make_extractor(monkeypatch) -> BatchPoseExtractor:
    """Build a BatchPoseExtractor with mocked moganet. Detector
    must be patched by the caller via `_nan_bbox_detector` BEFORE
    calling this — the constructor uses the patched class. The
    detector's `detect_frame` is overridden per-test in the caller.
    """

    class FakeMogaNet:
        def __init__(self, **kwargs):
            self.closed = False

        def infer_batch(self, crops, bboxes):
            raise AssertionError("not used by _detect_and_crop")

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        "src.pose_estimation.moganet_batch.MogaNetBatch",
        FakeMogaNet,
    )
    return BatchPoseExtractor(batch_size=4, device="cpu")


def _nan_bbox_detector(monkeypatch, *, x1, y1, x2, y2):
    """Mock PersonDetector returning a single BBox with the given
    fields. NaN in any field drives the int(NaN) crash at lines 147-150.
    """

    class NaNBBoxDetector:
        def __init__(self, **kwargs):
            pass

        def detect_frame(self, frame):
            return type(
                "BBox",
                (),
                {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": 0.9,
                },
            )()

    monkeypatch.setattr(
        "src.detection.person_detector.PersonDetector",
        NaNBBoxDetector,
    )


# --------------------------------------------------------------------------- #
# Observable 1: locks the stdlib crash mechanism — int(NaN) is ValueError.
# --------------------------------------------------------------------------- #


def test_int_nan_raises_valueerror():
    """Locks the stdlib crash mechanism that propagates from
    `int(detection.x1 - pad_x)` when x1 is NaN. Passes today (Python
    stdlib contract); exists to document the mechanism the fix must
    interrupt."""
    try:
        int(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError(
            "int(float('nan')) did not raise ValueError — Python stdlib "
            "contract changed? Re-check the assertion below."
        )


# --------------------------------------------------------------------------- #
# Observable 2: NaN x1 in detection bbox — the exact issue scenario.
# --------------------------------------------------------------------------- #


def test_nan_x1_in_detection_does_not_crash_with_valueerror(monkeypatch):
    """Detection with `x1=NaN, y1=30, x2=200, y2=300` (all other
    fields finite). On master: `int(NaN - pad_x) = ValueError` at
    line 148 — RED. After fix: NaN caught by `isfinite` guard at
    the top of the crop block, the corrupt detection is skipped
    (return empty crops/bboxes, same contract as `detection is None`),
    no stdlib int(NaN) crash. The RED signal is the SPECIFIC stdlib
    "cannot convert float NaN to integer" ValueError from line 148."""
    _nan_bbox_detector(monkeypatch, x1=float("nan"), y1=30.0, x2=200.0, y2=300.0)
    extractor = _make_extractor(monkeypatch)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    try:
        crops, bboxes = extractor._detect_and_crop(frame)
    except ValueError as e:
        msg = str(e)
        if "cannot convert float NaN to integer" in msg:
            raise AssertionError(
                f"BUG: _detect_and_crop (batch_extractor.py:148) raised "
                f"undocumented stdlib int(NaN) ValueError ({msg!r}) on "
                f"NaN x1. The fix must guard detection x1/y1/x2/y2 with "
                f"`math.isfinite` (or equivalent) at the top of the crop "
                f"block so the stdlib int(NaN) is unreachable."
            ) from e
        raise AssertionError(f"Unexpected ValueError on NaN x1: {e!r}") from e
    # GREEN post-fix: clean signal — empty crops/bboxes for corrupt
    # detection (same contract as the `detection is None` branch).
    assert crops == [], f"expected empty crops for NaN detection, got {len(crops)}"
    assert bboxes == [], f"expected empty bboxes for NaN detection, got {bboxes}"


# --------------------------------------------------------------------------- #
# Observable 3: NaN y2 in detection bbox — second crash site.
# --------------------------------------------------------------------------- #


def test_nan_y2_in_detection_does_not_crash_with_valueerror(monkeypatch):
    """Detection with `x1=50, y1=30, x2=200, y2=NaN` (only y2 is NaN).
    On master: `int(NaN + pad_y) = ValueError` at line 151 — RED.
    After fix: clean signal, no stdlib int(NaN) crash."""
    _nan_bbox_detector(monkeypatch, x1=50.0, y1=30.0, x2=200.0, y2=float("nan"))
    extractor = _make_extractor(monkeypatch)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    try:
        crops, bboxes = extractor._detect_and_crop(frame)
    except ValueError as e:
        msg = str(e)
        if "cannot convert float NaN to integer" in msg:
            raise AssertionError(
                f"BUG: _detect_and_crop (batch_extractor.py:151) raised "
                f"undocumented stdlib int(NaN) ValueError ({msg!r}) on "
                f"NaN y2."
            ) from e
        raise AssertionError(f"Unexpected ValueError on NaN y2: {e!r}") from e
    assert crops == []
    assert bboxes == []


# --------------------------------------------------------------------------- #
# Observable 4: all-NaN detection bbox — wide-net crash.
# --------------------------------------------------------------------------- #


def test_all_nan_detection_does_not_crash_with_valueerror(monkeypatch):
    """Detection with all-NaN bbox fields. On master: any of the
    four int(NaN) sites crashes — RED. After fix: clean signal."""
    _nan_bbox_detector(
        monkeypatch,
        x1=float("nan"),
        y1=float("nan"),
        x2=float("nan"),
        y2=float("nan"),
    )
    extractor = _make_extractor(monkeypatch)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    try:
        crops, bboxes = extractor._detect_and_crop(frame)
    except ValueError as e:
        msg = str(e)
        if "cannot convert float NaN to integer" in msg:
            raise AssertionError(
                f"BUG: _detect_and_crop (batch_extractor.py:148-151) raised "
                f"undocumented stdlib int(NaN) ValueError ({msg!r}) on "
                f"all-NaN detection."
            ) from e
        raise AssertionError(f"Unexpected ValueError on all-NaN detection: {e!r}") from e
    assert crops == []
    assert bboxes == []


# --------------------------------------------------------------------------- #
# Observable 5 (root-cause lock): source must guard int(detection.x1 - pad_x)
# etc. with an isfinite (or equivalent) check. This test is RED on master
# (no guard exists in _detect_and_crop) and GREEN after the fix.
# --------------------------------------------------------------------------- #


def test_source_has_isfinite_guard_in_detect_and_crop():
    """Root cause locked: _detect_and_crop computes
    `int(detection.x1 - pad_x)` etc. at lines 148-151 with no
    `math.isfinite` / `np.isfinite` / `math.isnan` / `np.isnan` /
    `np.nan_to_num` guard. After the fix, an isfinite (or equivalent)
    check MUST appear in `_detect_and_crop` BEFORE the int() conversions
    so stdlib int(NaN) is unreachable.

    Note: the test checks for a finite/NaN guard in `_detect_and_crop`,
    not in `extract_video_tracked` (the resize guard is a separate
    sibling fix, #1160)."""
    src = inspect.getsource(BatchPoseExtractor._detect_and_crop)
    has_guard = (
        "math.isfinite" in src
        or "np.isfinite" in src
        or "math.isnan" in src
        or "np.isnan" in src
        or "np.nan_to_num" in src
    )
    assert has_guard, (
        "BUG: _detect_and_crop (batch_extractor.py:148-151) calls "
        "`int(detection.x1 - pad_x)` / `int(detection.x2 + pad_x)` etc. "
        "with no isfinite guard. `int(float('nan'))` raises ValueError, "
        "crashing the whole batch on a single corrupt detection. Add a "
        "guard like `if not all(math.isfinite(getattr(detection, a)) "
        "for a in ('x1','y1','x2','y2')):` at the top of the crop block "
        "— skip the corrupt detection (return [], []) or raise a typed "
        "error naming the corrupt field."
    )


# --------------------------------------------------------------------------- #
# Regression: valid finite detection still produces correct crop + bbox.
# --------------------------------------------------------------------------- #


def test_valid_finite_detection_still_produces_crop_and_bbox(monkeypatch):
    """Regression: a detection with all-finite bbox fields MUST still
    produce a non-empty crop + bbox with the correct padding/clipping,
    identical to master behavior. The isfinite guard must let all-finite
    detections pass through unchanged."""
    _nan_bbox_detector(monkeypatch, x1=50.0, y1=30.0, x2=200.0, y2=300.0)
    extractor = _make_extractor(monkeypatch)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    crops, bboxes = extractor._detect_and_crop(frame)

    assert len(crops) == 1, f"expected 1 crop, got {len(crops)}"
    assert len(bboxes) == 1, f"expected 1 bbox, got {len(bboxes)}"
    x1, y1, x2, y2 = bboxes[0]
    # 20% padding: bw=150, pad_x=15, so x1 = max(0, 50-15)=35, x2 = min(640, 200+15)=215
    # y1 = max(0, 30-27)=3, y2 = min(480, 300+27)=327
    assert (x1, y1, x2, y2) == (35, 3, 215, 327), (
        f"BUG: bbox changed for valid detection — got ({x1},{y1},{x2},{y2}), "
        f"expected (35, 3, 215, 327). The isfinite guard must NOT alter "
        f"the path for finite detections."
    )
    # Crop shape should match the bbox (x2-x1, y2-y1, 3).
    assert crops[0].shape == (327 - 3, 215 - 35, 3), (
        f"BUG: crop shape changed — got {crops[0].shape}, expected {(327 - 3, 215 - 35, 3)}."
    )
