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
