"""#665: empty inventory returns [] silently — must raise ValueError.
#666: _layout_fingerprint uses frozenset (order-independent) — must use tuple.

frozenset loses element order. Zayak-violating [3A, 3T] and compliant
[3T, 3A] got the same fingerprint, dedup silently dropped the better layout.
"""

from __future__ import annotations

import inspect

import pytest
from app.services.choreography.csp_solver import (
    _generate_candidates,
    _layout_fingerprint,
    solve_layout,
)

# ---------------------------------------------------------------------------
# Source guards
# ---------------------------------------------------------------------------


def test_empty_inventory_guard_in_source():
    """#665: _generate_candidates raises ValueError on empty inventory."""
    source = inspect.getsource(_generate_candidates)
    assert "inventory is empty" in source, "#665: empty inventory guard missing"


def test_fingerprint_returns_tuple():
    """#666: _layout_fingerprint returns tuple, not frozenset."""
    fp = _layout_fingerprint([{"code": "3A"}, {"code": "3T"}])
    assert isinstance(fp, tuple), f"#666: expected tuple, got {type(fp).__name__}"


# ---------------------------------------------------------------------------
# #665: empty inventory ValueError
# ---------------------------------------------------------------------------


def test_empty_inventory_raises():
    """#665: empty inventory raises ValueError."""
    with pytest.raises(ValueError, match="inventory is empty"):
        _generate_candidates({"jumps": [], "spins": [], "combinations": []}, "free_skate")


def test_empty_inventory_dict_raises():
    """#665: totally empty dict raises ValueError."""
    with pytest.raises(ValueError, match="inventory is empty"):
        _generate_candidates({}, "short_program")


# ---------------------------------------------------------------------------
# #666: fingerprint order-dependence
# ---------------------------------------------------------------------------


def test_fingerprint_preserves_order():
    """#666: [3A, 3T] and [3T, 3A] produce different fingerprints."""
    fp_a = _layout_fingerprint([{"code": "3A"}, {"code": "3T"}])
    fp_b = _layout_fingerprint([{"code": "3T"}, {"code": "3A"}])
    assert fp_a != fp_b, "#666: order-independent fingerprint causes dedup collision"


def test_fingerprint_same_order_same_result():
    """#666: same order gives same fingerprint."""
    fp_a = _layout_fingerprint([{"code": "3A"}, {"code": "3T"}])
    fp_b = _layout_fingerprint([{"code": "3A"}, {"code": "3T"}])
    assert fp_a == fp_b


def test_fingerprint_zayak_distinction():
    """#666: Zayak-violating vs compliant layouts have different fingerprints."""
    # [3A, 3A, 3T] — Zayak violation (same base jump twice not in combo)
    # [3A, 3T, 3A] — Zayak compliant (2nd 3A is in a different position)
    violating = _layout_fingerprint([{"code": "3A"}, {"code": "3A"}, {"code": "3T"}])
    compliant = _layout_fingerprint([{"code": "3A"}, {"code": "3T"}, {"code": "3A"}])
    assert violating != compliant, "#666: Zayak-violating and compliant layouts must differ"
