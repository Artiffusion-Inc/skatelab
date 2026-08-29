"""FastAPI inference server for Vast.ai Serverless GPU worker.

Runs on the remote GPU. Receives S3 keys, processes video, returns results.
S3 credentials are passed per-request so the worker does not store cloud credentials.

Output: poses (.npy) + metrics (.json) — no video render.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiobotocore.session
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import Response

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

# File handler for PyWorker log monitoring (Vast.ai Serverless reads this)
_log_file = os.environ.get("MODEL_LOG_FILE", "/tmp/skatelab-server.log")  # noqa: S108
_fh = logging.FileHandler(_log_file)
_fh.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
logging.getLogger().addHandler(_fh)


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """Verify models in background while keeping server startup responsive."""
    background_task = asyncio.create_task(_background_init())
    try:
        yield
    finally:
        background_task.cancel()
        await asyncio.gather(background_task, return_exceptions=True)


app = FastAPI(title="Skating ML GPU Worker", lifespan=app_lifespan)

# Prometheus metrics
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

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
MOGANET_MODEL_PATH = _PROJECT_ROOT / "data/models/moganet/moganet_b_ap2d_384x288_fp16.onnx"
RF_DETR_MODEL_PATH = _PROJECT_ROOT / "data/models/rf_detr_nano_fp16.onnx"
TAS_MODEL_PATH = _PROJECT_ROOT / "data/models/tas/bigr_refiner_best.onnx"
TCPFORMER_MODEL_PATH = _PROJECT_ROOT / "data/models/tcpformer/TCPFormer_ap3d_81_fp16.onnx"

# S3 keys for each model
_S3_MODELS: list[tuple[Path, str]] = [
    (MOGANET_MODEL_PATH, "models/moganet/moganet_b_ap2d_384x288_fp16.onnx"),
    (RF_DETR_MODEL_PATH, "models/rf_detr_nano_fp16.onnx"),
    (TAS_MODEL_PATH, "models/tas/bigr_refiner_best.onnx"),
    (TCPFORMER_MODEL_PATH, "models/tcpformer/TCPFormer_ap3d_81_fp16.onnx"),
]

# TAS segmenter (loaded at startup, None if model unavailable)
_tas_segmenter = None
# Async session for S3
_async_session = aiobotocore.session.get_session()


_models_ready = False


async def _background_init():
    """Download models + warmup CUDA — runs after server is accepting requests."""
    global _models_ready, _tas_segmenter, _tcpformer_extractor  # noqa: PLW0603
    try:
        if not MOGANET_MODEL_PATH.exists():
            raise OSError(f"Model not found: {MOGANET_MODEL_PATH}")
        if not RF_DETR_MODEL_PATH.exists():
            raise OSError(f"Model not found: {RF_DETR_MODEL_PATH}")

        from src.device import DeviceConfig

        cfg = DeviceConfig.default()
        if cfg.is_cuda:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 2
            logger.info("GPU warmup: CUDA initialized")

        # Load TAS segmenter if the model file exists. The TAS package imports torch
        # (src.tas.classifier), which is NOT installed in the serverless GPU image (it
        # ships onnxruntime only). Skip the import entirely when the model is absent so
        # we never raise ModuleNotFoundError → Traceback → PyWorker fatal error.
        if not TAS_MODEL_PATH.exists():
            logger.warning("TAS model not found at %s — timeline unavailable", TAS_MODEL_PATH)
        else:
            try:
                from src.tas.inference import TASElementSegmenter

                _tas_segmenter = TASElementSegmenter(model_path=str(TAS_MODEL_PATH))
                logger.info("TAS segmenter loaded at startup (ONNX)")
            except (ImportError, ValueError, RuntimeError, OSError):
                logger.warning("TAS segmenter not loaded — timeline unavailable", exc_info=True)

        # Load TCPFormer 3D lifter if model exists
        _tcpformer_extractor = None
        try:
            from src.pose_3d.model_downloader import resolve_model

            tcpformer_path = resolve_model("tcpformer", device=cfg.device)
            if tcpformer_path is not None:
                from src.pose_3d.onnx_extractor import ONNXPoseExtractor

                _tcpformer_extractor = ONNXPoseExtractor(
                    model_path=tcpformer_path,
                    device=cfg.device,
                    temporal_window=81,
                )
                logger.info("TCPFormer 3D lifter loaded at startup (ONNX)")
            else:
                logger.warning("TCPFormer model unavailable — 3D lift disabled")
        except (ValueError, RuntimeError, OSError):
            logger.warning("TCPFormer not loaded — 3D lift disabled", exc_info=True)

        _models_ready = True
        logger.info("Background init complete — models ready")
    except (OSError, ValueError, RuntimeError):
        logger.exception("Background init failed")
        _models_ready = False


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/ready")
async def ready():
    """Readiness probe — returns 200 once server is up (models load in background)."""
    if not _models_ready:
        return {"status": "initializing", "detail": "models initializing"}
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" not in providers:
            return {"status": "ready", "gpu": "cpu_fallback"}
        return {"status": "ready", "gpu": "cuda"}
    except (ImportError, RuntimeError, OSError):
        return {"status": "ready", "gpu": "unknown"}


class DetectRequest(BaseModel):
    video_s3_key: str
    tracking: str = "auto"
    # S3 credentials passed per-request (worker doesn't store them)
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""


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
    video_s3_key: str
    person_click: dict[str, int] | None = None
    frame_skip: int = 1
    layer: int = 3
    tracking: str = "auto"
    ml_flags: dict[str, bool] = {}
    element_type: str | None = None
    isu_code: str | None = None
    lang: str = "ru"
    imu_left_s3_key: str | None = None
    imu_right_s3_key: str | None = None
    manifest_s3_key: str | None = None
    # S3 credentials passed per-request (worker doesn't store them)
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""


class ProcessResponse(BaseModel):
    poses_s3_key: str | None = None
    poses_3d_s3_key: str | None = None
    metrics_s3_key: str | None = None
    stats: dict
    metrics: list | None = None
    phases: object | None = None
    recommendations: list | None = None
    goe_grade: dict | None = None
    segments: list[dict] | None = None
    rotations: int | None = None
    imu_stats: dict[str, object] | None = None
    sensor_fusion: dict[str, object] | None = None


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
        endpoint_url=creds.s3_endpoint_url,
        aws_access_key_id=creds.s3_access_key_id,
        aws_secret_access_key=creds.s3_secret_access_key,
        region_name="us-east-1",
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
    if not _models_ready:
        return Response(status_code=503, content='{"status": "models_loading"}')
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

                logger.info("Downloading video for detection from S3: %s", req.video_s3_key)
                await _s3_download(s3, req.s3_bucket, req.video_s3_key, str(video_local))

                imu_stats: dict[str, object] = {}
                imu_fusion: dict[str, object] = {}
                from src.sensor_fusion import (
                    ImuStream,
                    annotate_video_phase,
                    decode_imu_file,
                    fused_confidence,
                    landing_stability,
                    summarize_pair,
                )

                imu_streams: dict[str, ImuStream] = {}

                capture_t0_ns = 0
                if req.manifest_s3_key:
                    manifest_local = Path(tmpdir) / "manifest.json"
                    await _s3_download(s3, req.s3_bucket, req.manifest_s3_key, str(manifest_local))
                    manifest = json.loads(manifest_local.read_text())
                    capture_t0_ns = int(manifest.get("t0_ns", 0) or 0)

                for side, key in (("left", req.imu_left_s3_key), ("right", req.imu_right_s3_key)):
                    if not key:
                        continue
                    imu_local = Path(tmpdir) / f"{side}.binpb"
                    await _s3_download(s3, req.s3_bucket, key, str(imu_local))
                    stream = decode_imu_file(imu_local)
                    imu_streams[side] = stream
                    imu_stats[side] = {
                        "samples": len(stream.timestamps_ns),
                        "gaps": stream.gaps,
                        "sample_rate_hz": round(stream.sample_rate_hz, 3),
                        "first_timestamp_ns": stream.timestamps_ns[0] if stream.timestamps_ns else None,
                        "last_timestamp_ns": stream.timestamps_ns[-1] if stream.timestamps_ns else None,
                    }
                    imu_fusion[side] = stream.angular_velocity_summary(capture_t0_ns)

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
                        video_key=req.video_s3_key,
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
                    video_key=req.video_s3_key,
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


def _make_output_keys(video_s3_key: str) -> tuple[str, str]:
    """Generate S3 output keys: (poses_key, metrics_key).

    'uploads/abc/input.mp4' → poses='uploads/abc/output_poses.npy', metrics='uploads/abc/output_metrics.json'
    'uploads/test/waltz.mp4' → poses='output/uploads/test/waltz_poses.npy', metrics='output/uploads/test/waltz_metrics.json'
    """
    p = Path(video_s3_key)
    if p.stem == "input":
        base = str(p.with_name("output"))
    else:
        base = f"output/{video_s3_key.rsplit('.', 1)[0]}"

    return f"{base}_poses.npy", f"{base}_metrics.json"


@app.post("/process", response_model=ProcessResponse)
async def process(req: ProcessRequest):
    if not _models_ready:
        return Response(status_code=503, content='{"status": "models_loading"}')
    from src.pose_preparation import prepare_poses
    from src.types import ElementPhase, PersonClick

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()
    try:
        async with _s3(req) as s3:
            with tempfile.TemporaryDirectory() as tmpdir:
                video_local = Path(tmpdir) / "input.mp4"

                logger.info("Downloading video from S3: %s", req.video_s3_key)
                await _s3_download(s3, req.s3_bucket, req.video_s3_key, str(video_local))

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

                poses_3d_norm = None
                poses_3d_key = ""

                # --- TAS element segmentation (concurrent with biomechanics) ---
                def _run_tas_sync():
                    """Blocking TAS ONNX inference — runs in thread pool for true parallelism."""
                    if _tas_segmenter is None:
                        return None
                    segs = _tas_segmenter.segment(prepared.poses_norm, fps=prepared.meta.fps)
                    return [
                        {
                            "element_type": s["element_type"],
                            "start": s["start"],
                            "end": s["end"],
                            "confidence": s["confidence"],
                        }
                        for s in segs
                    ]

                # Offload TAS to thread — asyncio.create_task does NOT parallelize CPU/GPU code
                segments_coro = asyncio.to_thread(_run_tas_sync)

                # --- Biomechanics analysis ---
                metrics: list = []
                phases: ElementPhase | None = None
                recommendations: list = []
                rotations: int = 0

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
                        rotations = phase_result.rotations

                        analyzer = BiomechanicsAnalyzer(element_def)
                        metrics = analyzer.analyze(prepared.poses_norm, phases, prepared.meta.fps)

                        # ISU GOE grading
                        goe_grade = None
                        if req.isu_code:
                            from src.analysis.goe_grader import GOEGrader
                            from src.utils.isu_loader import load_sov_entry

                            grader = GOEGrader()
                            entry = load_sov_entry(req.isu_code)
                            bv = entry["base_value"] if entry else 0.0
                            expected_rot = entry.get("rotations", element_def.rotations)
                            goe_grade = grader.compute_goe_grade(
                                metrics, base_value=bv, expected_rotations=expected_rot
                            )

                        recommender = Recommender()
                        recommendations = recommender.recommend_with_goe(
                            metrics, req.element_type, goe_grade, lang=req.lang
                        )

                # --- 3D Lift (TCPFormer) ---
                if _tcpformer_extractor is not None:
                    try:
                        from src.pose_estimation.normalizer import PoseNormalizer

                        poses_3d_raw = _tcpformer_extractor.estimate_3d(prepared.poses_norm)
                        normalizer_3d = PoseNormalizer(target_spine_length=0.4)
                        poses_3d_norm = normalizer_3d.normalize_3d(poses_3d_raw)
                        logger.info("3D lift complete: %d frames", len(poses_3d_norm))
                    except Exception:
                        logger.warning("3D lift failed — continuing with 2D", exc_info=True)

                # Wait for TAS to finish
                segments_result = await segments_coro

                if "left" in imu_streams and "right" in imu_streams:
                    imu_fusion["pair"] = summarize_pair(imu_streams["left"], imu_streams["right"])
                if phases is not None:
                    for side in ("left", "right"):
                        if side in imu_fusion:
                            imu_fusion[side] = annotate_video_phase(
                                imu_fusion[side],
                                fps=prepared.meta.fps,
                                takeoff=phases.takeoff,
                                landing=phases.landing,
                            )
                if "left" in imu_fusion and "right" in imu_fusion and "pair" in imu_fusion:
                    imu_fusion["confidence"] = fused_confidence(
                        imu_fusion["left"], imu_fusion["right"], imu_fusion["pair"]
                    )
                if phases is not None:
                    for side, stream in imu_streams.items():
                        imu_fusion.setdefault("landing_stability", {})[side] = landing_stability(
                            stream,
                            t0_ns=capture_t0_ns,
                            fps=prepared.meta.fps,
                            landing_frame=phases.landing,
                        )
                # --- Upload results to S3 ---
                poses_key, metrics_key = _make_output_keys(req.video_s3_key)
                upload_tasks = []

                logger.info("Uploading poses + metrics to S3")

                # Save poses as .npy
                poses_local = Path(tmpdir) / "poses.npy"
                np.save(str(poses_local), prepared.poses_norm)
                upload_tasks.append(_s3_upload(s3, req.s3_bucket, poses_key, str(poses_local)))

                # Save 3D poses if available
                if poses_3d_norm is not None:
                    poses_3d_local = Path(tmpdir) / "poses_3d.npy"
                    np.save(str(poses_3d_local), poses_3d_norm)
                    poses_3d_key = poses_key.replace("_poses.npy", "_poses_3d.npy")
                    upload_tasks.append(
                        _s3_upload(s3, req.s3_bucket, poses_3d_key, str(poses_3d_local))
                    )

                # Save metrics + phases + recommendations as JSON
                metrics_json = Path(tmpdir) / "metrics.json"
                metrics_data = {
                    "stats": {
                        "total_frames": prepared.meta.num_frames,
                        "valid_frames": prepared.n_valid,
                        "fps": prepared.meta.fps,
                        "resolution": f"{prepared.meta.width}x{prepared.meta.height}",
                    },
                    "metrics": [
                        {"name": m.name, "value": m.value, "unit": m.unit, "is_good": m.is_good}
                        for m in metrics
                    ],
                    "phases": phases.__dict__ if phases else None,
                    "recommendations": recommendations,
                    "goe_grade": (
                        {
                            "grade": goe_grade.grade,
                            "base_value": goe_grade.base_value,
                            "estimated_score": goe_grade.estimated_score,
                            "modifier": goe_grade.modifier,
                            "positives": goe_grade.positives,
                            "negatives": goe_grade.negatives,
                            "confidence": goe_grade.confidence,
                        }
                        if goe_grade
                        else None
                    ),
                    "element_type": req.element_type,
                    "rotations": rotations,
                    "imu_stats": imu_stats or None,
                    "sensor_fusion": imu_fusion or None,
                }
                # #488: NaN/Infinity coerce + allow_nan=False. Pre-fix
                # `json.dumps(..., allow_nan=True)` (the default) serialized
                # a raw `NaN` literal into the S3 metrics.json artifact,
                # which is invalid per RFC 8259 (only null + number
                # literals are valid) and crashes any strict-JSON
                # consumer (JS JSON.parse, RustFS audit tooling, etc).
                # The backend worker sanitizes NaN→None in its own
                # frame-metrics path (worker.py:194-197) but gpu_server
                # bypasses that — mirror the same pattern here. The
                # metrics list is dicts (post-PhaseDetectionResult
                # Pydantic serialization), so we coerce via dict key
                # access rather than `.value` attribute.
                sanitized_metrics = []
                for m in metrics_data["metrics"]:
                    mm = m if isinstance(m, dict) else m.model_dump()
                    if math.isfinite(mm.get("value", 0) or 0):
                        sanitized_metrics.append(mm)
                    else:
                        sanitized_metrics.append({**mm, "value": None})
                sanitized_payload = {**metrics_data, "metrics": sanitized_metrics}
                metrics_json.write_text(
                        json.dumps(
                        sanitized_payload,
                        ensure_ascii=False,
                        indent=2,
                        allow_nan=False,  # raise on remaining NaN (defense in depth)
                    )
                )
                upload_tasks.append(_s3_upload(s3, req.s3_bucket, metrics_key, str(metrics_json)))

                await asyncio.gather(*upload_tasks)

                INFERENCE_REQUESTS.labels(status="success").inc()
                return ProcessResponse(
                    poses_s3_key=poses_key,
                    poses_3d_s3_key=poses_3d_key if poses_3d_norm is not None else None,
                    metrics_s3_key=metrics_key,
                    stats=metrics_data["stats"],
                    metrics=metrics_data["metrics"],
                    phases=metrics_data["phases"],
                    recommendations=recommendations,
                    goe_grade=metrics_data.get("goe_grade"),
                    segments=segments_result,
                    rotations=metrics_data.get("rotations"),
                    imu_stats=metrics_data.get("imu_stats"),
                    sensor_fusion=metrics_data.get("sensor_fusion"),
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


@app.post("/ping")
async def ping():
    """Lightweight liveness probe for Vast.ai PyWorker benchmarks."""
    return {"status": "ok"}
