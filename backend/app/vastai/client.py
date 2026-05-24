"""Client for calling Vast.ai Serverless GPU endpoint.

Flow:
  1. POST /route to get worker URL + auth from Vast.ai
  2. POST /{endpoint} to PyWorker with {auth_data, payload}
  3. PyWorker validates auth, proxies payload to FastAPI (port 8000)
  4. Return S3 keys (no local download)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

ROUTE_URL = "https://run.vast.ai/route/"
ROUTE_TIMEOUT = 30
WORKER_TIMEOUT = 600

_async_client: httpx.AsyncClient | None = None


async def get_async_client() -> httpx.AsyncClient:
    """Get or create the shared httpx.AsyncClient with connection pooling."""
    global _async_client  # noqa: PLW0603
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(WORKER_TIMEOUT, connect=30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _async_client


@dataclass
class VastResult:
    poses_key: str | None
    metrics_key: str | None
    stats: dict
    metrics: list | None
    phases: object | None
    recommendations: list | None
    segments: list[dict] | None = None


@dataclass
class VastDetectResult:
    persons: list[dict]
    preview_image: str
    video_key: str
    auto_click: dict[str, int] | None
    width: int
    height: int
    status: str


def _build_auth_data(route: dict, endpoint_name: str) -> dict:
    """Build auth_data dict for PyWorker from route response."""
    return {
        "endpoint": endpoint_name,
        "request_idx": route["request_idx"],
        "reqnum": route["reqnum"],
        "url": route["url"],
        "cost": route["cost"],
        "signature": route["signature"],
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
)
async def _async_route_request(endpoint_name: str, api_key: str) -> dict:
    """Get route + auth data from Vast.ai. Each call returns fresh signature."""
    client = await get_async_client()
    resp = await client.post(
        ROUTE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"endpoint": endpoint_name},
        timeout=ROUTE_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error_msg" in data:
        raise RuntimeError(f"Vast.ai route error: {data['error_msg']}")
    return {
        "url": data["url"],
        "signature": data["signature"],
        "reqnum": data["reqnum"],
        "request_idx": data["request_idx"],
        "cost": data["cost"],
    }


async def process_video_remote_async(
    video_key: str,
    person_click: dict[str, int] | None = None,
    frame_skip: int = 1,
    tracking: str = "auto",
    ml_flags: dict[str, bool] | None = None,
    element_type: str | None = None,
) -> VastResult:
    """Async: send video processing to Vast.ai Serverless GPU.

    Video must already be in S3 at `video_key`.
    Returns S3 keys for poses.npy + metrics.json (no video render).

    Raises httpx.HTTPStatusError on routing/processing failures.
    """
    settings = get_settings()
    if ml_flags is None:
        ml_flags = {}

    api_key = settings.vastai.api_key.get_secret_value()
    endpoint_name = settings.vastai.endpoint_name

    # 1. Route to worker (fresh signature per request)
    logger.info("Routing to Vast.ai endpoint: %s", endpoint_name)
    route = await _async_route_request(endpoint_name, api_key)
    logger.info("Worker URL: %s", route["url"])

    # 2. Send processing request wrapped in PyWorker format
    payload = {
        "video_s3_key": video_key,
        "person_click": person_click,
        "frame_skip": frame_skip,
        "tracking": tracking,
        "ml_flags": ml_flags,
        "element_type": element_type,
        "s3_endpoint_url": settings.s3.endpoint_url,
        "s3_access_key_id": settings.s3.access_key_id.get_secret_value(),
        "s3_secret_access_key": settings.s3.secret_access_key.get_secret_value(),
        "s3_bucket": settings.s3.bucket,
    }
    body = {
        "auth_data": _build_auth_data(route, endpoint_name),
        "payload": payload,
    }
    client = await get_async_client()
    resp = await client.post(
        f"{route['url']}/process",
        json=body,
    )
    resp.raise_for_status()
    result = resp.json()

    # 3. Return S3 keys directly (no download)
    segments = result.get("segments")
    return VastResult(
        poses_key=result.get("poses_s3_key"),
        metrics_key=result.get("metrics_s3_key"),
        stats=result["stats"],
        metrics=result.get("metrics"),
        phases=result.get("phases"),
        recommendations=result.get("recommendations"),
        segments=segments,
    )


async def detect_video_remote_async(
    video_key: str,
    tracking: str = "auto",
) -> VastDetectResult:
    """Send person detection to Vast.ai Serverless GPU.

    Video must already be in S3 at `video_key`.
    Returns detected persons, preview image, and auto-click.

    Raises httpx.HTTPStatusError on routing/processing failures.
    """
    settings = get_settings()

    api_key = settings.vastai.api_key.get_secret_value()
    endpoint_name = settings.vastai.endpoint_name

    # 1. Route to worker (fresh signature per request)
    logger.info("Routing detection to Vast.ai endpoint: %s", endpoint_name)
    route = await _async_route_request(endpoint_name, api_key)
    logger.info("Worker URL: %s", route["url"])

    # 2. Send detection request wrapped in PyWorker format
    payload = {
        "video_s3_key": video_key,
        "tracking": tracking,
        "s3_endpoint_url": settings.s3.endpoint_url,
        "s3_access_key_id": settings.s3.access_key_id.get_secret_value(),
        "s3_secret_access_key": settings.s3.secret_access_key.get_secret_value(),
        "s3_bucket": settings.s3.bucket,
    }
    body = {
        "auth_data": _build_auth_data(route, endpoint_name),
        "payload": payload,
    }
    client = await get_async_client()
    resp = await client.post(
        f"{route['url']}/detect",
        json=body,
    )
    resp.raise_for_status()
    result = resp.json()

    return VastDetectResult(
        persons=list(result["persons"]),
        preview_image=result["preview_image"],
        video_key=result["video_key"],
        auto_click=result.get("auto_click"),
        width=result.get("width", 0),
        height=result.get("height", 0),
        status=result.get("status", ""),
    )
