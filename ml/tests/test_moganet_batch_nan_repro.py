"""RED repro for #1197 — MogaNetBatch NaN crash on int(crop_w*scale) at lines 63-64 / 149-150.

The detector may return a crop array whose shape tuple contains NaN when the
YOLOv8n box postprocessing step produced NaN coordinates (e.g. corrupt NMS
output, half-precision overflow, or downstream stage bug). The current guard
``if crop_w <= 0 or crop_h <= 0`` is bypassed by NaN — ``NaN <= 0`` is False —
so execution reaches:

    scale = min(input_w / crop_w, input_h / crop_h)   # NaN
    new_w = int(crop_w * scale)                        # int(NaN) -> ValueError
    new_h = int(crop_h * scale)                        # int(NaN) -> ValueError

The same NaN appears at lines 149-150 in rescale_keypoints. A corrupt
detector crop must not abort the whole batch inference. The fix should
add an ``math.isfinite`` guard for crop_w, crop_h (and ideally input dims)
that converts NaN to a clear, typed ``ValueError`` BEFORE int() conversion.

These tests must FAIL on master (current code) and PASS after the fix.
"""

from __future__ import annotations

import inspect
import re

import numpy as np
import pytest

from src.pose_estimation import moganet_batch
from src.pose_estimation.moganet_batch import (
    MOGANET_INPUT_SIZE,
    preprocess_crops,
    rescale_keypoints,
)


def _make_finite_crop(h: int, w: int) -> np.ndarray:
    """Build a valid (h, w, 3) uint8 BGR crop."""
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


class _ShapeOnlyCrop:
    """Duck-typed crop that returns a NaN-containing shape.

    Used to simulate a corrupt detector where the shape tuple itself
    contains NaN. ``preprocess_crops`` only reads ``crop.shape[:2]``,
    so the array data is irrelevant.
    """

    def __init__(self, h, w, *, h_nan: bool = False, w_nan: bool = False) -> None:
        self._h = float("nan") if h_nan else h
        self._w = float("nan") if w_nan else w
        # Real underlying data for cv2.resize in case the guard is missed.
        self._arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

    @property
    def shape(self) -> tuple:
        return (self._h, self._w, 3)

    def __array__(self, dtype=None):
        return self._arr.astype(dtype) if dtype else self._arr


class TestPreprocessCropsNaN:
    """REGRESSION (#1197): NaN-width / NaN-height crops must NOT raise
    ``ValueError: cannot convert float NaN to integer`` from int(crop_w*scale).
    """

    def test_preprocess_crops_nan_width_does_not_crash_repro(self):
        """crop_w=NaN (height valid) must not raise int(NaN) ValueError.

        On unfixed code: ``NaN <= 0`` is False so the guard at line 61 is
        bypassed, scale becomes NaN, and ``int(crop_w * scale) = int(NaN)``
        raises ``ValueError: cannot convert float NaN to integer``.
        """
        nan_w_crop = _ShapeOnlyCrop(100, 100, w_nan=True)

        with pytest.raises((ValueError,)) as excinfo:
            preprocess_crops([nan_w_crop])
        # Bug #1197: the underlying exception is the int(NaN) ValueError.
        # The fix must convert to a clearer ValueError that names crop dim
        # / NaN — bare int(NaN) is the symptom.
        msg = str(excinfo.value)
        assert "cannot convert float NaN to integer" not in msg, (
            f"preprocess_crops raised bare int(NaN) ValueError (bug #1197). "
            f"Expected a guard for NaN crop dimensions. Got: {excinfo.value!r}"
        )

    def test_preprocess_crops_nan_height_does_not_crash_repro(self):
        """crop_h=NaN (width valid) must not raise int(NaN) ValueError."""
        nan_h_crop = _ShapeOnlyCrop(100, 100, h_nan=True)

        with pytest.raises((ValueError,)) as excinfo:
            preprocess_crops([nan_h_crop])
        msg = str(excinfo.value)
        assert "cannot convert float NaN to integer" not in msg, (
            f"preprocess_crops raised bare int(NaN) ValueError (bug #1197). "
            f"Expected a guard for NaN crop dimensions. Got: {excinfo.value!r}"
        )

    def test_preprocess_crops_mixed_valid_and_nan_does_not_crash_repro(self):
        """A mixed batch (valid + NaN-w) must surface a clear ValueError,
        not the raw int(NaN) ValueError that aborts the whole batch.

        On unfixed code: the first valid crop preprocesses fine, then the
        NaN-w crop triggers ``int(NaN * scale) = ValueError`` and aborts
        the batch — valid crops in the same batch are lost.
        """
        valid = _make_finite_crop(200, 150)
        nan_w = _ShapeOnlyCrop(100, 100, w_nan=True)

        with pytest.raises((ValueError,)) as excinfo:
            preprocess_crops([valid, nan_w])
        msg = str(excinfo.value)
        assert "cannot convert float NaN to integer" not in msg, (
            f"preprocess_crops raised bare int(NaN) ValueError on mixed "
            f"batch (bug #1197). Expected guard. Got: {excinfo.value!r}"
        )

    def test_preprocess_crops_isfinite_guard_present_repro(self):
        """Source check: preprocess_crops must guard NaN before int().

        The fix should add an explicit ``math.isfinite`` (or equivalent
        NaN-rejecting) check for crop_w, crop_h before the
        ``int(crop_w * scale)`` call. Acceptable patterns:
          - ``math.isfinite(crop_w) and math.isfinite(crop_h)``
          - ``np.isfinite(crop_w) and np.isfinite(crop_h)``
          - ``if not (crop_w == crop_w):`` (self-NaN idiom)
        """
        src = inspect.getsource(moganet_batch.preprocess_crops)
        guarded = bool(
            re.search(r"math\.isfinite\(\s*crop_w\s*\)", src)
            or re.search(r"math\.isfinite\(\s*crop_h\s*\)", src)
            or re.search(r"np\.isfinite\(\s*crop_w\s*\)", src)
            or re.search(r"np\.isfinite\(\s*crop_h\s*\)", src)
            or re.search(r"crop_w\s*==\s*crop_w", src)
            or re.search(r"crop_h\s*==\s*crop_h", src)
        )
        assert guarded, (
            "preprocess_crops source has no NaN guard before int(crop_w*scale). "
            "Bug #1197: int(NaN) crashes the whole batch. "
            "Add math.isfinite(crop_w) and math.isfinite(crop_h) checks.\n"
            f"--- source ---\n{src}"
        )


