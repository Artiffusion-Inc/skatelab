#!/usr/bin/env python3
"""Benchmark RF-DETR variants (Nano/Small/Medium) on skating video.

Compares FPS, detection recall, and small-object detection quality
against YOLOv8n baseline.

Usage:
    uv run python scripts/benchmark_detector.py --video path/to/skating.mp4
    uv run python scripts/benchmark_detector.py --video path/to/skating.mp4 --models nano small
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from src.detection.person_detector import PersonDetector
from src.utils.video import extract_frames, get_video_meta


def benchmark_model(
    model_path: Path,
    input_size: int,
    frames: list[np.ndarray],
    confidence: float = 0.5,
) -> dict:
    """Run detection on all frames, return metrics."""
    detector = PersonDetector(
        model_path=str(model_path),
        confidence=confidence,
        input_size=input_size,
    )

    # Warmup
    detector.detect_frame(frames[0])

    detections: list[int] = []
    times: list[float] = []

    for frame in frames:
        t0 = time.perf_counter()
        bbox = detector.detect_frame(frame)
        t1 = time.perf_counter()
        detections.append(1 if bbox is not None else 0)
        times.append(t1 - t0)

    recall = sum(detections) / len(detections) if detections else 0
    fps = 1.0 / (sum(times) / len(times)) if times else 0
    avg_ms = sum(times) / len(times) * 1000

    return {
        "model": model_path.stem,
        "recall": recall,
        "fps": fps,
        "avg_ms": avg_ms,
        "detected_frames": sum(detections),
        "total_frames": len(frames),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark RF-DETR on skating video")
    parser.add_argument("--video", type=Path, required=True, help="Path to skating video")
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["nano", "small", "medium"],
        default=["nano", "small", "medium"],
        help="Model variants to benchmark",
    )
    parser.add_argument("--max-frames", type=int, default=100, help="Max frames to process")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence")
    args = parser.parse_args()

    # Read frames
    frames = []
    for i, frame in enumerate(extract_frames(args.video)):
        if i >= args.max_frames:
            break
        frames.append(frame)

    print(f"Video: {args.video} ({len(frames)} frames)")
    print(f"Resolution: {frames[0].shape[1]}x{frames[0].shape[0]}")
    print()

    model_configs = {
        "nano": {"path": Path("data/models/rf_detr_nano.onnx"), "size": 384},
        "small": {"path": Path("data/models/rf_detr_small.onnx"), "size": 512},
        "medium": {"path": Path("data/models/rf_detr_medium.onnx"), "size": 576},
    }

    results = []
    for name in args.models:
        config = model_configs[name]
        if not config["path"].exists():
            print(f"SKIP {name}: {config['path']} not found")
            continue
        print(f"Benchmarking {name} ({config['size']}x{config['size']})...")
        result = benchmark_model(config["path"], config["size"], frames, args.confidence)
        results.append(result)
        print(
            f"  Recall: {result['recall']:.1%} | FPS: {result['fps']:.1f} | Avg: {result['avg_ms']:.1f}ms"
        )

    # Summary table
    print("\n| Model | Recall | FPS | Avg ms |")
    print("|-------|--------|-----|--------|")
    for r in results:
        print(f"| {r['model']} | {r['recall']:.1%} | {r['fps']:.1f} | {r['avg_ms']:.1f} |")

    # Decision criteria
    print("\nSuccess criteria: recall >= YOLOv8n baseline, FPS >= 25")
    for r in results:
        status = "PASS" if r["fps"] >= 25 else "FAIL (FPS)"
        print(f"  {r['model']}: {status}")


if __name__ == "__main__":
    main()
