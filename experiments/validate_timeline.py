"""Validate element timeline on 20 test videos.

Measures: F1@50, F1@25, over-segmentation rate, inference time.
"""

import json
import time
from pathlib import Path

import numpy as np

from ml.src.tas.inference import TASElementSegmenter
from ml.src.tas.metrics import MultiOverlapF1

MODEL_PATH = Path("data/models/tas/bigr_refiner_best.onnx")
TEST_DIR = Path("data/datasets/mcfs/features")
LABEL_DIR = Path("data/datasets/mcfs/groundTruth")


def main():
    if not MODEL_PATH.exists():
        print(f"Model not found: {MODEL_PATH}")
        print("Run experiments/train_tas_v2.py first")
        return

    segmenter = TASElementSegmenter(model_path=MODEL_PATH)
    metric = MultiOverlapF1(thresholds=[0.10, 0.25, 0.50])

    test_files = sorted(TEST_DIR.glob("*.npy"))[:20]
    if not test_files:
        print("No test files found")
        return

    all_f1 = []
    inference_times = []
    total_segments = 0
    total_labels = 0

    for fpath in test_files:
        features = np.load(fpath)  # (T, 17, 2)
        if features.ndim == 3 and features.shape[1:] == (17, 2):
            poses = features.astype(np.float32)
        else:
            flat = features.reshape(features.shape[0], 17, 2)
            poses = flat.astype(np.float32)

        t0 = time.perf_counter()
        segments = segmenter.segment(poses, fps=30.0)
        dt = time.perf_counter() - t0
        inference_times.append(dt)

        # Load ground truth if available
        label_file = LABEL_DIR / (fpath.stem + ".txt")
        if label_file.exists():
            true_labels = np.loadtxt(label_file, dtype=int)
            # Convert segments to label sequence
            pred_labels = np.zeros(len(poses), dtype=int)
            for seg in segments:
                type_map = {"None": 0, "Jump": 1, "Spin": 2, "Step": 3}
                label = type_map.get(seg["element_type"], 0)
                pred_labels[seg["start"] : seg["end"] + 1] = label
            result = metric.compute(pred_labels, true_labels)
            all_f1.append(result)
            total_segments += len(segments)
            total_labels += int(np.sum(true_labels > 0))
            print(
                f"{fpath.stem}: f1@50={result['f1@50']:.3f}, f1@25={result['f1@25']:.3f}, {len(segments)} segs, {dt:.2f}s"
            )
        else:
            total_segments += len(segments)
            print(f"{fpath.stem}: {len(segments)} segments, {dt:.2f}s (no ground truth)")

    print("\n=== Summary ===")
    print(f"Files: {len(test_files)}")
    print(f"Segments: {total_segments}")
    if all_f1:
        keys = all_f1[0].keys()
        for k in keys:
            vals = [r[k] for r in all_f1]
            print(f"  {k}: {np.mean(vals):.4f} (+/- {np.std(vals):.4f})")
    print(f"Avg inference time: {np.mean(inference_times):.2f}s")
    if total_labels > 0:
        over_seg = max(0, total_segments - total_labels) / total_labels
        print(f"Over-segmentation rate: {over_seg:.2f}")

    # Save results
    results = {
        "files_tested": len(test_files),
        "total_segments": total_segments,
        "f1_results": {k: float(np.mean([r[k] for r in all_f1])) for k in all_f1[0].keys()}
        if all_f1
        else {},
        "avg_inference_time": float(np.mean(inference_times)),
    }
    out_path = Path("experiments/results/timeline_validation.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
