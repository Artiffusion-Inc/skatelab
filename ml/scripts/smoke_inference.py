#!/usr/bin/env python3
"""Reproducible real-video ML smoke run.

Usage:
    uv run --frozen --package ml python ml/scripts/smoke_inference.py \
        data/datasets/skatingverse/test_videos/100_0WOWTjJO.mp4 \
        --output /tmp/skatelab-smoke-result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.inference_result import result_from_report
from src.model_config import ModelConfig
from src.pipeline import AnalysisPipeline
from src.utils.profiling import PipelineProfiler


def run_smoke(video: Path, output: Path, element: str, device: str) -> dict:
    """Run one real video and write the stable result contract."""
    config = ModelConfig.default()
    warnings = config.validate()
    profiler = PipelineProfiler()
    pipeline = AnalysisPipeline(device=device, profiler=profiler, model_config=config)
    with profiler:
        report = pipeline.analyze(video, element_type=element)

    profile = profiler.to_dict()
    timings = {"total_wall_time_s": profile["total_wall_time_s"]}
    timings.update({stage["name"]: stage["wall_time_s"] for stage in profile["stages"]})
    result = result_from_report(report, timings=timings)
    if warnings:
        result = replace(result, warnings=list(dict.fromkeys([*warnings, *result.warnings])))

    payload = result.to_dict()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ML pipeline on one real video")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--element", default="waltz_jump")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    args = parser.parse_args()

    if not args.video.is_file():
        parser.error(f"video not found: {args.video}")

    payload = run_smoke(args.video, args.output, args.element, args.device)
    print(f"Result: {args.output}")
    print(f"Processed frames: {payload['processed_frames']}")
    print(f"Metrics: {len(payload['metrics'])}")
    print(f"Total time: {payload['timings']['total_wall_time_s']:.3f}s")
    print(f"3D enabled: {payload['stages'].get('pose_3d', False)}")
    for warning in payload["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
