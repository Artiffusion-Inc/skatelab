"""Client for calling Vast.ai Serverless GPU endpoint.

Flow:
  1. POST /route to get worker URL + auth from Vast.ai
  2. POST /{endpoint} to PyWorker with {auth_data, payload}
  3. PyWorker validates auth, proxies payload to FastAPI (port 8000)
  4. Return R2 keys (no local download)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

ROUTE_URL = "https://run.vast.ai/route/"
REQUEST_TIMEOUT = 600  # 10 min for video processing
ROUTE_TIMEOUT = 30


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


def _route_request(endpoint_name: str, api_key: str) -> dict:
    """Get route + auth data from Vast.ai. Each call returns fresh signature."""
    resp = httpx.post(
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


async def _async_route_request(endpoint_name: str, api_key: str) -> dict:
    """Async version of _route_request."""
    async with httpx.AsyncClient(timeout=ROUTE_TIMEOUT) as client:
        resp = await client.post(
            ROUTE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"endpoint": endpoint_name},
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


def process_video_remote(
    video_key: str,
    person_click: dict[str, int] | None = None,
    frame_skip: int = 1,
    tracking: str = "auto",
    ml_flags: dict[str, bool] | None = None,
    element_type: str | None = None,
) -> VastResult:
    """Send video processing to Vast.ai Serverless GPU.

    Video must already be in R2 at `video_key`.
    Returns R2 keys for poses.npy + metrics.json (no video render).

    Raises httpx.HTTPStatusError on routing/processing failures.
    """
    settings = get_settings()
    if ml_flags is None:
        ml_flags = {}

    api_key = settings.vastai.api_key.get_secret_value()
    endpoint_name = settings.vastai.endpoint_name

    # 1. Route to worker (fresh signature per request)
    logger.info("Routing to Vast.ai endpoint: %s", endpoint_name)
    route = _route_request(endpoint_name, api_key)
    logger.info("Worker URL: %s", route["url"])

    # 2. Send processing request wrapped in PyWorker format
    payload = {
        "video_r2_key": video_key,
        "person_click": person_click,
        "frame_skip": frame_skip,
        "tracking": tracking,
        "ml_flags": ml_flags,
        "element_type": element_type,
        "r2_endpoint_url": settings.r2.endpoint_url,
        "r2_access_key_id": settings.r2.access_key_id.get_secret_value(),
        "r2_secret_access_key": settings.r2.secret_access_key.get_secret_value(),
        "r2_bucket": settings.r2.bucket,
    }
    body = {
        "auth_data": _build_auth_data(route, endpoint_name),
        "payload": payload,
    }
    resp = httpx.post(
        f"{route['url']}/process",
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()

    # 3. Return R2 keys directly (no download)
    segments = result.get("segments")
    return VastResult(
        poses_key=result.get("poses_r2_key"),
        metrics_key=result.get("metrics_r2_key"),
        stats=result["stats"],
        metrics=result.get("metrics"),
        phases=result.get("phases"),
        recommendations=result.get("recommendations"),
        segments=segments,
    )


async def process_video_remote_async(
    video_key: str,
    person_click: dict[str, int] | None = None,
    frame_skip: int = 1,
    tracking: str = "auto",
    ml_flags: dict[str, bool] | None = None,
    element_type: str | None = None,
) -> VastResult:
    """Async version of process_video_remote using httpx.AsyncClient."""
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
        "video_r2_key": video_key,
        "person_click": person_click,
        "frame_skip": frame_skip,
        "tracking": tracking,
        "ml_flags": ml_flags,
        "element_type": element_type,
        "r2_endpoint_url": settings.r2.endpoint_url,
        "r2_access_key_id": settings.r2.access_key_id.get_secret_value(),
        "r2_secret_access_key": settings.r2.secret_access_key.get_secret_value(),
        "r2_bucket": settings.r2.bucket,
    }
    body = {
        "auth_data": _build_auth_data(route, endpoint_name),
        "payload": payload,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{route['url']}/process",
            json=body,
        )
        resp.raise_for_status()
        result = resp.json()

    # 3. Return R2 keys directly (no download)
    segments = result.get("segments")
    return VastResult(
        poses_key=result.get("poses_r2_key"),
        metrics_key=result.get("metrics_r2_key"),
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

    Video must already be in R2 at `video_key`.
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
        "video_r2_key": video_key,
        "tracking": tracking,
        "r2_endpoint_url": settings.r2.endpoint_url,
        "r2_access_key_id": settings.r2.access_key_id.get_secret_value(),
        "r2_secret_access_key": settings.r2.secret_access_key.get_secret_value(),
        "r2_bucket": settings.r2.bucket,
    }
    body = {
        "auth_data": _build_auth_data(route, endpoint_name),
        "payload": payload,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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
