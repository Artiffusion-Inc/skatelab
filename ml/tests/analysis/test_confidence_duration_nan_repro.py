"""RED repro — confidence.py NaN duration silently treated as best-case (#1221).

Bug: `ml/src/analysis/confidence.py:41,43` use `if duration_sec < 0.05:` /
`elif duration_sec < 0.1:` boolean guards. If `duration_sec` is NaN, then
`NaN < 0.05 = False` and `NaN < 0.1 = False` (Python IEEE 754), so the
factor is silently set to 1.0 (best case). No crash, no warning, no log.

Root cause: NaN is semantically different from a numeric value:
- duration = 0.001: "very short, suspicious" (factor 0.3)
- duration = NaN: "I don't know, corrupt data" (factor must NOT be 1.0)

Consumer chain: inflated confidence -> overconfident diagnosis -> coach
trusts bad data -> bad recommendations -> wrong Russian text -> overconfident
dashboard scoring.

Repro entry points:
- NaN `start_frame` or `end_frame` -> `duration_frames` is NaN -> `duration_sec` is NaN
- NaN propagating from upstream phase detection failure
"""

from __future__ import annotations

import math

import pytest

# ---------------------------------------------------------------------------
# 3 observable tests — NaN must NOT silently land in best-case branch
# ---------------------------------------------------------------------------


def test_nan_duration_does_not_silently_return_best_case_factor():
    """#1221: NaN duration_sec must NOT silently produce duration_factor=1.0.

    Pre-fix: `if duration_sec < 0.05:` is False for NaN (NaN comparisons
    always False), `elif duration_sec < 0.1:` is also False, so the `else`
    branch sets duration_factor=1.0. NaN input is indistinguishable from
    a healthy phase (duration_sec=0.5) for the purposes of this factor.

    Post-fix: NaN input must be guarded and the factor must NOT be 1.0.
    Concretely, the test passes if the result does not include the
    1.0 (best-case) duration_factor when duration_sec is NaN.
    """
    from src.analysis.confidence import compute_phase_confidence
    from src.analysis.types import PhaseExtended

    # 30 frames at 30 fps = 1.0 sec healthy duration, with high method factor
    # and high base confidence. The ONLY thing that should pull the result
    # away from "high confidence" is the NaN duration. If the bug is
    # present, NaN duration produces the SAME result as a healthy 1.0s
    # phase, hiding the data quality issue.
    healthy = PhaseExtended(
        name="air",
        start_frame=60,
        end_frame=90,
        start_time=2.0,
        end_time=3.0,
        confidence=0.95,
        detection_method="com_parabola",
    )
    nan_duration = PhaseExtended(
        name="air",
        start_frame=60.0,
        end_frame=float("nan"),  # corrupt end_frame -> NaN duration
        start_time=2.0,
        end_time=3.0,
        confidence=0.95,
        detection_method="com_parabola",
    )

    healthy_result = compute_phase_confidence(healthy, total_frames=120, fps=30.0)
    nan_result = compute_phase_confidence(nan_duration, total_frames=120, fps=30.0)

    # Healthy phase at 1.0s should be high confidence
    assert healthy_result > 0.7, (
        f"Healthy 1.0s phase should be high confidence, got {healthy_result}"
    )

    # The NaN-duration phase must NOT match the healthy result, because NaN
    # is "I don't know" not "this is a great phase". Pre-fix the two are
    # equal; post-fix NaN must be guarded (e.g. 0.0 or visibly lower).
    assert nan_result < healthy_result, (
        f"NaN duration must NOT be treated as best-case. "
        f"healthy_result={healthy_result}, nan_result={nan_result}. "
        f"Pre-fix: NaN lands in `else: duration_factor = 1.0`, matching healthy phase."
    )


def test_nan_duration_produces_isfinite_low_confidence():
    """#1221: NaN duration must yield isfinite output AND not be best-case.

    Post-fix expectation: result is finite (no NaN propagation) AND the
    duration factor is not 1.0. Acceptable outcomes:
    - return 0.0 (data unreliable)
    - return a low-confidence value with explicit NaN guard
    """
    from src.analysis.confidence import compute_phase_confidence
    from src.analysis.types import PhaseExtended

    nan_phase = PhaseExtended(
        name="air",
        start_frame=60.0,
        end_frame=float("nan"),
        start_time=2.0,
        end_time=3.0,
        confidence=0.95,
        detection_method="com_parabola",
    )
    result = compute_phase_confidence(nan_phase, total_frames=120, fps=30.0)

    assert math.isfinite(result), (
        f"NaN duration must NOT propagate to NaN output. Got {result}. "
        f"Pre-fix: NaN propagates to NaN weighted sum, then NaN check (line 70) "
        f"returns 0.0 — but ONLY if NaN propagates. Check if it actually does."
    )

    # Best-case factor is 1.0; with confidence=0.95, method=0.95, coverage 0.25
    # the weighted result for a fully-healthy 1s phase is high (>0.85).
    # NaN must NOT produce that high value.
    assert result < 0.85, (
        f"NaN duration must NOT yield high (best-case) confidence. Got {result}. "
        f"Pre-fix: NaN lands in `else: duration_factor = 1.0` -> ~0.92 result."
    )


