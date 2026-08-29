#!/usr/bin/env python3
"""Inspect a SkateLab Android .binpb stream without loading ML models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.sensor_fusion import decode_imu_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to left.binpb or right.binpb")
    parser.add_argument("--t0-ns", type=int, default=0, help="Capture anchor from manifest.json")
    parser.add_argument("--manifest", type=Path, help="Manifest JSON (auto-reads t0_ns)")
    args = parser.parse_args()

    if args.manifest:
        manifest = json.loads(args.manifest.read_text())
        args.t0_ns = int(manifest.get("t0_ns", args.t0_ns) or 0)
    stream = decode_imu_file(args.path)
    print(json.dumps({
        "path": str(args.path),
        "samples": len(stream.timestamps_ns),
        "gaps": stream.gaps,
        "sample_rate_hz": round(stream.sample_rate_hz, 3),
        "first_timestamp_ns": stream.timestamps_ns[0] if stream.timestamps_ns else None,
        "last_timestamp_ns": stream.timestamps_ns[-1] if stream.timestamps_ns else None,
        "angular_velocity": stream.angular_velocity_summary(args.t0_ns),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
