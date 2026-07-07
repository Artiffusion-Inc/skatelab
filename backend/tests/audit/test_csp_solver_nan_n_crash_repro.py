"""#1214: int(n**0.5 * 1.5) crashes when n is NaN in _generate_positions.

If `n` is NaN, `int(NaN)` raises ValueError, which propagates out of the
entire CSP solver and aborts the choreography plan. A `math.isfinite(n)`
guard (or safe default `cols`) is required.
"""

from __future__ import annotations

import math

import pytest
from app.services.choreography.csp_solver import _generate_positions

# ---------------------------------------------------------------------------
# Observable crashes
# ---------------------------------------------------------------------------


def test_generate_positions_nan_n_does_not_raise():
    """#1214: NaN n must not raise ValueError from int(NaN)."""
    positions = _generate_positions(float("nan"))  # type: ignore[arg-type]
    # NaN n → no usable positions, but must not crash
    assert isinstance(positions, list)


def test_generate_positions_inf_n_does_not_raise():
    """#1214: +inf n must not raise (int(inf) raises)."""
    positions = _generate_positions(float("inf"))  # type: ignore[arg-type]
    assert isinstance(positions, list)


def test_generate_positions_negative_n_does_not_raise():
    """#1214: negative n must not raise (n**0.5 yields a complex-ish path)."""
    positions = _generate_positions(-1)  # type: ignore[arg-type]
    assert isinstance(positions, list)


# ---------------------------------------------------------------------------
# Regression — valid n still produces sane output
# ---------------------------------------------------------------------------


def test_generate_positions_valid_n_returns_sane_count():
    """#1214 regression: valid n still returns a list of n positions."""
    n = 5
    positions = _generate_positions(n)
    assert isinstance(positions, list)
    assert len(positions) == n
    for p in positions:
        assert "x" in p and "y" in p
        assert math.isfinite(p["x"]) and math.isfinite(p["y"])


# ---------------------------------------------------------------------------
# Source guard — root cause locked
# ---------------------------------------------------------------------------


def test_nan_n_guard_exists_in_source():
    """#1214: csp_solver _generate_positions guards NaN n before int()."""
    import inspect

    source = inspect.getsource(_generate_positions)
    assert "math.isfinite" in source, (
        "#1214: math.isfinite guard missing from _generate_positions()"
    )