def test_short_duration_still_uses_low_factor():
    """Sanity: short (0.001s) duration must still be flagged low (factor 0.3).

    This is the LEGITIMATE branch that NaN should NOT be silently routed to.
    Post-fix must NOT change this behavior — only NaN should be guarded.
    """
    from src.analysis.confidence import compute_phase_confidence
    from src.analysis.types import PhaseExtended

    short_phase = PhaseExtended(
        name="air",
        start_frame=60,
        end_frame=61,  # 1 frame at 30fps = 0.033s, < 0.05 -> factor 0.3
        start_time=2.0,
        end_time=2.033,
        confidence=0.95,
        detection_method="com_parabola",
    )
    nan_phase = PhaseExtended(
        name="air",
        start_frame=60.0,
        end_frame=float("nan"),
        start_time=2.0,
        end_time=3.0,
        confidence=0.95,
        detection_method="com_parabola",
    )

    short_result = compute_phase_confidence(short_phase, total_frames=120, fps=30.0)
    nan_result = compute_phase_confidence(nan_phase, total_frames=120, fps=30.0)

    # Short phase (0.033s) must still produce a lower confidence than the
    # NaN phase would in a pre-fix world (NaN -> 1.0 factor -> ~0.92).
    # Post-fix, the NaN must NOT be conflated with the short-phase case.
    # Specifically: the NaN result must be DIFFERENT from the short result
    # because they are semantically distinct ("suspiciously short" vs "I
    # don't know").
    assert nan_result != short_result, (
        f"NaN duration must not equal short duration result. "
        f"short_result={short_result}, nan_result={nan_result}. "
        f"Pre-fix: both are sub-best-case; NaN is still treated as best-case "
        f"in compute_phase_confidence so they differ, but the assertion here "
        f"guards against a future fix that conflates them."
    )
    # And: short phase must still be flagged low (not 0.0 — that would mean
    # we broke the existing short-duration detection).
    assert short_result > 0.0, (
        f"Short 0.033s phase must still have some confidence, got {short_result}"
    )
    assert short_result < 0.85, f"Short 0.033s phase must still be flagged low, got {short_result}"


# ---------------------------------------------------------------------------
# 1 regression test — valid boundary cases still behave correctly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("end_frame", "expected_in_range"),
    [
        (62, "low"),  # 2/30 = 0.067s, < 0.1 -> factor 0.6
        (64, "full"),  # 4/30 = 0.133s, >= 0.1 -> factor 1.0
    ],
)
def test_valid_duration_boundaries_unchanged(end_frame, expected_in_range):
    """Regression: post-fix, valid duration boundaries still produce expected factors.

    - 0.067s: < 0.1 -> factor 0.6
    - 0.133s: >= 0.1 -> factor 1.0
    """
    from src.analysis.confidence import compute_phase_confidence
    from src.analysis.types import PhaseExtended

    phase = PhaseExtended(
        name="air",
        start_frame=60,
        end_frame=end_frame,
        start_time=2.0,
        end_time=2.0 + (end_frame - 60) / 30.0,
        confidence=0.95,
        detection_method="com_parabola",
    )
    result = compute_phase_confidence(phase, total_frames=120, fps=30.0)

    if expected_in_range == "low":
        # 0.6 factor; combined with confidence 0.95, method 0.95, coverage ~0.033 -> moderate
        assert 0.0 < result < 0.85, f"0.067s phase should be moderate, got {result}"
    else:
        # 1.0 factor; combined should be the highest
        assert result > 0.85, f"0.133s phase should be high, got {result}"


# ---------------------------------------------------------------------------
# 1 source check — root cause is locked in (NaN comparisons are False)
# ---------------------------------------------------------------------------


def test_nan_comparisons_are_false_in_python():
    """Document the root cause: NaN < anything is always False in IEEE 754.

    This is the language-level fact that makes the bug possible. The fix
    is an explicit `math.isfinite(duration_sec)` check before the
    threshold comparisons, OR explicit NaN handling on `duration_frames`.
    """
    nan = float("nan")
    # NaN < 0.05 is False (this is what makes the bug silent)
    assert not (nan < 0.05), "NaN < 0.05 must be False (IEEE 754)"
    # NaN < 0.1 is also False
    assert not (nan < 0.1), "NaN < 0.1 must be False (IEEE 754)"
    # The only way to detect NaN is `math.isnan` or `not math.isfinite`.
    assert math.isnan(nan), "math.isnan(nan) is True"
    assert not math.isfinite(nan), "not math.isfinite(NaN) is True"
