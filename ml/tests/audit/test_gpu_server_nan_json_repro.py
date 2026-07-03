"""RED repro: ML gpu_server serializes metrics with raw NaN literal -> invalid JSON.

Bug (#NNN, HIGH):
  ml/gpu_server/server.py:592
      metrics_json.write_text(_json.dumps(metrics_data, ensure_ascii=False, indent=2))
  `json.dumps` defaults `allow_nan=True` -> emits raw `NaN` / `Infinity` tokens,
  which are INVALID per RFC 8259 (only `null` / number literals allowed). The
  inline `ProcessResponse` at line ~598-609 is serialized by FastAPI with the
  SAME default, so the HTTP response body carries the raw `NaN` too.

  Metric values from BiomechanicsAnalyzer can be NaN in production:
    metrics.py:1413 compute_rotation_speed
      return float(np.max(np.abs(flight_velocity)))
    flight_velocity is NaN when shoulder keypoints are NaN (missed detections
    in low-light / distant-camera rink video):
      np.arctan2(nan, nan) = nan -> np.degrees(nan) = nan
      -> compute_angular_velocity propagates nan -> np.max(abs(nan)) = nan.

  The backend arq worker sanitizes NaN->None in its OWN frame-metrics path
  (backend/app/worker.py:194-197 to_list), but gpu_server's `metrics_data` dict
  BYPASSES that sanitizer and serializes raw metric values.

End-to-end chain (corrected by this repro):
  gpu_server writes an invalid metrics.json to S3 at server.py:592 (raw `NaN`
  literal). The inline ProcessResponse (server.py:598-609) is Pydantic-
  serialized, which coerces NaN->null, so the HTTP body is NOT corrupted. The
  backend consumes `result.get("metrics")` from the inline response
  (vastai/client.py:187) -> session_saver stores `None` (NULL, not NaN) in
  SessionMetric -> the DB->frontend chain does NOT carry NaN. So today the bug
  is LATENT: the persisted S3 metrics.json artifact is invalid JSON, but no
  current Python consumer re-reads the artifact (json.loads tolerates NaN
  anyway). The corruption detonates for any non-Python / strict-JSON consumer
  of the S3 artifact (JS JSON.parse throws "Unexpected identifier NaN", RustFS
  audit, export pipelines, a future reprocess path that re-reads the artifact).

Repro strategy:
  Mock the heavy stages so /process completes and reaches the metrics
  serialization at server.py:592. Capture (a) the S3-uploaded metrics.json
  content (read inside the _s3_upload mock, since the temp dir is torn down
  post-request) and (b) the inline HTTP response body. Assert BOTH contain the
  literal `NaN` (which JS JSON.parse rejects) -- i.e. the bug is present now
  (RED). No real GPU / ONNX / S3 / model files needed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import gpu_server.server as srv
import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.types import ElementPhase, MetricResult

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

_NAN_METRIC = MetricResult(
    name="rotation_speed",
    value=float("nan"),  # the bug: raw NaN reaches the serializer
    unit="deg/s",
    is_good=False,
    reference_range=(0.0, 0.0),
)


def _fake_prepared():
    """NaN-free PreparedPoses stand-in (only fields the /process handler reads)."""
    poses = np.zeros((10, 17, 2), dtype=np.float32)  # valid, no NaN
    meta = SimpleNamespace(width=1280, height=720, fps=30.0, num_frames=10)
    return SimpleNamespace(
        poses_norm=poses,
        poses_px=np.zeros((10, 17, 3), dtype=np.float32),
        poses_3d=None,
        confs=np.ones((10, 17), dtype=np.float32),
        frame_indices=np.arange(10),
        meta=meta,
        n_valid=10,
        n_total=10,
    )


def _fake_phase_result():
    """PhaseDetectionResult stand-in with a valid ElementPhase."""
    phases = ElementPhase(name="waltz_jump", start=0, takeoff=2, peak=5, landing=8, end=9)
    return SimpleNamespace(phases=phases, confidence=0.9, rotations=1)


# ---------------------------------------------------------------------------
# Fixtures: mock the heavy ML stages + S3
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    # Neutralize the startup background init (it would race on _models_ready and
    # try to load onnxruntime). Pretend models are ready so /process doesn't 503.
    async def _noop_bg():
        return None

    monkeypatch.setattr(srv, "_background_init", _noop_bg)
    monkeypatch.setattr(srv, "_models_ready", True, raising=True)
    # TAS segmenter disabled so the concurrent _run_tas_sync path is skipped.
    monkeypatch.setattr(srv, "_tas_segmenter", None, raising=True)
    # 3D lifter disabled (referenced at server.py:526; only assigned inside the
    # background init we just no-op'd, so define it here).
    monkeypatch.setattr(srv, "_tcpformer_extractor", None, raising=False)

    # prepare_poses: import happens inside the handler as
    # `from src.pose_preparation import prepare_poses` -> patch on that module.
    import src.pose_preparation as pp

    monkeypatch.setattr(pp, "prepare_poses", lambda *a, **kw: _fake_prepared())

    # PhaseDetector / BiomechanicsAnalyzer / Recommender are imported inside the
    # handler from src.analysis.{phase_detector,metrics,recommender}.
    import src.analysis.metrics as m_mod
    import src.analysis.phase_detector as pd_mod
    import src.analysis.recommender as r_mod

    fake_pd = MagicMock()
    fake_pd.detect_phases.return_value = _fake_phase_result()
    monkeypatch.setattr(pd_mod, "PhaseDetector", lambda: fake_pd)

    fake_an = MagicMock()
    fake_an.analyze.return_value = [_NAN_METRIC]
    monkeypatch.setattr(m_mod, "BiomechanicsAnalyzer", lambda element_def: fake_an)

    fake_rec = MagicMock()
    fake_rec.recommend_with_goe.return_value = []
    monkeypatch.setattr(r_mod, "Recommender", lambda: fake_rec)

    # S3: no-op download; upload captures the metrics.json content if the key
    # matches so we can inspect what was serialized to S3.
    captured: dict[str, str] = {}

    async def _fake_download(s3, bucket, key, path):
        Path_like = __import__("pathlib").Path
        Path_like(path).parent.mkdir(parents=True, exist_ok=True)
        Path_like(path).write_bytes(b"\x00")  # dummy non-empty file

    async def _fake_upload(s3, bucket, key, path):
        Path_like = __import__("pathlib").Path
        if key.endswith("metrics.json"):
            captured["metrics_json"] = Path_like(path).read_text()
        # poses .npy uploads are ignored.

    monkeypatch.setattr(srv, "_s3_download", _fake_download)
    monkeypatch.setattr(srv, "_s3_upload", _fake_upload)

    # Expose captured content via the client container.
    with TestClient(srv.app) as c:
        c._captured = captured  # type: ignore[attr-defined]
        yield c


# ---------------------------------------------------------------------------
# RED repro
# ---------------------------------------------------------------------------


def test_gpu_server_metrics_json_contains_nan_literal(client):
    """S3-bound metrics.json carries a raw `NaN` token (RFC 8259 violation).

    Current code (RED): server.py:592
        metrics_json.write_text(_json.dumps(metrics_data, ensure_ascii=False, indent=2))
    `json.dumps` defaults `allow_nan=True` -> emits raw `NaN`/`Infinity` tokens,
    which are INVALID per RFC 8259 (only `null` / number literals allowed).

    Metric values from BiomechanicsAnalyzer can be NaN in production:
      metrics.py:1413 compute_rotation_speed returns
        float(np.max(np.abs(flight_velocity)))
      flight_velocity is NaN when shoulder keypoints are NaN (missed detections
      in low-light / distant-camera rink video): np.arctan2(nan,nan)=nan ->
      np.degrees(nan)=nan -> velocity propagates nan -> np.max(abs(nan))=nan.

    The backend arq worker sanitizes NaN->None in its OWN frame-metrics path
    (backend/app/worker.py:194-197 to_list), but gpu_server's `metrics_data` dict
    BYPASSES that sanitizer and serializes raw metric values into the S3
    metrics.json artifact. The inline ProcessResponse (server.py:598-609) is
    Pydantic-serialized, which coerces NaN->null, so the HTTP body is NOT
    corrupted -- but the persisted S3 metrics.json artifact IS.

    Impact: the S3 metrics.json is invalid JSON. Python json.loads tolerates NaN
    by default (so the current backend, which consumes `result.get("metrics")`
    from the inline response, ingests the Pydantic-coerced None and is fine), but
    any non-Python / strict-JSON consumer of the S3 artifact (JS, RustFS audit,
    export, a future reprocess path that re-reads the artifact) breaks: JS
    JSON.parse throws "Unexpected identifier NaN". Silent corruption of the
    persisted ML output artifact.

    Fix (DO NOT apply here): mirror the worker sanitizer -- pass
    `allow_nan=False` and coerce NaN/Infinity in metrics_data["metrics"] values
    to None before the `_json.dumps` call at server.py:592.
    """
    req = {
        "video_s3_key": "uploads/abc/input.mp4",
        "person_click": {"x": 100, "y": 100},
        "frame_skip": 1,
        "layer": 3,
        "tracking": "auto",
        "ml_flags": {},
        "element_type": "waltz_jump",
        "isu_code": None,
        "lang": "ru",
        "s3_endpoint_url": "http://localhost",
        "s3_access_key_id": "x",
        "s3_secret_access_key": "x",
        "s3_bucket": "test",
    }
    resp = client.post("/process", json=req)
    assert resp.status_code == 200, resp.text

    # S3 artifact content (captured inside the upload mock -- the temp dir is
    # torn down post-request, so capture must happen inside _s3_upload).
    s3_json = client._captured["metrics_json"]  # type: ignore[attr-defined]

    # RED: the artifact must NOT contain a raw `NaN` literal. It currently DOES
    # (json.dumps allow_nan=True default), so this assertion FAILS now -> RED.
    assert "NaN" not in s3_json, (
        "BUG (RED): gpu_server S3 metrics.json contains a raw `NaN` literal -- "
        "json.dumps(allow_nan=True) default -> invalid JSON per RFC 8259. JS "
        "JSON.parse throws 'Unexpected identifier NaN'; non-Python / strict-JSON "
        "S3 consumers break. Must serialize NaN as `null` (allow_nan=False + "
        f"NaN->None sanitizer). Actual content:\n{s3_json}"
    )

    # And a strict RFC 8259 parse MUST succeed (it currently raises -> RED).
    json.loads(s3_json, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_python_json_tolerates_nan_so_s3_corruption_is_silent():
    """Explains WHY the bug is silent today: Python json.loads accepts NaN by
    default, so the corrupted S3 artifact round-trips through any Python
    consumer without error. The corruption only detonates for strict / non-
    Python consumers (JS JSON.parse, strict RFC 8259 parsers).
    """
    import math

    parsed = json.loads('{"value": NaN}')
    assert set(parsed) == {"value"} and math.isnan(parsed["value"])
