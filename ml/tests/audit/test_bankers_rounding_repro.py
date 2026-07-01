"""RED repro — Python round() misclassifies rotation LEVEL (#514).

phase_detector.py:35 `count_rotations`:
    return round(total_radians / (2.0 * np.pi))

Python's built-in round() uses banker's rounding (round-half-to-even) AND
rounds to nearest. For rotation LEVEL (the number of FULL completed turns),
neither is correct: a half-turn overshoot is an over-rotation of the LOWER
level, not a completed next level. 3.5 full turns = an over-rotated TRIPLE
(3), not a quad (4). round(3.5) == 4 (banker's rounds-to-even, but even if it
were round-half-up round(3.5)==4 it would still be wrong) → rotations == 4 →
compose_isu_element_type → "4Lz" (quad, BV ~11.0) instead of "3Lz" (triple,
BV ~5.9). A half-turn overshoot inflates a triple to a quad.

The correct rule is FLOOR: the level is the count of full completed turns;
the incomplete half is an over-rotation, not a new turn.

(Companion #517 — metrics.py:1290 round(x, 1) banker's at 1 decimal — was
considered but the real function's float sum never lands on the exact banker's
edge value 2.55 (it drifts to 2.5500000710 → round→2.6), so #517 is not
production-reachable as a deterministic bug and is left out of this repro/fix.)

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

import numpy as np

from src.analysis.phase_detector import count_rotations


def test_count_rotations_half_turn_is_over_rotation_not_next_level():
    """3.5 full turns is an over-rotated TRIPLE (3), not a completed quad (4).
    Rotation level = count of FULL completed turns → floor, not round.
    """
    # 3.5 full turns: triple + half overshoot.
    angles = np.linspace(0.0, 3.5 * 2.0 * np.pi, 60)
    rotations = count_rotations(angles)
    assert rotations == 3, (
        f"BUG #514: count_rotations(3.5 turns) = {rotations}, expected 3 "
        f"(an over-rotated TRIPLE, not a completed quad). "
        f"phase_detector.py:35 round(total_radians/(2π)) rounds-to-nearest "
        f"(with banker's round-half-to-even): round(3.5) == 4 inflates a "
        f"triple to a quad (4Lz, BV ~11.0, vs 3Lz, BV ~5.9). Rotation LEVEL "
        f"is the count of FULL completed turns — a half overshoot is not a "
        f"completed turn, so the level must floor, not round-to-nearest."
    )
