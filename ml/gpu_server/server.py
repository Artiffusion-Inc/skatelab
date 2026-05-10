"""FastAPI inference server for Vast.ai Serverless GPU worker.

Runs on the remote GPU. Receives R2 keys, processes video, returns results.
R2 credentials are passed per-request so the worker does not store cloud credentials.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

import aiobotocore.session
import numpy as np
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Skating ML GPU Worker")

# Prometheus metrics
INFERENCE_DURATION = Histogram(
    "inference_duration_seconds",
    "Time spent processing a video",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)
INFERENCE_REQUESTS = Counter(
    "inference_requests_total",
    "Total /process requests",
    ["status"],
)
ACTIVE_REQUESTS = Gauge(
    "active_requests",
    "Number of requests currently being processed",
)

# Models are at /app/data/models/ inside the container
os.environ.setdefault("PROJECT_ROOT", "/app")

_PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", "/app"))
MOGANET_MODEL_PATH = _PROJECT_ROOT / "data/models/moganet/moganet_b_ap2d_384x288.onnx"
YOLO_MODEL_PATH = _PROJECT_ROOT / "data/models/yolov8n.onnx"

# R2 keys for each model
_R2_MODELS: list[tuple[Path, str]] = [
    (MOGANET_MODEL_PATH, "models/moganet/moganet_b_ap2d_384x288.onnx"),
    (YOLO_MODEL_PATH, "models/yolov8n.onnx"),
]

# Async session for R2
_async_session = aiobotocore.session.get_session()


async def _download_models_from_r2():
    """Download ONNX models from R2 if missing locally."""
    r2_endpoint = os.environ.get("R2_ENDPOINT_URL", "")
    r2_access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
    r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    r2_bucket = os.environ.get("R2_BUCKET", "")

    if not all([r2_endpoint, r2_access_key, r2_secret, r2_bucket]):
        logger.warning("R2 credentials not set — skipping model downloads")
        return

    import botocore.config

    boto_config = botocore.config.Config(
        connect_timeout=10,
        read_timeout=300,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )
    async with _async_session.create_client(
        "s3",
        endpoint_url=r2_endpoint,
        aws_access_key_id=r2_access_key,
        aws_secret_access_key=r2_secret,
        region_name="auto",
        config=boto_config,
    ) as s3:
        for local_path, r2_key in _R2_MODELS:
            if local_path.exists():
                size_mb = local_path.stat().st_size / 1e6
                logger.info("Model found: %s (%.1f MB)", local_path, size_mb)
                continue

            logger.info("Downloading model from R2: %s → %s", r2_key, local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            resp = await s3.get_object(Bucket=r2_bucket, Key=r2_key)
            body = await resp["Body"].read()
            local_path.write_bytes(body)
            size_mb = len(body) / 1e6
            logger.info("Downloaded: %s (%.1f MB)", local_path, size_mb)


@app.on_event("startup")
async def warmup_gpu():
    """Pre-warm CUDA/cuDNN and download missing models from R2."""
    await _download_models_from_r2()

    from src.device import DeviceConfig

    cfg = DeviceConfig.default()
    if not cfg.is_cuda:
        return
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 2
    logging.getLogger(__name__).info("GPU warmup: CUDA initialized")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/ready")
async def ready():
    """Readiness probe — checks ONNX session health."""
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" not in providers:
            return Response(status_code=503, content='{"status": "no_cuda"}')
        return {"status": "ready"}
    except (ImportError, RuntimeError, OSError):
        return Response(status_code=503, content='{"status": "unhealthy"}')


class DetectRequest(BaseModel):
    video_r2_key: str
    tracking: str = "auto"
    # R2 credentials passed per-request (worker doesn't store them)
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""


class DetectPerson(BaseModel):
    track_id: int
    hits: int
    bbox: list[float]  # [x1, y1, x2, y2] normalized
    mid_hip: list[float]  # [x, y] normalized


class DetectResponse(BaseModel):
    persons: list[DetectPerson]
    preview_image: str  # base64-encoded PNG
    video_key: str
    auto_click: dict[str, int] | None = None
    width: int
    height: int
    status: str


class ProcessRequest(BaseModel):
    video_r2_key: str
    person_click: dict[str, int] | None = None
    frame_skip: int = 1
    layer: int = 3
    tracking: str = "auto"
    export: bool = True
    ml_flags: dict[str, bool] = {}
    element_type: str | None = None
    # R2 credentials passed per-request (worker doesn't store them)
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""


class ProcessResponse(BaseModel):
    video_r2_key: str
    poses_r2_key: str | None = None
    csv_r2_key: str | None = None
    stats: dict
    metrics: list | None = None
    phases: object | None = None
    recommendations: list | None = None


def _s3(creds: ProcessRequest | DetectRequest):
    """Async S3 client factory (returns context manager)."""
    from botocore.config import Config

    cfg = Config(
        connect_timeout=10,
        read_timeout=120,
        retries={"max_attempts": 3, "mode": "adaptive"},
    )
    return _async_session.create_client(
        "s3",
        endpoint_url=creds.r2_endpoint_url,
        aws_access_key_id=creds.r2_access_key_id,
        aws_secret_access_key=creds.r2_secret_access_key,
        region_name="auto",
        config=cfg,
    )


async def _s3_download(s3, bucket: str, key: str, path: str) -> None:
    """Download object from S3 to local file (aiobotocore has no download_file)."""
    resp = await s3.get_object(Bucket=bucket, Key=key)
    body = resp["Body"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("wb") as f:
        while True:
            chunk = await body.read(8 * 1024 * 1024)  # 8 MB chunks
            if not chunk:
                break
            f.write(chunk)


async def _s3_upload(s3, bucket: str, key: str, path: str) -> None:
    """Upload local file to S3 (aiobotocore has no upload_file)."""
    data = Path(path).read_bytes()
    await s3.put_object(Bucket=bucket, Key=key, Body=data)


DETECT_DURATION = Histogram(
    "detect_duration_seconds",
    "Time spent detecting persons in a video",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
DETECT_REQUESTS = Counter(
    "detect_requests_total",
    "Total /detect requests",
    ["status"],
)


@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    import base64

    import cv2

    from src.device import DeviceConfig
    from src.pose_estimation.pose_extractor import PoseExtractor
    from src.utils.video import get_video_meta

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        async with _s3(req) as s3:
            with tempfile.TemporaryDirectory() as tmpdir:
                video_local = Path(tmpdir) / "input.mp4"

                logger.info("Downloading video for detection from R2: %s", req.video_r2_key)
                await _s3_download(s3, req.r2_bucket, req.video_r2_key, str(video_local))

                cfg = DeviceConfig.default()
                extractor = PoseExtractor(
                    model_path=str(MOGANET_MODEL_PATH),
                    tracking_backend="custom",
                    tracking_mode=req.tracking,
                    conf_threshold=0.3,
                    output_format="normalized",
                    device=cfg.device,
                )
                persons, _ = extractor.preview_persons(video_local, num_frames=30)

                if not persons:
                    return DetectResponse(
                        persons=[],
                        preview_image="",
                        video_key=req.video_r2_key,
                        auto_click=None,
                        width=0,
                        height=0,
                        status="Люди не найдены. Попробуйте другое видео.",
                    )

                meta = get_video_meta(video_local)
                w, h = meta.width, meta.height

                # Render preview with bounding boxes
                cap = cv2.VideoCapture(str(video_local))
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    raise RuntimeError("Failed to read video frame")

                annotated = _render_person_preview(frame, persons)
                success, buf = cv2.imencode(".png", annotated)
                if not success:
                    raise RuntimeError("Failed to encode preview image")
                preview_b64 = base64.b64encode(buf).decode("ascii")

                # Auto-click: if only 1 person, select automatically
                auto_click = None
                status_msg: str
                if len(persons) == 1:
                    mid_hip = persons[0]["mid_hip"]
                    auto_click = {"x": int(mid_hip[0] * w), "y": int(mid_hip[1] * h)}
                    status_msg = "Обнаружен 1 человек — выбран автоматически"
                else:
                    status_msg = (
                        f"Обнаружено {len(persons)} человек. Выберите на превью или из списка."
                    )

                persons_out = [
                    DetectPerson(
                        track_id=p["track_id"],
                        hits=p["hits"],
                        bbox=p["bbox"],
                        mid_hip=p["mid_hip"],
                    )
                    for p in persons
                ]

                DETECT_REQUESTS.labels(status="success").inc()
                return DetectResponse(
                    persons=persons_out,
                    preview_image=preview_b64,
                    video_key=req.video_r2_key,
                    auto_click=auto_click,
                    width=w,
                    height=h,
                    status=status_msg,
                )
    except Exception:
        DETECT_REQUESTS.labels(status="error").inc()
        raise
    finally:
        ACTIVE_REQUESTS.dec()
        DETECT_DURATION.observe(time.perf_counter() - start)


def _render_person_preview(frame, persons, selected_idx=None):
    """Draw person bounding boxes on frame."""
    import cv2

    annotated = frame.copy()
    h, w = frame.shape[:2]
    colors = [(255, 165, 0), (0, 200, 200), (200, 100, 0), (200, 0, 200), (0, 180, 255)]
    for i, p in enumerate(persons):
        x1, y1, x2, y2 = p["bbox"]
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        if selected_idx is not None and i == selected_idx:
            color = (0, 255, 0)
            thickness = 3
        else:
            color = colors[i % len(colors)]
            thickness = 2
        cv2.rectangle(annotated, (px1, py1), (px2, py2), color, thickness)
        label = f"#{i + 1} (hits: {p['hits']})"
        cv2.rectangle(annotated, (px1, py1 - 28), (px1 + len(label) * 10 + 10, py1), color, -1)
        cv2.putText(
            annotated,
            label,
            (px1 + 5, py1 - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return annotated


def _make_output_keys(video_r2_key: str) -> tuple[str, str, str]:
    """Generate R2 output keys: (video_key, poses_key, csv_key).

    'uploads/abc/input.mp4' → 'uploads/abc/output.mp4'
    'uploads/test/waltz.mp4' → 'output/uploads/test/waltz.mp4'
    """
    p = Path(video_r2_key)
    if p.stem == "input":
        out_video = str(p.with_name("output" + p.suffix))
    else:
        out_video = f"output/{video_r2_key}"

    base = out_video.rsplit(".", 1)[0]
    return out_video, f"{base}_poses.npy", f"{base}_metrics.json"


@app.post("/process", response_model=ProcessResponse)
async def process(req: ProcessRequest):
    from src.types import ElementPhase, PersonClick
    from src.utils.frame_buffer import AsyncFrameReader
    from src.utils.video_writer import H264Writer
    from src.visualization.pipeline import VizPipeline, prepare_poses

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        async with _s3(req) as s3:
            with tempfile.TemporaryDirectory() as tmpdir:
                video_local = Path(tmpdir) / "input.mp4"
                output_local = Path(tmpdir) / "output.mp4"

                logger.info("Downloading video from R2: %s", req.video_r2_key)
                await _s3_download(s3, req.r2_bucket, req.video_r2_key, str(video_local))

                click = (
                    PersonClick(x=req.person_click["x"], y=req.person_click["y"])
                    if req.person_click
                    else None
                )

                logger.info(
                    "Running pipeline (element=%s, ml_flags=%s)", req.element_type, req.ml_flags
                )
                prepared = prepare_poses(
                    video_local,
                    person_click=click,
                    frame_skip=req.frame_skip,
                    tracking=req.tracking,
                    progress_cb=None,
                )

                # --- Biomechanics analysis (after pose extraction, before render) ---
                metrics: list = []
                phases: ElementPhase | None = None
                recommendations: list = []

                if req.element_type:
                    from src.analysis import element_defs
                    from src.analysis.metrics import BiomechanicsAnalyzer
                    from src.analysis.phase_detector import PhaseDetector
                    from src.analysis.recommender import Recommender

                    element_def = element_defs.get_element_def(req.element_type)
                    if element_def is not None:
                        phase_detector = PhaseDetector()
                        phase_result = phase_detector.detect_phases(
                            prepared.poses_norm, prepared.meta.fps, req.element_type
                        )
                        phases = phase_result.phases

                        analyzer = BiomechanicsAnalyzer(element_def)
                        metrics = analyzer.analyze(prepared.poses_norm, phases, prepared.meta.fps)

                        recommender = Recommender()
                        recommendations = recommender.recommend(metrics, req.element_type)

                # --- Render video with skeleton overlay ---
                pipe = VizPipeline(
                    meta=prepared.meta,
                    poses_norm=prepared.poses_norm,
                    poses_px=prepared.poses_px,
                    poses_3d=prepared.poses_3d,
                    layer=req.layer,
                    confs=prepared.confs,
                    frame_indices=prepared.frame_indices,
                )

                meta = prepared.meta
                writer = H264Writer(output_local, meta.width, meta.height, meta.fps)
                reader = AsyncFrameReader(video_local, buffer_size=16, frame_skip=1)
                reader.start()

                pose_idx = 0
                while True:
                    result = reader.get_frame()
                    if result is None:
                        break
                    fi, frame = result
                    current_pose_idx, pose_idx = pipe.find_pose_idx(fi, pose_idx)
                    frame, _ = pipe.render_frame(frame, fi, current_pose_idx)
                    pipe.draw_frame_counter(frame, fi)
                    writer.write(frame)

                reader.join(timeout=5)
                writer.close()

                # --- Upload results to R2 ---
                out_video_key, poses_key, csv_key = _make_output_keys(req.video_r2_key)
                logger.info("Uploading results to R2: %s", out_video_key)

                upload_tasks = [_s3_upload(s3, req.r2_bucket, out_video_key, str(output_local))]

                # Save poses as .npy
                poses_local = Path(tmpdir) / "poses.npy"
                np.save(str(poses_local), prepared.poses_norm)
                upload_tasks.append(_s3_upload(s3, req.r2_bucket, poses_key, str(poses_local)))

                # Save metrics + phases + recommendations as JSON
                import json as _json

                metrics_json = Path(tmpdir) / "metrics.json"
                metrics_data = {
                    "stats": {
                        "total_frames": meta.num_frames,
                        "valid_frames": prepared.n_valid,
                        "fps": meta.fps,
                        "resolution": f"{meta.width}x{meta.height}",
                    },
                    "metrics": [
                        {"name": m.name, "value": m.value, "unit": m.unit, "is_good": m.is_good}
                        for m in metrics
                    ],
                    "phases": phases.__dict__ if phases else None,
                    "recommendations": recommendations,
                    "element_type": req.element_type,
                }
                metrics_json.write_text(_json.dumps(metrics_data, ensure_ascii=False, indent=2))
                upload_tasks.append(_s3_upload(s3, req.r2_bucket, csv_key, str(metrics_json)))

                await asyncio.gather(*upload_tasks)

                INFERENCE_REQUESTS.labels(status="success").inc()
                return ProcessResponse(
                    video_r2_key=out_video_key,
                    poses_r2_key=poses_key,
                    csv_r2_key=csv_key,
                    stats=metrics_data["stats"],
                    metrics=metrics_data["metrics"],
                    phases=metrics_data["phases"],
                    recommendations=recommendations,
                )
    except Exception:
        INFERENCE_REQUESTS.labels(status="error").inc()
        raise
    finally:
        ACTIVE_REQUESTS.dec()
        INFERENCE_DURATION.observe(time.perf_counter() - start)


@app.get("/health")
async def health():
    return {"status": "ok"}
