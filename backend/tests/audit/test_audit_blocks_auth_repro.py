"""RED repro: log_auth_event propagates db.flush() failure — best-effort audit aborts auth.

Root cause
----------
``backend/app/services/audit.py:34-35`` — ``log_auth_event`` ends with::

    db.add(entry)
    await db.flush()

with NO try/except around it. The function is documented/intended as a
best-effort audit (``"Record an auth event."``) but any ``flush()`` failure
(transient DB connection drop, constraint violation, statement timeout,
asyncpg ``InterfaceError``) propagates as an unhandled exception and ABORTS
the auth operation it was supposed to merely observe.

None of the 9 call sites in ``backend/app/routes/auth.py`` wrap it either::

    181  login
    196  login_failed   <- worst case: audit BEFORE raise ClientException(401)
    210  login
    240  register
    258  register
    302  password_reset_request
    340  password_reset_complete
    354  logout
    386  email_verify

Most damaging on the ``login_failed`` path (auth.py:196): the audit write
happens BEFORE the ``raise ClientException(401)`` at line 199. If the audit
flush raises, the user gets a 500 instead of the real 401 — the actual auth
outcome is masked by the telemetry write that was supposed to observe it.
Same risk on every login/refresh/logout/register/password-reset/email-verify.

Contract: audit = observe-only, NEVER gate auth. A failure to write a telemetry
row must not change the auth response. Audit should fail open (log + swallow),
not fail closed (abort the caller).

Repro
-----
Pure pytest, mock db. ``CrashDB`` implements the AsyncSession interface
``log_auth_event`` uses (``db.add`` + ``await db.flush()``): ``add`` is a no-op,
``flush`` raises (simulates a DB connection lost mid-request). The RED
assertion: ``log_auth_event`` must NOT propagate the flush exception.
CURRENT code raises the ``RuntimeError`` -> ``raised=True`` -> assertion
``assert not raised`` FAILS. After a fix (try/except around ``db.add``+``flush``,
log at WARN + return) the exception is swallowed -> ``raised=False`` -> GREEN.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.services.audit import log_auth_event


class CrashDB:
    """AsyncSession stub: add is no-op, flush raises (DB connection lost)."""

    def add(self, *args: object, **kwargs: object) -> None:
        """No-op — mimics SQLAlchemy ``AsyncSession.add``."""

    async def flush(self) -> None:
        raise RuntimeError("db connection lost")


class OkDB:
    """AsyncSession stub: add + flush succeed (sanity / setup confirmation)."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, entry: object) -> None:
        self.added.append(entry)

    async def flush(self) -> None:
        return None


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host="1.2.3.4"),
        headers={"user-agent": "test-agent"},
    )


@pytest.mark.asyncio
async def test_log_auth_event_does_not_propagate_flush_failure() -> None:
    """RED: best-effort audit must NOT propagate a db.flush() exception.

    CURRENT (RED): ``await log_auth_event(...)`` raises ``RuntimeError`` ->
    ``raised=True`` -> ``assert not raised`` FAILS.
    CONTRACT: best-effort — the exception is swallowed, auth proceeds.
    """
    raised = False
    try:
        await log_auth_event(CrashDB(), "login_failed", user_id="u1", request=_request())
    except Exception:
        raised = True
    assert not raised, (
        "BUG: log_auth_event propagated a db.flush() exception — best-effort "
        "audit telemetry aborted the caller (auth route would get 500, real "
        "auth outcome masked). Audit must observe, not gate auth."
    )


@pytest.mark.asyncio
async def test_log_auth_event_sanity_ok_db_returns_none() -> None:
    """GREEN sanity: on a working db, no raise and returns None.

    Confirms the test setup is right and not masking the real RED — the crash
    test above is the one that fails against current code.
    """
    db = OkDB()
    result = await log_auth_event(db, "login", user_id="u1", request=_request())
    assert result is None
    assert len(db.added) == 1
