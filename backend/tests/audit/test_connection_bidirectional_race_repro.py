"""RED repro — connections: get_active only checks from→to, not to→from.

Bug: get_active(db, from_user_id=A, to_user_id=B, type=COACHING) only
finds connections where A→B. If a connection already exists B→A (the other
direction), the invite path does NOT check for it, creating a DUPLICATE
coaching relationship with reversed direction.

The route handler (routes/connections.py:71-78) calls get_active with
from=inviter, to=invitee — but a B→A ACTIVE connection should also block
re-inviting in the opposite direction.

Expected: inviting B when B→A already exists should return 409 Conflict.
Pre-fix: it creates a second A→B connection — duplicate coaching.
"""

from pathlib import Path

import pytest


def test_invite_route_checks_reverse_direction():
    """#549 fix: invite route must check both directions via get_active.

    Post-fix: routes/connections.py:invite calls get_active twice — once
    for (from=inviter, to=invitee) and once for (from=invitee, to=inviter).
    Both must return None to allow the invite. If either direction has an
    active connection, 409 Conflict.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "connections_mod", "backend/app/routes/connections.py"
    )
    connections_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(connections_module)

    source = Path(connections_module.__file__).read_text()

    # The invite handler is in routes/connections.py — find it.
    # It must call get_active_conn twice (forward and reverse direction).
    invite_section_start = source.find("async def invite(")
    # Find the next @post decorator (start of next handler).
    next_decorator = source.find("@post(", invite_section_start)
    if next_decorator == -1:
        next_decorator = len(source)
    # Walk back to the @decorator line just before invite.
    decorator_idx = source.rfind("@", 0, invite_section_start)
    invite_body = source[decorator_idx:next_decorator]

    # Count get_active_conn calls inside the invite handler.
    forward_count = invite_body.count("get_active_conn(")
    assert forward_count >= 2, (
        f"Expected at least 2 get_active_conn() calls in invite handler "
        f"(forward + reverse direction), got {forward_count}. "
        f"Pre-fix: only forward direction was checked, allowing "
        f"bidirectional duplicate coaching connections."
    )

    # The reverse check must use from_user_id=to_user.id and
    # to_user_id=verified_user.id (swapped args).
    assert (
        "from_user_id=to_user.id" in invite_body and "to_user_id=verified_user.id" in invite_body
    ), (
        "Expected reverse-direction check with swapped from/to_user_id "
        "arguments in invite handler. Pre-fix: only forward direction was "
        "checked."
    )


def test_get_active_directional_is_documented():
    """Document that get_active is still directional (only checks from→to).

    #549: the CRUD's get_active remains directional by design (it's
    a simple lookup). The bidirectional check is at the route level
    (invite handler), not the CRUD level. This test documents the
    current CRUD contract — get_active is a single-direction lookup;
    callers that need bidirectional must check both directions
    explicitly.
    """
    # #549: get_active is still directional. The fix is at the route
    # level — invite checks both directions via two get_active calls.
    import inspect

    from app.crud.connection import get_active

    source = inspect.getsource(get_active)
    # get_active still has the directional WHERE clause (from→to only).
    # This is intentional — the CRUD provides a simple lookup, and the
    # bidirectional contract is the caller's responsibility.
    assert "Connection.from_user_id ==" in source, (
        "get_active should still be a directional lookup "
        "(from→to only) — the bidirectional check is at the route level"
    )
