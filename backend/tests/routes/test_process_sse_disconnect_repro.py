"""#699 repro: stream_process_status SSE generator must detect client disconnect.

RED contract (before fix): `async for message in pubsub.listen()` blocked on
a Valkey read, holding the generator away from the event loop — a client
disconnect went undetected for up to 60s and pubsub connections accumulated
under mobile flakiness. GREEN contract (after fix): the generator polls
`pubsub.get_message(timeout=...)` in a loop, checking `request.is_connected`
each tick so ASGI/Litestar can observe `http.disconnect` and tear the stream
down promptly.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _mod():
    if "app.routes.process" not in sys.modules:
        importlib.import_module("app.routes.process")
    return sys.modules["app.routes.process"]


def _src() -> str:
    return Path(_mod().__file__).read_text()


def _body() -> str:
    src = _src()
    start = src.index("async def stream_process_status")
    # last method in the controller — cut at end-of-method indentation
    end = src.index("\n        return ServerSentEvent(", start)
    end = src.index(")", end) + 1
    return src[start:end]


def test_no_blocking_pubsub_listen() -> None:
    """The blocking `pubsub.listen()` loop was replaced by a poll loop."""
    body = _body()
    # `pubsub.listen()` blocks on a Valkey read; the fix replaces it with
    # `get_message(timeout=...)` so the loop returns control each tick.
    # Check only real code lines — the #699 comment mentions `pubsub.listen()`
    # by name when explaining the removal, which is not the blocking call.
    code_lines = [ln for ln in body.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "pubsub.listen()" not in code, (
        "pubsub.listen() still present — blocks event loop, no disconnect detection"
    )
    assert "get_message(" in code, "poll loop missing — get_message not used"


def test_disconnect_check_in_loop() -> None:
    """The generator checks request.is_connected inside the loop."""
    body = _body()
    assert "is_connected" in body, (
        "disconnect check missing — generator never observes client disconnect"
    )


def test_request_param_added_to_stream_handler() -> None:
    """stream_process_status accepts a Request so it can check connectivity."""
    body = _body()
    sig_end = body.index(") -> ServerSentEvent:")
    sig = body[:sig_end]
    assert "request" in sig, "request param missing from stream_process_status signature"
