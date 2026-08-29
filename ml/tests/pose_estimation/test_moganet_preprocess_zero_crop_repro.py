"""Regression tests for #1046 — MogaNetBatch.preprocess_crops ZeroDivisionError on degenerate crops.

A YOLOv8n detector can return a zero-area box (e.g. sub-pixel coverage at frame edge).
preprocess_crops at ml/src/pose_estimation/moganet_batch.py:62-64 (and rescale_keypoints
at lines 148-150) compute:

    scale = min(input_w / crop_w, input_h / crop_h)  # crop_w or crop_h == 0 -> ZeroDivisionError

A single degenerate crop must not abort the whole batch. This file pins the expected
behavior at the public API surface: a degenerate crop must raise a clear, typed error
(ValueError) — NOT a bare ZeroDivisionError — so the caller can skip the crop rather
than the whole inference.
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


class TestPreprocessCropsZeroSize:
    """REGRESSION (#1046): zero-w / zero-h crops must NOT raise ZeroDivisionError."""

    def test_preprocess_crops_zero_width_does_not_crash_repro(self):
        """crop_w=0 (height valid) must not raise ZeroDivisionError.

        On unfixed code: raises ``ZeroDivisionError: division by zero`` from
        ``min(input_w / crop_w, ...)``.
        """
        zero_w_crop = np.zeros((100, 0, 3), dtype=np.uint8)
        with pytest.raises((ValueError, ZeroDivisionError)) as excinfo:
            preprocess_crops([zero_w_crop])
        # Bug #1046: was ZeroDivisionError; fix must convert to ValueError.
        # On master this test must FAIL because ZeroDivisionError leaks through.
        assert not isinstance(excinfo.value, ZeroDivisionError), (
            f"ZeroDivisionError leaks from preprocess_crops (bug #1046). "
            f"Expected ValueError. Got: {excinfo.value!r}"
        )

    def test_preprocess_crops_zero_height_does_not_crash_repro(self):
        """crop_h=0 (width valid) must not raise ZeroDivisionError."""
        zero_h_crop = np.zeros((0, 100, 3), dtype=np.uint8)
        with pytest.raises((ValueError, ZeroDivisionError)) as excinfo:
            preprocess_crops([zero_h_crop])
        assert not isinstance(excinfo.value, ZeroDivisionError), (
            f"ZeroDivisionError leaks from preprocess_crops (bug #1046). "
            f"Expected ValueError. Got: {excinfo.value!r}"
        )

    def test_preprocess_crops_mixed_valid_and_zero_does_not_crash_repro(self):
        """A mixed batch (valid + zero-w) must surface a clear ValueError, not abort silently.

        On unfixed code: the whole batch aborts on the first zero-w crop with
        ZeroDivisionError; valid crops in the same batch are lost.
        """
        valid = _make_finite_crop(200, 150)
        zero_w = np.zeros((100, 0, 3), dtype=np.uint8)
        with pytest.raises((ValueError, ZeroDivisionError)) as excinfo:
            preprocess_crops([valid, zero_w])
        assert not isinstance(excinfo.value, ZeroDivisionError), (
            f"ZeroDivisionError leaks from mixed batch (bug #1046). "
            f"Expected ValueError. Got: {excinfo.value!r}"
        )

    def test_preprocess_crops_valid_crops_unchanged_repro(self):
        """Regression: valid crops still produce a finite (B, 3, H, W) tensor."""
        crops = [
            _make_finite_crop(200, 150),
            _make_finite_crop(100, 80),
            _make_finite_crop(288, 384),
        ]
        tensor = preprocess_crops(crops)
        assert tensor.shape == (3, 3, MOGANET_INPUT_SIZE[1], MOGANET_INPUT_SIZE[0])
        assert tensor.dtype == np.float32
        assert np.all(np.isfinite(tensor)), "valid crops must produce all-finite values"

    def test_preprocess_crops_unguarded_div_source_repro(self):
        """Source check: the unguarded ``min(input_w / crop_w, ...)`` is present.

        The fix should add an explicit guard (e.g. ``max(crop_w, 1)``) OR raise
        ValueError. This test asserts the API now either (a) has a guard, or
        (b) raises ValueError when called with a zero-w crop. The previous test
        pins (b); this one pins (a) at the source.
        """
        src = inspect.getsource(moganet_batch.preprocess_crops)
        # Either: there is an explicit guard, or a ValueError-raising branch.
        # The unguarded form ``scale = min(input_w / crop_w, ...)`` (no guard
        # before crop_w) is the bug. A correct version clamps crop_w/h to >= 1
        # OR checks for it and raises.
        # Acceptable guard patterns (any one of):
        #   - clamp: max(crop_w, 1), max(crop_h, 1)
        #   - early raise: if crop_w == 0 or crop_h == 0: raise ValueError
        #   - np.maximum(..., 1) clamp
        guarded = bool(
            re.search(r"max\(\s*crop_w\s*,\s*1\s*\)", src)
            or re.search(r"max\(\s*crop_h\s*,\s*1\s*\)", src)
            or re.search(r"np\.maximum\(\s*crop_w\s*,\s*1\s*\)", src)
            or re.search(r"if\s+.*crop_w\s*<=\s*0.*raise\s+ValueError", src, re.S)
            or re.search(r"if\s+.*crop_h\s*<=\s*0.*raise\s+ValueError", src, re.S)
            or re.search(r"if\s+.*crop_w\s*==\s*0.*raise\s+ValueError", src, re.S)
            or re.search(r"if\s+.*crop_h\s*==\s*0.*raise\s+ValueError", src, re.S)
        )
        assert guarded, (
            "preprocess_crops source has no guard for zero-w / zero-h crops. "
            "Bug #1046: 'scale = min(input_w / crop_w, ...)' will raise "
            "ZeroDivisionError on degenerate crops.\n--- source ---\n" + src
        )


class TestRescaleKeypointsZeroSize:
    """rescale_keypoints mirrors preprocess_crops and must also be guarded."""

    def test_rescale_keypoints_zero_width_does_not_crash_repro(self):
        """Zero-w crop in rescale_keypoints must not raise ZeroDivisionError."""
        zero_w_crop = np.zeros((100, 0, 3), dtype=np.uint8)
        keypoints = np.zeros((1, 17, 2), dtype=np.float32)
        bboxes = [(0, 0, 0, 100)]
        with pytest.raises((ValueError, ZeroDivisionError)) as excinfo:
            rescale_keypoints(keypoints, [zero_w_crop], bboxes)
        assert not isinstance(excinfo.value, ZeroDivisionError), (
            f"ZeroDivisionError leaks from rescale_keypoints (bug #1046). "
            f"Expected ValueError. Got: {excinfo.value!r}"
        )
