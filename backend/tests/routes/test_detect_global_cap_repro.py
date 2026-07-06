"""#766 repro: enqueue_detect must have a global cap, not only per-user limit.

RED contract (before fix): only `check_rate_limit(f"detect:enqueue:{user.id}",
...)` — a botnet of N accounts runs N*10/min GPU jobs. GREEN contract (after
fix): a second `check_rate_limit("detect:enqueue:global", ...)` caps the whole
fleet so extra accounts buy nothing once the cap is hit.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _mod():
    # `app.routes.__init__` rebinds `detect = Router(...)`, shadowing the
    # submodule attribute, so `import app.routes.detect as mod` returns the
    # Router. The real module is in sys.modules — grab it directly.
    if "app.routes.detect" not in sys.modules:
        importlib.import_module("app.routes.detect")
    return sys.modules["app.routes.detect"]


def _src() -> str:
    return Path(_mod().__file__).read_text()


def _body() -> str:
    src = _src()
    start = src.index("async def enqueue_detect")
    return src[start:]


def test_global_cap_constant_present() -> None:
    """Module exposes a tunable global cap constant."""
    mod = _mod()
    assert hasattr(mod, "GLOBAL_DETECT_CAP"), "GLOBAL_DETECT_CAP constant missing"
    assert isinstance(mod.GLOBAL_DETECT_CAP, int) and mod.GLOBAL_DETECT_CAP > 0


def test_global_rate_limit_call_present() -> None:
    """enqueue_detect calls a shared global rate-limit identifier after per-user."""
    body = _body()
    assert "detect:enqueue:global" in body, (
        "global cap call missing — only per-user limit present (botnet N*10/min)"
    )


def test_per_user_check_before_global_check() -> None:
    """Per-user limit is checked before the global cap (cheaper check first)."""
    body = _body()
    per_user_idx = body.index("detect:enqueue:{user.id}")
    global_idx = body.index("detect:enqueue:global")
    assert per_user_idx < global_idx, (
        "per-user check should run before global cap (legit traffic hits cheap limit first)"
    )
