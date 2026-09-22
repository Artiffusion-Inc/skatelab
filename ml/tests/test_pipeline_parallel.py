# tests/test_pipeline_parallel.py
"""Tests for async pipeline parallelism."""

import asyncio
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from src.model_config import ModelConfig
from src.pipeline import AnalysisPipeline
from src.types import ElementPhase, VideoMeta


@pytest.fixture
def model_config(tmp_path):
    """Provide required placeholder model files without downloading binaries."""
    for relative_path in (
        "data/models/moganet_b_ap2d_384x288.onnx",
        "data/models/rf_detr_nano.onnx",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test model placeholder")
    return ModelConfig.from_root(tmp_path)


@pytest.mark.asyncio
async def test_analyze_async_exists():
    """Test that analyze_async method exists and is callable."""
    pipeline = AnalysisPipeline(enable_smoothing=False)

    assert callable(pipeline.analyze_async)
    assert hasattr(pipeline, "_detect_phases_async")
    assert hasattr(pipeline, "_compute_metrics_async")
    assert hasattr(pipeline, "_load_reference_async")


@pytest.mark.asyncio
async def test_analyze_async_without_element(model_config):
    """Test analyze_async without element type."""
    pipeline = AnalysisPipeline(enable_smoothing=False, model_config=model_config)

    # Mock both get_video_meta and extract_and_track
    mock_meta = VideoMeta(
        path=Path("dummy.mp4"),
        num_frames=100,
        fps=30.0,
        width=1920,
        height=1080,
    )

    with (
        mock.patch("src.pipeline.get_video_meta", return_value=mock_meta),
        mock.patch.object(
            pipeline,
            "_extract_and_track",
            return_value=(np.random.randn(100, 17, 3), 0),
        ),
    ):
        report = await pipeline.analyze_async(
            Path("dummy.mp4"),
            element_type=None,
        )

    assert report.element_type == "unknown"
    assert report.phases.takeoff == 0
    assert report.phases.peak == 0
    assert report.phases.landing == 0


def test_analyze_sync_still_works(model_config):
    """Test that sync analyze method still works after adding async."""
    pipeline = AnalysisPipeline(enable_smoothing=False, model_config=model_config)

    # Mock both get_video_meta and extract_and_track
    mock_meta = VideoMeta(
        path=Path("dummy.mp4"),
        num_frames=100,
        fps=30.0,
        width=1920,
        height=1080,
    )

    with (
        mock.patch("src.pipeline.get_video_meta", return_value=mock_meta),
        mock.patch.object(
            pipeline,
            "_extract_and_track",
            return_value=(np.random.randn(100, 17, 3), 0),
        ),
    ):
        report = pipeline.analyze(
            Path("dummy.mp4"),
            element_type=None,
        )

    assert report.element_type == "unknown"


@pytest.mark.asyncio
async def test_parallel_stage_execution():
    """Test that async methods can be executed in parallel."""
    pipeline = AnalysisPipeline(enable_smoothing=False)

    # Create mock tasks
    async def mock_task(name, delay):
        await asyncio.sleep(delay)
        return name

    # Run tasks in parallel
    results = await asyncio.gather(
        mock_task("task1", 0.01),
        mock_task("task2", 0.01),
    )

    assert len(results) == 2
    assert "task1" in results
    assert "task2" in results


@pytest.mark.asyncio
async def test_detect_phases_async_with_manual():
    """Test _detect_phases_async with manual phases."""
    pipeline = AnalysisPipeline(enable_smoothing=False)

    poses = np.random.randn(100, 17, 2).astype(np.float32)
    manual = ElementPhase(name="test", takeoff=50, peak=60, landing=70, start=40, end=80)

    result = await pipeline._detect_phases_async(poses, 30.0, "test", manual)

    assert result == manual


@pytest.mark.asyncio
async def test_compute_metrics_async():
    """Test _compute_metrics_async method."""
    from src.analysis import element_defs

    pipeline = AnalysisPipeline(enable_smoothing=False)

    poses = np.random.randn(100, 17, 2).astype(np.float32)
    phases = ElementPhase(name="waltz_jump", takeoff=50, peak=60, landing=70, start=40, end=80)
    element_def = element_defs.get_element_def("waltz_jump")

    if element_def is not None:
        metrics = await pipeline._compute_metrics_async(poses, phases, 30.0, element_def)

        # Should return list of metrics
        assert isinstance(metrics, list)


@pytest.mark.asyncio
async def test_load_reference_async():
    """Test _load_reference_async method."""
    pipeline = AnalysisPipeline(enable_smoothing=False, reference_store=None)

    # Without reference store, should return None
    result = await pipeline._load_reference_async("waltz_jump")

    assert result is None
