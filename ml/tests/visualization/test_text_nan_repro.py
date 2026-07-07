"""Repro tests for #1167: visualization/core/text.py:286 int(background_alpha*255) NaN crash.

Bug: PIL text overlay crashes with `ValueError: cannot convert float NaN to integer`
when `background_alpha` is NaN (corrupt theme config / upstream NaN propagation).

Contract: NaN/non-finite background_alpha must NOT crash; fall back to safe default
(opaque background, alpha=1.0) so user gets visible text rather than missing frame.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from src.visualization.core.text import render_cyrillic_text


def _frame() -> np.ndarray:
    return np.zeros((100, 400, 3), dtype=np.uint8)


@pytest.fixture(autouse=True)
def _silence_deprecation():
    """render_cyrillic_text emits DeprecationWarning; silence to keep test output clean."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


class TestRenderCyrillicTextAlphaNaN:
    def test_nan_background_alpha_does_not_crash(self):
        """NaN background_alpha must not raise ValueError on int(NaN*255)."""
        frame = _frame()
        # Should not raise
        result = render_cyrillic_text(
            frame,
            "Test",
            (10, 30),
            background=(0, 0, 0),
            background_alpha=float("nan"),
        )
        assert result is frame

    def test_inf_background_alpha_does_not_crash(self):
        """Inf background_alpha must not raise; same guard as NaN."""
        frame = _frame()
        # Should not raise
        result = render_cyrillic_text(
            frame,
            "Test",
            (10, 30),
            background=(0, 0, 0),
            background_alpha=float("inf"),
        )
        assert result is frame

    def test_neg_inf_background_alpha_does_not_crash(self):
        """-Inf background_alpha must not raise."""
        frame = _frame()
        result = render_cyrillic_text(
            frame,
            "Test",
            (10, 30),
            background=(0, 0, 0),
            background_alpha=float("-inf"),
        )
        assert result is frame

    def test_nan_alpha_frame_modified(self):
        """Frame should be modified (text drawn) even with NaN alpha — no silent no-op."""
        frame = _frame()
        render_cyrillic_text(
            frame,
            "Привет",
            (10, 30),
            background=(0, 0, 0),
            background_alpha=float("nan"),
        )
        # Some pixels should have been written (text rendered, not skipped)
        assert frame.any(), "Frame was not modified — text overlay was skipped entirely"

    def test_valid_alpha_still_works(self):
        """Sanity: valid alpha 0.6 must continue to work after guard added."""
        frame = _frame()
        result = render_cyrillic_text(
            frame,
            "Test",
            (10, 30),
            background=(0, 0, 0),
            background_alpha=0.6,
        )
        assert result is frame
        assert frame.any()
