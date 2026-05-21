"""Tests for Valkey-backed task state management."""

import pytest
from app.task_manager import (
    TaskStatus,
    _set_test_pool,
    create_task_state,
    get_task_state,
    is_cancelled,
    mark_cancelled,
    publish_task_event,
    set_cancel_signal,
    store_error,
    store_result,
    update_progress,
)


@pytest.fixture
async def valkey():
    import redis.asyncio as aioredis

    client = aioredis.Redis(host="localhost", port=6379, db=1, decode_responses=True)
    _set_test_pool(client)
    yield client
    _set_test_pool(None)
    keys = await client.keys("task:*")
    if keys:
        await client.delete(*keys)
    keys = await client.keys("task_cancel:*")
    if keys:
        await client.delete(*keys)
    await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_get_state(valkey):
    await create_task_state("test_task_1", "/tmp/video.mp4")
    state = await get_task_state("test_task_1")

    assert state is not None
    assert state["task_id"] == "test_task_1"
    assert state["status"] == TaskStatus.PENDING
    assert state["progress"] == 0.0
    assert state["video_key"] == "/tmp/video.mp4"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_progress(valkey):
    await create_task_state("test_task_2", "/tmp/video.mp4")
    await update_progress("test_task_2", 0.5, "Rendering...")
    state = await get_task_state("test_task_2")

    assert state["progress"] == 0.5
    assert state["message"] == "Rendering..."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_store_result(valkey):
    await create_task_state("test_task_3", "/tmp/video.mp4")
    await store_result("test_task_3", {"video_path": "out.mp4", "stats": {}})
    state = await get_task_state("test_task_3")

    assert state["status"] == TaskStatus.COMPLETED
    assert state["result"] == {"video_path": "out.mp4", "stats": {}}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_store_error(valkey):
    await create_task_state("test_task_4", "/tmp/video.mp4")
    await store_error("test_task_4", "OOM")
    state = await get_task_state("test_task_4")

    assert state["status"] == TaskStatus.FAILED
    assert state["error"] == "OOM"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_flow(valkey):
    await create_task_state("test_task_5", "/tmp/video.mp4")
    assert not await is_cancelled("test_task_5")

    await set_cancel_signal("test_task_5")
    assert await is_cancelled("test_task_5")

    await mark_cancelled("test_task_5")
    state = await get_task_state("test_task_5")
    assert state["status"] == TaskStatus.CANCELLED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(valkey):
    state = await get_task_state("nonexistent")
    assert state is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_task_event(valkey):
    """publish_task_event should publish to pub/sub channel."""
    import asyncio
    import json

    pubsub = valkey.pubsub()
    channel = "task_events:test_pub_1"
    await pubsub.subscribe(channel)

    await asyncio.sleep(0.05)

    await publish_task_event("test_pub_1", {"status": "running", "progress": 0.5})

    msg = await asyncio.wait_for(pubsub.get_message(timeout=1.0), timeout=1.0)
    while msg and msg["type"] != "message":
        msg = await asyncio.wait_for(pubsub.get_message(timeout=1.0), timeout=1.0)

    if msg:
        data = json.loads(msg["data"])
        assert data["status"] == "running"
        assert data["progress"] == 0.5
    else:
        pytest.fail("No message received from pub/sub")

    await pubsub.unsubscribe(channel)
    await pubsub.aclose()


def test_worker_queue_names():
    """Each WorkerSettings class should use its own queue name."""
    from app.worker import FastWorkerSettings, HeavyWorkerSettings

    assert FastWorkerSettings.queue_name == "skatelab:queue:fast"
    assert HeavyWorkerSettings.queue_name == "skatelab:queue:heavy"


def test_worker_graceful_shutdown():
    """Each WorkerSettings class should have job_completion_wait set."""
    from app.worker import FastWorkerSettings, HeavyWorkerSettings

    # Fast worker (detect) jobs are quick, 120s is generous
    assert FastWorkerSettings.job_completion_wait == 120
    # Heavy worker (process) jobs can run 5-10 min, wait up to 10 min
    assert HeavyWorkerSettings.job_completion_wait == 600
