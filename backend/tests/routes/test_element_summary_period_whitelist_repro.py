"""#784 repro: element-summary `period` param must be whitelisted via Literal.

RED contract (before fix): `period: str = Parameter(default="30d", ...)` —
description promised `7d/30d/90d/all` but nothing enforced it, so `999d` /
`garbage` / empty were accepted. GREEN contract (after fix): the param is
typed `Period = Literal["7d", "30d", "90d", "all"]`, so Litestar rejects
unknown values with a 400 before the handler runs.
"""

from __future__ import annotations

import inspect
import typing
from pathlib import Path

import app.routes.metrics_summary as mod


def _src() -> str:
    return Path(mod.__file__).read_text()


def test_period_param_typed_as_literal_whitelist() -> None:
    """The module-level `Period` alias is a Literal with exactly the 4 values.

    Litestar wraps the handler so `inspect.signature` no longer sees the `period`
    param directly — assert on the exported `Period` alias instead, which is what
    the route signature annotates the param with.
    """
    assert hasattr(mod, "Period"), "Period alias missing from module"
    args = set(typing.get_args(mod.Period))
    assert args == {"7d", "30d", "90d", "all"}, (
        f"Period must be Literal[7d,30d,90d,all], got args={args!r}"
    )


def test_period_module_alias_whitelist() -> None:
    """Source declares the `Period` Literal alias with the 4 allowed values."""
    src = _src()
    assert "Period = Literal[" in src, "Period Literal alias missing"
    for value in ('"7d"', '"30d"', '"90d"', '"all"'):
        assert value in src, f"{value} missing from Period whitelist"


def test_period_param_uses_period_alias_not_str() -> None:
    """The route signature uses `period: Period`, not bare `period: str`."""
    src = _src()
    # The buggy line was `period: str = Parameter(...)` — assert it's gone.
    assert "period: str" not in src, "period still typed bare str (no whitelist)"
    assert "period: Period" in src, "period not annotated as Period alias"
