"""Tests for 3D pipeline integration in AnalysisPipeline."""

import numpy as np
import pytest

from src.pipeline import AnalysisPipeline
from src.types import H36Key


def test_pipeline_has_3d_lifter_attribute():
    """AnalysisPipeline has _3d_lifter attribute slot."""
    pipeline = AnalysisPipeline(device="cpu")
    assert hasattr(pipeline, "_3d_lifter")


def test_get_3d_lifter_returns_none_without_model():
    """_get_3d_lifter() returns None when model file not found."""
    pipeline = AnalysisPipeline(device="cpu")
    result = pipeline._get_3d_lifter()
    assert result is None


def test_3d_lifter_unavailable_flag_prevents_retry():
    """When model is missing, _3d_lifter_unavailable=True prevents repeated warnings."""
    pipeline = AnalysisPipeline(device="cpu")
    # First call sets the flag
    assert pipeline._get_3d_lifter() is None
    assert pipeline._3d_lifter_unavailable is True
    # Second call short-circuits (no repeated warning)
    assert pipeline._get_3d_lifter() is None


def test_3d_lifter_release_resets_to_none():
    """After release(), _3d_lifter is None and can be re-created (if model exists)."""
    pipeline = AnalysisPipeline(device="cpu")
    # Simulate a released lifter (was created, then released)
    pipeline._3d_lifter = None
    # Should not set _3d_lifter_unavailable (that's only for missing model file)
    assert not getattr(pipeline, "_3d_lifter_unavailable", False)
    # Re-creating will try to find model file again (lazy re-init)
    result = pipeline._get_3d_lifter()
    # Without model file, returns None but this time from file-not-found
    assert result is None
