"""Tests for business notification producers."""

from __future__ import annotations

import pytest
from app.crud.notifications import count_by_user
from app.services.notification_events import (
    analysis_completed,
    analysis_failed,
    export_ready,
    training_plan_generated,
)


@pytest.mark.asyncio
async def test_notification_producers_create_typed_events(db_session, authed_user):
    completed = await analysis_completed(
        db_session,
        user_id=authed_user.id,
        session_id="session-1",
    )
    failed = await analysis_failed(
        db_session,
        user_id=authed_user.id,
        session_id="session-2",
    )
    training = await training_plan_generated(
        db_session,
        user_id=authed_user.id,
        plan_id="plan-1",
    )
    exported = await export_ready(
        db_session,
        user_id=authed_user.id,
        export_id="export-1",
    )

    assert (completed.event_type, completed.source_id) == ("analysis.completed", "session-1")
    assert completed.deep_link == "skatelab://session/session-1"
    assert completed.payload == {"session_id": "session-1"}
    assert completed.title and completed.body

    assert (failed.event_type, failed.source_id) == ("analysis.failed", "session-2")
    assert failed.deep_link == "skatelab://session/session-2"
    assert failed.payload == {"session_id": "session-2"}
    assert failed.title and failed.body

    assert (training.event_type, training.source_id) == ("training.assigned", "plan-1")
    assert training.deep_link == "skatelab://training/plan-1"
    assert training.payload == {"training_plan_id": "plan-1"}

    assert (exported.event_type, exported.source_id) == ("export.ready", "export-1")
    assert exported.deep_link == "skatelab://exports/export-1"
    assert exported.payload == {"export_id": "export-1"}


@pytest.mark.asyncio
async def test_notification_producer_is_idempotent_by_recipient_event_source(
    db_session, authed_user
):
    first = await analysis_completed(
        db_session,
        user_id=authed_user.id,
        session_id="session-retry",
    )
    second = await analysis_completed(
        db_session,
        user_id=authed_user.id,
        session_id="session-retry",
    )

    assert second.id == first.id
    assert await count_by_user(db_session, authed_user.id) == 1
