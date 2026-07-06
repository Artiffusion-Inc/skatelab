"""#783 repro: element-summary `element` param must be whitelisted via Literal.

RED contract (before fix): `element: str = Parameter(description="Element type key")`
accepted `garbage`/`<script>`/empty and echoed them back. GREEN contract (after
fix): the param is typed `ElementFamily = Literal["jumps","spins","step",
"choreo","all"]`, so Litestar rejects unknown values with a 400 before the
handler runs.
"""

from __future__ import annotations

import typing
from pathlib import Path

import app.routes.metrics_summary as mod


def _src() -> str:
    return Path(mod.__file__).read_text()


def test_element_family_alias_is_literal_whitelist() -> None:
    """The module-level `ElementFamily` alias is a Literal with the 5 families."""
    assert hasattr(mod, "ElementFamily"), "ElementFamily alias missing from module"
    args = set(typing.get_args(mod.ElementFamily))
    assert args == {"jumps", "spins", "step", "choreo", "all"}, (
        f"ElementFamily must be Literal[jumps,spins,step,choreo,all], got {args!r}"
    )


def test_element_param_uses_element_family_alias_not_str() -> None:
    """The route signature uses `element: ElementFamily`, not bare `element: str`."""
    src = _src()
    assert "element: str" not in src, "element still typed bare str (no whitelist)"
    assert "element: ElementFamily" in src, "element not annotated as ElementFamily"


def test_element_family_whitelist_values_in_source() -> None:
    """Source declares the ElementFamily Literal alias with the family values."""
    src = _src()
    assert "ElementFamily = Literal[" in src, "ElementFamily Literal alias missing"
    for value in ('"jumps"', '"spins"', '"step"', '"choreo"', '"all"'):
        assert value in src, f"{value} missing from ElementFamily whitelist"
