# ML Smoke Run

The smoke command exercises the real local ML path on the checked-in SkatingVerse fixture. It validates required models before opening the video and writes a strict-JSON result for backend/UI consumers.

## Model setup

Required files:

- `data/models/moganet_b_ap2d_384x288.onnx`
- `data/models/rf_detr_nano.onnx`

Optional 3D file:

- `data/models/tcpformer/TCPFormer_ap3d_81_fp16.onnx`

Override paths without symlinks with `SKATELAB_MOGANET_MODEL`, `SKATELAB_RF_DETR_MODEL`, and `SKATELAB_TCPFORMER_MODEL`. A missing TCPFormer is reported as `pose_3d: false` with a warning; it does not fail the 2D run.

## Reproducible command

```bash
uv run --frozen --package ml python ml/scripts/smoke_inference.py \
  data/datasets/skatingverse/test_videos/100_0WOWTjJO.mp4 \
  --output /tmp/skatelab-smoke-result.json
```

The output contains `processed_frames`, `valid_frames`, `metrics`, `timings`, enabled `stages`, `warnings`, and normalized H3.6M-17 per-frame `annotations` with frame indices, timestamps, keypoints, and confidence values. Non-finite annotation values are encoded as JSON `null`.

A smoke pass verifies structure, finite timings, frame/index consistency, and usable annotation data. It does not assert a fixed score or claim skating accuracy. Timing is an operational measurement; accuracy requires a labelled benchmark.
