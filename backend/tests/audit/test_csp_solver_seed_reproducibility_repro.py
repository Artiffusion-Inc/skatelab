"""Repro tests — csp_solver.solve_layout(seed=...) positions non-deterministic (#845).

``solve_layout(seed=42)`` elements/TES are deterministic but rink ``positions``
differ across identical-seed calls. Root cause: ``_generate_positions``
(csp_solver.py:251) calls bare ``random.seed()`` (no arg) which reseeds the
GLOBAL RNG from OS entropy, destroying the seeded state set in ``solve_layout``
(line 282: ``random.seed(seed)``).

Fix (#845): remove the bare ``random.seed()`` line. ``solve_layout`` already
seeds when ``seed is not None``; when ``seed is None`` Python OS-seeds on first
use. The explicit reseed is both redundant and harmful (perturbs global RNG).

Tests:
  - observable: same seed → identical positions (RED: differ).
  - observable: after _generate_positions, RNG stream still on seeded track
    (RED: diverged by the bare reseed).
  - source-asserting: _generate_positions source has no bare random.seed().
"""

from __future__ import annotations

import random

import pytest
from app.services.choreography.csp_solver import _generate_positions, solve_layout

_INVENTORY = {
    "jumps": ["3Lz", "3F", "3Lo", "3S", "2A", "2T", "1Eu"],
    "spins": ["CSp4", "LSp4", "FSp4"],
    "combinations": ["3Lz+2T", "3F+2T"],
}
_MUSIC = {"duration": 240.0, "peaks": [], "structure": []}


def _positions(layout: dict) -> list[dict]:
    return [e.get("position") for e in layout["elements"]]


def test_solve_layout_seed_reproduces_positions_repro():
    """#845: two solve_layout(..., seed=42) calls must produce IDENTICAL
    rink positions (not just identical elements/TES).

    RED without the fix: _generate_positions calls bare random.seed(),
    reseeding the global RNG → positions drift across calls.
    """
    r1 = solve_layout(_INVENTORY, _MUSIC, "mens_singles", "free_skate", num_layouts=2, seed=42)
    r2 = solve_layout(_INVENTORY, _MUSIC, "mens_singles", "free_skate", num_layouts=2, seed=42)
    assert len(r1) == len(r2)
    for a, b in zip(r1, r2, strict=False):
        # elements + TES deterministic is a precondition, not the bug:
        assert [e["code"] for e in a["elements"]] == [e["code"] for e in b["elements"]]
        # THE BUG: positions must match for same seed.
        assert _positions(a) == _positions(b), (
            f"#845: identical-seed positions differ — "
            f"{_positions(a)} vs {_positions(b)}. "
            f"_generate_positions reseeds the global RNG."
        )


def test_generate_positions_unseeded_call_destroys_seeded_rng_repro():
    """#845: after random.seed(42) + _generate_positions(n), the global RNG
    must still be on the seeded(42) stream — the bare random.seed() inside
    _generate_positions must not have replaced it.

    RED without the fix: _generate_positions calls random.seed() → global RNG
    reseeded from OS entropy → subsequent random.random() not the seed(42)
    value.
    """
    random.seed(42)
    _ = _generate_positions(6)
    after = random.random()
    # Reference: seed(42) then consume the SAME count of draws as
    # _generate_positions(6) made, then take one more. Reconstruct that count:
    # 6 cells × 2 uniform draws + 1 shuffle (n swaps) ≈ nondeterministic, so
    # instead assert the stream is still reproducible: reseed(42) without
    # _generate_positions must yield the same `after` on a fresh seed+draw.
    random.seed(42)
    # Consume draws matching _generate_positions(6): cols=max(1,int(6**0.5*1.5))=3,
    # rows=(6+3-1)//3=2 → 6 iterations × 2 uniform + 1 shuffle.
    cols = max(1, int(6**0.5 * 1.5))
    rows = max(1, (6 + cols - 1) // cols)
    cell_w = 52.0 / cols
    cell_h = 24.0 / rows
    for i in range(6):
        row = i // cols
        col = i % cols
        random.uniform(cell_w * 0.2, cell_w * 0.8)
        random.uniform(cell_h * 0.2, cell_h * 0.8)
    # shuffle consumes draws too; approximate by consuming n more for parity
    # is not exact. The contract under test: after _generate_positions, the RNG
    # was NOT replaced by OS entropy. Assert by re-seeding identically and
    # comparing the next draw — if _generate_positions did NOT reseed,
    # repeating the same setup reproduces `after`.
    # Simpler robust check: seed(42), call _generate_positions, then the next
    # random() must equal seed(42) + same calls + random(). Compare two runs:
    random.seed(42)
    _generate_positions(6)
    run1_next = random.random()
    random.seed(42)
    _generate_positions(6)
    run2_next = random.random()
    assert run1_next == run2_next, (
        f"#845: RNG stream not reproducible after _generate_positions "
        f"(run1={run1_next}, run2={run2_next}) — bare random.seed() inside "
        f"_generate_positions reseeds from OS entropy each call."
    )
    # Suppress unused-var warning for `after` (kept for documentation).
    del after


def test_generate_positions_source_has_no_bare_random_seed_repro():
    """#845 GREEN (root cause lock): _generate_positions source must NOT call
    bare ``random.seed()`` (no-arg form reseeds global RNG from OS entropy).
    """
    import inspect

    src = inspect.getsource(_generate_positions)
    assert "random.seed()" not in src, (
        "#845: _generate_positions calls bare random.seed() — this reseeds "
        "the global RNG from OS entropy, destroying the seeded state set in "
        "solve_layout. Remove the line."
    )
