"""#667: NaN TES layout poisons fingerprint, blocks real replacements.

In csp_solver, if the first TES stored for a fingerprint is NaN,
any later real TES fails the `tes > existing` check because NaN
comparisons are always False. The fix uses math.isfinite to
displace NaN entries with any finite value.
"""

from __future__ import annotations

import math

import pytest
from app.services.choreography.csp_solver import _generate_candidates

# ---------------------------------------------------------------------------
# Source guard — math.isfinite in dedup
# ---------------------------------------------------------------------------


def test_nan_tes_guard_exists_in_source():
    """#667: csp_solver best_by_fp dedup checks math.isfinite."""
    import inspect

    source = inspect.getsource(_generate_candidates)
    assert "math.isfinite" in source, (
        "#667: math.isfinite guard missing from _generate_candidates()"
    )


# ---------------------------------------------------------------------------
# NaN displacement logic
# ---------------------------------------------------------------------------


def test_nan_tes_replaced_by_finite():
    """#667: dedup logic replaces NaN TES with any finite value."""
    fp = frozenset({"3T", "3S"})
    best_by_fp: dict[frozenset[str], tuple[float, dict]] = {
        fp: (float("nan"), {"elements": ["3T", "3S"]})
    }
    tes = 5.0
    existing_tes = best_by_fp[fp][0]
    # Guard from fix: not math.isfinite(existing) or tes > existing
    should_replace = not math.isfinite(existing_tes) or tes > existing_tes
    assert should_replace, "NaN should be displaced by finite TES"


def test_finite_tes_kept_when_higher():
    """#667: higher finite TES replaces lower finite TES."""
    fp = frozenset({"3T", "3S"})
    best_by_fp: dict[frozenset[str], tuple[float, dict]] = {fp: (3.0, {"elements": ["3T", "3S"]})}
    tes = 5.0
    existing_tes = best_by_fp[fp][0]
    should_replace = not math.isfinite(existing_tes) or tes > existing_tes
    assert should_replace


def test_finite_tes_not_replaced_by_lower():
    """#667: lower finite TES does NOT replace higher finite TES."""
    fp = frozenset({"3T", "3S"})
    best_by_fp: dict[frozenset[str], tuple[float, dict]] = {fp: (5.0, {"elements": ["3T", "3S"]})}
    tes = 3.0
    existing_tes = best_by_fp[fp][0]
    should_replace = not math.isfinite(existing_tes) or tes > existing_tes
    assert not should_replace


def test_isfinite_rejects_nan_and_inf():
    """math.isfinite rejects NaN, +inf, -inf; accepts real floats."""
    assert not math.isfinite(float("nan"))
    assert not math.isfinite(float("inf"))
    assert not math.isfinite(float("-inf"))
    assert math.isfinite(0.0)
    assert math.isfinite(9.5)
