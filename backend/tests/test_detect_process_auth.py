"""Tests for auth enforcement on detect and process routes."""

import pytest


async def test_detect_enqueue_requires_auth(client):
    """Unauthenticated POST /detect returns 401."""
    response = await client.post(
        "/api/v1/detect",
        files={"video": ("test.mp4", b"fake", "video/mp4")},
    )
    assert response.status_code == 401


async def test_detect_status_requires_auth(client):
    """Unauthenticated GET /detect/{task_id}/status returns 401."""
    response = await client.get("/api/v1/detect/fake_task/status")
    assert response.status_code == 401


async def test_detect_result_requires_auth(client):
    """Unauthenticated GET /detect/{task_id}/result returns 401."""
    response = await client.get("/api/v1/detect/fake_task/result")
    assert response.status_code == 401


async def test_process_enqueue_requires_auth(client):
    """Unauthenticated POST /process/queue returns 401."""
    response = await client.post(
        "/api/v1/process/queue",
        json={
            "session_id": "fake",
            "video_key": "fake",
            "person_click": {"x": 0.5, "y": 0.5},
        },
    )
    assert response.status_code == 401


async def test_process_status_requires_auth(client):
    """Unauthenticated GET /process/{task_id}/status returns 401."""
    response = await client.get("/api/v1/process/fake_task/status")
    assert response.status_code == 401


async def test_process_cancel_requires_auth(client):
    """Unauthenticated POST /process/{task_id}/cancel returns 401."""
    response = await client.post("/api/v1/process/fake_task/cancel")
    assert response.status_code == 401


async def test_process_stream_requires_auth(client):
    """Unauthenticated GET /process/{task_id}/stream returns 401."""
    response = await client.get("/api/v1/process/fake_task/stream")
    assert response.status_code == 401