class TestRescaleKeypointsNaN:
    """rescale_keypoints mirrors preprocess_crops and must also be guarded."""

    def test_rescale_keypoints_nan_width_does_not_crash_repro(self):
        """NaN-w crop in rescale_keypoints must not raise int(NaN) ValueError."""
        nan_w = _ShapeOnlyCrop(100, 100, w_nan=True)
        keypoints = np.zeros((1, 17, 2), dtype=np.float32)
        bboxes = [(0, 0, 0, 100)]

        with pytest.raises((ValueError,)) as excinfo:
            rescale_keypoints(keypoints, [nan_w], bboxes)
        msg = str(excinfo.value)
        assert "cannot convert float NaN to integer" not in msg, (
            f"rescale_keypoints raised bare int(NaN) ValueError (bug #1197). "
            f"Expected guard. Got: {excinfo.value!r}"
        )

    def test_rescale_keypoints_isfinite_guard_present_repro(self):
        """Source check: rescale_keypoints must guard NaN before int()."""
        src = inspect.getsource(moganet_batch.rescale_keypoints)
        guarded = bool(
            re.search(r"math\.isfinite\(\s*crop_w\s*\)", src)
            or re.search(r"math\.isfinite\(\s*crop_h\s*\)", src)
            or re.search(r"np\.isfinite\(\s*crop_w\s*\)", src)
            or re.search(r"np\.isfinite\(\s*crop_h\s*\)", src)
            or re.search(r"crop_w\s*==\s*crop_w", src)
            or re.search(r"crop_h\s*==\s*crop_h", src)
        )
        assert guarded, (
            "rescale_keypoints source has no NaN guard before int(crop_w*scale). "
            "Bug #1197: int(NaN) crashes the whole batch.\n"
            f"--- source ---\n{src}"
        )


def test_valid_crops_still_work_repro():
    """Sanity regression: valid crops still produce a finite (B, 3, H, W) tensor."""
    crops = [
        _make_finite_crop(200, 150),
        _make_finite_crop(100, 80),
        _make_finite_crop(288, 384),
    ]
    tensor = preprocess_crops(crops)
    assert tensor.shape == (3, 3, MOGANET_INPUT_SIZE[1], MOGANET_INPUT_SIZE[0])
    assert tensor.dtype == np.float32
    assert np.all(np.isfinite(tensor)), "valid crops must produce all-finite values"
