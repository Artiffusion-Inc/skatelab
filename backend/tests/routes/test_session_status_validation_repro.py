"""Repro tests for missing session status-transition validation in PATCH /sessions/{id}.

`PATCH /sessions/{id}` (routes/sessions.py:206-226) accepts `PatchSessionRequest`
whose `status` field is a free `str | None` with `max_length=20` (schemas.py) —
NOT an enum/whitelist. The route applies it directly via
`update(db, session, **data.model_dump(exclude_unset=True))`, so a client can set
`status` to ANY string, including `"completed"` / `"done"` on a session that was
never analyzed (no metrics, no pose data, no worker run).

Why this is a bug — it corrupts downstream metrics / PRs / trends:

  - `/metrics/prs` filters `Session.status == "done"` (routes/metrics.py:183)
    AND `SessionMetric.is_pr`. The PR detection writes `SessionMetric.is_pr`
    during analysis (services/session_saver.py). A client setting
    `status="completed"` does not create metrics, but combined with the
    dual-status bug (see below) it lets a client flip a session into the
    "finished" state without ever running the ML pipeline.

  - `/metrics/trend` (routes/metrics.py:48) and `/metrics/diagnostics`
    (routes/metrics.py:240) also filter `Session.status == "done"`. A client
    that force-sets `status="done"` can inject a half-analyzed / errored
    session into trend/diagnostics aggregation, skewing regression/stagnation
    diagnostics with garbage data.

  - There is NO state-machine: nothing prevents `uploading → completed`
    (skipping the worker entirely), `failed → completed` (resurrecting a failed
    session as if it finished), or `completed → uploading` (resurrecting a
    finished session into an "editable" state). The `status` column is a
    free-text field on a user-mutable endpoint.

Background — the dual-status inconsistency that makes this worse: the worker
writes BOTH `"completed"` (crud/session.py:121 via update_session_analysis)
AND `"done"` (services/session_saver.py:93 via save_analysis_results) to the
SAME `Session.status` column on the SAME session in the SAME transaction
(worker.py:414 then worker.py:424). `save_analysis_results` runs second and
wins, so a fully-analyzed session ends up `"done"`; but a session whose worker
ran only `update_session_analysis` (no metrics) ends up `"completed"`. The
metrics endpoints filter `"done"` only — so the `"completed"`-without-metrics
sessions are invisible to PRs/trend/diagnostics, but a client can PATCH a
session to `"done"` and make it visible with whatever (missing) data it has.

The existing `test_patch_session` (routes/test_sessions.py) only patches
`element_type` — it never sends `status`, so the status-free-for-all never
surfaces in CI.

Repro: create a session (status=`uploading`, no metrics, no analysis), then
PATCH `status="completed"`. RED now: 200 and the session is now `completed`.
After the fix (validate allowed status transitions server-side, or make
`status` read-only on the client-mutable PATCH endpoint) → 400.

No production data mutated: in-memory SQLite test DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> User:
    user = User(
        email="owner-status@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user):
    from app.auth.security import create_access_token

    token = create_access_token(user_id=owner_user.id)
    return {"Authorization": f"Bearer {token}"}


async def _create_owner_session(db_session: AsyncSession, owner_user: User):
    from app.crud.session import create as crud_create

    return await crud_create(db_session, user_id=owner_user.id, element_type="lutz")


@pytest.mark.asyncio
async def test_patch_session_status_completed_without_analysis_must_be_rejected_repro(
    client, owner_headers, owner_user, db_session: AsyncSession
):
    """PATCH status="completed" on a never-analyzed session must NOT be allowed.

    RED now: the PATCH is accepted (200) and the session is flipped to
    "completed" with no metrics / no pose data / no worker run — a client can
    bypass the ML pipeline and inject a "finished" session. After the fix
    (status-transition validation / status not client-mutable) → 400.
    """
    session = await _create_owner_session(db_session, owner_user)

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.patch(
            f"/v1/sessions/{session.id}",
            json={"status": "completed"},
            headers=owner_headers,
        )

    assert response.status_code == 400, (
        'BUG: PATCH /sessions/{id} accepted status="completed" on a session '
        f"that never ran analysis (got {response.status_code}, expected 400). "
        f"A client can bypass the ML pipeline and mark a session finished with "
        f"no metrics — corrupting PRs/trend/diagnostics filters. Body: {response.text}"
    )

    # The session must NOT have been mutated to "completed".
    from app.crud.session import get_by_id

    fresh = await get_by_id(db_session, session.id)
    assert fresh is not None and fresh.status != "completed", (
        f"BUG: session status was flipped to {fresh.status if fresh else None} "
        "via PATCH with no analysis — the ML pipeline was bypassed."
    )


@pytest.mark.asyncio
async def test_patch_session_status_arbitrary_string_must_be_rejected_repro(
    client, owner_headers, owner_user, db_session: AsyncSession
):
    """PATCH status=<arbitrary string> must be validated, not stored verbatim.

    `PatchSessionRequest.status` is `str | None` with no enum/whitelist, so any
    string up to 20 chars is accepted. RED now: PATCH status="bogus_xyz"
    returns 200 and stores "bogus_xyz" as the session status. After the fix
    (whitelist of allowed statuses) → 400.
    """
    session = await _create_owner_session(db_session, owner_user)

    with patch(
        "app.routes.sessions.get_object_url_async",
        new_callable=AsyncMock,
        return_value="https://fake.url",
    ):
        response = await client.patch(
            f"/v1/sessions/{session.id}",
            json={"status": "bogus_xyz"},
            headers=owner_headers,
        )

    assert response.status_code == 400, (
        "BUG: PATCH /sessions/{id} accepted an arbitrary status string "
        f"(got {response.status_code}, expected 400). status is free-text with no "
        f"whitelist. Body: {response.text}"
    )
