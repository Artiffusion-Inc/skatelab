# ML

Pure GPU-oriented ML library. No backend, database, queue, or web-framework dependencies.

## Entry Points

- `src/pipeline.py` — analysis orchestration.
- `src/types.py` — stable H3.6M and report types.
- `src/pose_estimation/` — MogaNet-B pose extraction and target tracking.
- `src/pose_3d/` — TCPFormer/ONNX 3D lifting.
- `src/analysis/` — phases, metrics, physics, GOE, recommendations.
- `src/tracking/` — DeepSORT, fallback association, identity and tracklet merge.
- `gpu_server/` — Vast.ai inference service and image.

## Rules

- CUDA inference only. Run `bash ml/scripts/setup_cuda_compat.sh` after `uv sync`.
- Primary pose representation is H3.6M 17 keypoints. Make normalized/pixel and 2D/3D shapes explicit.
- Keep model loading lazy and release GPU sessions when pipeline stages finish.
- Do not guess tracking fixes: extract trajectories and identify exact divergence frame/layer.
- Anti-steal combines position and skeletal signals with AND, not OR.
- Preserve NaN semantics through gap filling, smoothing, metrics, and serialization.
- Experiments stay in `experiments/` until validated and intentionally integrated.

## Verify

```bash
uv run pytest ml/tests/ -v --tb=short --import-mode=importlib
uv run ruff check ml/
uv run basedpyright --level error ml/src
```

GPU/integration tests require compatible hardware and model assets; report skipped coverage explicitly.
