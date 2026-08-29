"""Regression test for #1162: project_3d_to_2d scalar path int(NaN) crash.

Bug (per issue #1162): `project_3d_to_2d` scalar path
(ml/src/visualization/core/geometry.py) crashed with uncaught
`ValueError: cannot convert float NaN to integer` when x/y/z was NaN
because `int(x * scale)` with NaN x raises ValueError. The depth clamp
`max(0.1, depth)` IS NaN-safe (Python builtin), so depth = 0.1 and
scale = focal_length / 0.1 = 10 * focal_length — NaN propagates through
`x * scale` to `int(...)`.

Fix: add `math.isfinite(x) and math.isfinite(y) and math.isfinite(z)`
guard at top of the scalar method, raising a clear ValueError naming
the bad input (mirrors PR #1065/#1070 pattern for sibling functions).
Sibling to #1077 (same root cause, already fixed via PR #1147).

Contract: NaN in any of x/y/z on the scalar path → ValueError naming
the bad input (NOT the generic Python int-cast message). Finite
input → finite pixel tuple (regression).
"""

from __future__ import annotations

import inspect

import numpy as np

from src.visualization.core.geometry import project_3d_to_2d


def test_scalar_path_has_isfinite_guard():
    """GREEN contract: scalar branch of project_3d_to_2d isfinite-guards
    x/y/z before the int cast. The unfixed code did
    `x_2d = width // 2 + int(x * scale)` with no NaN guard → int(NaN) →
    ValueError crash."""
    src = inspect.getsource(project_3d_to_2d)
    # The scalar branch (else: at the bottom of the function) isfinite-guards.
    # Anchor on the "Single position" comment that precedes the scalar branch.
    assert "# Single position" in src, (
        "project_3d_to_2d scalar branch must be marked '# Single position'"
    )
    scalar_branch = src.split("# Single position", 1)[1]
    assert "isfinite" in scalar_branch, (
        "project_3d_to_2d scalar branch must isfinite-guard x/y/z before "
        "the int cast. Without it, int(NaN * scale) crashes."
    )


def test_scalar_nan_raises_clear_valueerror():
    """GREEN contract: NaN in any of x/y/z → ValueError naming the bad
    input (not the generic Python int-cast ValueError)."""
    nan = float("nan")
    raised = False
    msg = ""
    try:
        project_3d_to_2d((nan, 0.5, 1.0), 1920, 1080)
    except ValueError as e:
        raised = True
        msg = str(e)
    assert raised, (
        "BUG: project_3d_to_2d with a NaN x did not raise ValueError. "
        "The scalar path did int(NaN * scale) → must crash; without an "
        "isfinite guard it crashes with the generic int-cast message "
        "instead of a clear naming-the-input message."
    )
    assert "finite" in msg.lower() or "nan" in msg.lower(), (
        f"ValueError message should name the bad input, got: {msg!r}"
    )


def test_scalar_nan_y_raises_valueerror():
    """GREEN contract: NaN y → ValueError (same path as NaN x)."""
    raised = False
    try:
        project_3d_to_2d((0.5, float("nan"), 1.0), 1920, 1080)
    except ValueError:
        raised = True
    assert raised, "NaN y must raise ValueError via the isfinite guard."


def test_scalar_nan_z_raises_valueerror():
    """GREEN contract: NaN z → ValueError (z participates in depth)."""
    raised = False
    try:
        project_3d_to_2d((0.5, 0.5, float("nan")), 1920, 1080)
    except ValueError:
        raised = True
    assert raised, "NaN z must raise ValueError via the isfinite guard."


def test_scalar_finite_returns_finite_pixel():
    """Regression: finite scalar tuple (0.5, 0.3, 1.0) → finite pixel
    tuple. The isfinite guard must not regress the finite path."""
    out = project_3d_to_2d((0.5, 0.3, 1.0), 1920, 1080)
    assert isinstance(out, tuple) and len(out) == 2
    x_px, y_px = out
    assert isinstance(x_px, (int, np.integer))
    assert isinstance(y_px, (int, np.integer))
    assert 0 <= x_px < 1920
    assert 0 <= y_px < 1080
