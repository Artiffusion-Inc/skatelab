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

# Async session for R2
_async_session = aiobotocore.session.get_session()


@app.on_event("startup")
async def warmup_gpu():
    """Pre-warm CUDA/cuDNN to eliminate cold-start latency."""
    from src.device import DeviceConfig

    cfg = DeviceConfig.default()
    if not cfg.is_cuda:
        return
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 2
    # Just importing ort and accessing CUDA provider triggers init
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
    except Exception:
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
    return _async_session.create_client(
        "s3",
        endpoint_url=creds.r2_endpoint_url,
        aws_access_key_id=creds.r2_access_key_id,
        aws_secret_access_key=creds.r2_secret_access_key,
        region_name="auto",
    )


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
        async with await _s3(req) as s3:
            with tempfile.TemporaryDirectory() as tmpdir:
                video_local = Path(tmpdir) / "input.mp4"

                logger.info("Downloading video for detection from R2: %s", req.video_r2_key)
                await s3.download_file(req.r2_bucket, req.video_r2_key, str(video_local))

                cfg = DeviceConfig.default()
                extractor = PoseExtractor(
                    model_path="data/models/moganet/moganet_b_ap2d_384x288.onnx",
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


@app.post("/process", response_model=ProcessResponse)
async def process(req: ProcessRequest):
    from src.types import PersonClick
    from src.utils.frame_buffer import AsyncFrameReader
    from src.utils.video_writer import H264Writer
    from src.visualization.pipeline import VizPipeline, prepare_poses

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        async with await _s3(req) as s3:
            with tempfile.TemporaryDirectory() as tmpdir:
                video_local = Path(tmpdir) / "input.mp4"
                output_local = Path(tmpdir) / "output.mp4"

                logger.info("Downloading video from R2: %s", req.video_r2_key)
                await s3.download_file(req.r2_bucket, req.video_r2_key, str(video_local))

                click = (
                    PersonClick(x=req.person_click["x"], y=req.person_click["y"])
                    if req.person_click
                    else None
                )

                logger.info("Running pipeline (ml_flags=%s)", req.ml_flags)
                prepared = prepare_poses(
                    video_local,
                    person_click=click,
                    frame_skip=req.frame_skip,
                    tracking=req.tracking,
                    progress_cb=None,
                )

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

                frame_idx = 0
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
                    frame_idx += 1

                reader.join(timeout=5)
                writer.close()

                result = {
                    "stats": {
                        "total_frames": meta.num_frames,
                        "valid_frames": prepared.n_valid,
                        "fps": meta.fps,
                        "resolution": f"{meta.width}x{meta.height}",
                    },
                }

                out_key = req.video_r2_key.replace("input/", "output/")
                logger.info("Uploading result to R2: %s", out_key)

                upload_tasks = [s3.upload_file(str(output_local), req.r2_bucket, out_key)]

                poses_key = None
                csv_key = None

                await asyncio.gather(*upload_tasks)

                INFERENCE_REQUESTS.labels(status="success").inc()
                return ProcessResponse(
                    video_r2_key=out_key,
                    poses_r2_key=poses_key,
                    csv_r2_key=csv_key,
                    stats=result["stats"],
                    metrics=result.get("metrics"),
                    phases=result.get("phases"),
                    recommendations=result.get("recommendations"),
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
