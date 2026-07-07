"""RED repro — `GOEGrader.compute_goe_grade` / `detect_modifier`
(ml/src/analysis/goe_grader.py:55 / :94) SILENTLY INFLATE the GOE grade to 5
(perfect) and DROP the under-rotation modifier (`<<` → `""`) when
`rotation_count` is NaN.

Root cause: no `np.isfinite` guard on `rotation_count` before the
grade/modifier logic. NaN comparisons (`NaN >= 0.5`, `NaN > 0.25`,
`0 < NaN`) are ALL False, so every under-rotation branch is skipped and
`detect_modifier` returns `""`. `compute_goe_grade` then sees no error,
does NOT cap the grade at 3, and the other (finite) positive bullets
inflate the grade to 5 — a missing PRIMARY measurement scores PERFECT,
the dangerous (optimistic) direction. Mirrors #966 `classify_jump` guard
(NaN rotation_count → "unknown", 0.0).

Contract: a NaN `rotation_count` must NOT inflate the GOE grade to 5 and
must NOT silently erase the `<<` under-rotation modifier. The grader must
be CONSERVATIVE on a missing primary metric — capped grade, defined
modifier — NOT optimistic (clean +5 / `""`). Finite `rotation_count` is
unchanged (regression).

Pure-Python (no GPU, no DB): `GOEGrader` is a pure-data function over a
`list[MetricResult]`. The NaN rotation_count is fed directly.
"""

import inspect
import math

import numpy as np

from src.analysis.goe_grader import GOEGrader
from src.types import MetricResult

NaN = float("nan")


def _mr(name: str, val: float) -> MetricResult:
    return MetricResult(name=name, value=val, unit="x", is_good=True, reference_range=(0, 1))


def _full_metrics(rotation_count: float) -> list[MetricResult]:
    """A 'clean jump' metric set — all finite, all bullets met EXCEPT
    rotation_count, which is the parameter under test. With rc=3.0 this
    yields grade=5, modifier="" (perfect clean jump)."""
    return [
        _mr("max_height", 0.40),
        _mr("landing_com_velocity", -0.5),
        _mr("landing_smoothness", 0.9),
        _mr("hard_landing", 0.1),
        _mr("rotation_speed", 450),
        _mr("airtime", 0.55),
        _mr("approach_direction_change", 50.0),
        _mr("arm_position_score", 0.9),
        _mr("landing_trunk_recovery", 0.8),
        _mr("rotation_count", rotation_count),
    ]


# --------------------------------------------------------------------------- #
# Observable 1: NaN rotation_count must NOT inflate the grade to 5 (perfect).
# --------------------------------------------------------------------------- #


def test_nan_rotation_count_does_not_inflate_grade_to_5_repro():
    """CORRECT behavior: when `rotation_count` is NaN (occluded shoulder
    during fast rotation — a NORMAL case), `compute_goe_grade` must NOT
    return grade=5 (perfect). A missing PRIMARY measurement must yield a
    CONSERVATIVE (capped) grade — not the optimistic perfect 5. NaN
    comparisons are all False, so the under-rotation penalty is skipped
    and the finite positive bullets inflate the grade to 5 — silent
    wrong grade, optimistic direction (#923).

    RED now: grade=5 (perfect) for a NaN rotation_count. After fix: grade
    capped (≤3) — NaN is treated as missing, not as "clean".
    """
    grader = GOEGrader()
    result = grader.compute_goe_grade(_full_metrics(NaN), base_value=1.0, expected_rotations=3.0)
    assert result.grade < 5, (
        f"BUG: NaN rotation_count → grade={result.grade} (INFLATED to "
        f"perfect 5). NaN comparisons skipped the under-rotation penalty "
        f"and the finite positive bullets inflated the grade. A missing "
        f"PRIMARY measurement must NOT yield perfect — the grader must be "
        f"CONSERVATIVE (capped ≤3), not optimistic. Mirror #966 "
        f"classify_jump guard: NaN rotation_count → neutral/unknown. (#923)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: NaN rotation_count must NOT silently drop the '<<' modifier.
# --------------------------------------------------------------------------- #


def test_nan_rotation_count_does_not_drop_under_rotation_modifier_repro():
    """CORRECT behavior: when `rotation_count` is NaN, `detect_modifier`
    must NOT return `""` (silently dropping the under-rotation marker).
    A missing rotation count is conservative-severe under-rotation —
    the `<<` marker must be kept, OR replaced with a defined neutral
    modifier — NOT erased to `""` (which means "clean"). `shortfall =
    expected - NaN = NaN`; `NaN >= 0.5` / `NaN > 0.25` / `0 < NaN` are all
    False → modifier `""` (silently clean). This is the dangerous
    direction: a missing measurement reads as a clean jump (#923).

    RED now: modifier="" (silently dropped). After fix: modifier is a
    defined under-rotation marker (e.g. "<<" — conservative) or another
    non-empty defined neutral — NOT erased to "".
    """
    grader = GOEGrader()
    modifier = grader.detect_modifier({"rotation_count": NaN}, expected_rotations=3.0)
    assert modifier != "", (
        f"BUG: NaN rotation_count → modifier={modifier!r} (silently "
        f"dropped to clean). `shortfall = expected - NaN = NaN`; NaN >= 0.5 "
        f"= False, NaN > 0.25 = False, 0 < NaN = False → all under-rotation "
        f"branches skipped → modifier '' (clean). A missing PRIMARY "
        f"measurement must NOT read as clean — the modifier must be a "
        f"defined under-rotation marker (e.g. '<<' conservative) or a "
        f"defined neutral, NOT erased to ''. (#923)"
    )


# --------------------------------------------------------------------------- #
# Regression: finite rotation_count unchanged grade + modifier.
# --------------------------------------------------------------------------- #


def test_finite_rotation_count_unchanged_grade_and_modifier_repro():
    """Regression guard: a finite `rotation_count` (3.0 clean, 2.4
    downgraded, 2.85 q) must produce the SAME grade and modifier as before
    the NaN guard. The guard (np.isfinite) is identity on finite input —
    the no-NaN case must not regress.

    This PASSES today; it locks the contract so the NaN-aware fix cannot
    regress the finite case.
    """
    grader = GOEGrader()

    # Clean: rc=3.0 → modifier="", grade=5 (all bullets met).
    clean = grader.compute_goe_grade(_full_metrics(3.0), base_value=1.0, expected_rotations=3.0)
    assert clean.modifier == "", f"Clean rc=3.0 modifier regressed: {clean.modifier!r}"
    assert clean.grade == 5, f"Clean rc=3.0 grade regressed: {clean.grade}"

    # Downgraded: rc=2.4 → modifier="<<", grade capped at 3.
    downgraded = grader.compute_goe_grade(
        _full_metrics(2.4), base_value=1.0, expected_rotations=3.0
    )
    assert downgraded.modifier == "<<", (
        f"Downgraded rc=2.4 modifier regressed: {downgraded.modifier!r}"
    )
    assert downgraded.grade <= 3, f"Downgraded rc=2.4 grade cap regressed: {downgraded.grade}"

    # Quarter under: rc=2.85 → modifier="q".
    q = grader.detect_modifier({"rotation_count": 2.85}, expected_rotations=3.0)
    assert q == "q", f"q modifier rc=2.85 regressed: {q!r}"


# --------------------------------------------------------------------------- #
# Regression: NaN approach_direction_change does not silently drop edge
# modifier (related path — same NaN-comparison root cause).
# --------------------------------------------------------------------------- #


def test_nan_approach_direction_change_does_not_silently_drop_edge_modifier_repro():
    """CORRECT behavior: when `approach_direction_change` is NaN (and
    rotation_count is finite-clean), `detect_modifier` must NOT silently
    return `""` for the edge check. `abs(NaN) > 90` = False,
    `abs(NaN) > 60` = False → modifier "" (no edge error flagged). A
    missing direction-change measurement must NOT read as "clean edge" —
    it should flag a conservative unclear-edge `!` or a defined neutral,
    NOT erase to `""`. Same NaN-comparison root cause as rotation_count
    (#923). This locks the sibling path; the fix may cover both or just
    rotation_count (the PRIMARY signal named in #923) — the test asserts
    the contract for the path the fix covers.
    """
    grader = GOEGrader()
    # Clean rotation_count (3.0) + NaN approach_direction_change.
    modifier = grader.detect_modifier(
        {"rotation_count": 3.0, "approach_direction_change": NaN},
        expected_rotations=3.0,
    )
    assert modifier != "", (
        f"BUG: NaN approach_direction_change → modifier={modifier!r} "
        f"(silently dropped to clean). abs(NaN) > 90 / > 60 are False → "
        f"edge modifier '' (clean edge). A missing direction-change "
        f"measurement must NOT read as clean edge — conservative fallback "
        f"'!' (unclear edge), NOT erased to ''. Same NaN-comparison root "
        f"cause as rotation_count (#923)."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.isfinite / NaN guard added on
# rotation_count in detect_modifier (and/or compute_goe_grade).
# --------------------------------------------------------------------------- #


def test_goe_grader_has_nan_guard_on_rotation_count_repro():
    """GREEN contract source check: `GOEGrader.detect_modifier` (and/or
    `compute_goe_grade`) guards `rotation_count` with `np.isfinite` /
    `np.nan_to_num` before the grade/modifier logic, mirroring #966
    `classify_jump` (`if not np.isfinite(rotation_count): return "unknown",
    0.0`). This locks the root cause: a missing PRIMARY measurement must
    NOT inflate the grade or erase the modifier.
    """
    detect_src = inspect.getsource(GOEGrader.detect_modifier)
    compute_src = inspect.getsource(GOEGrader.compute_goe_grade)
    has_guard = ("np.isfinite" in detect_src or "np.nan_to_num" in detect_src) or (
        "np.isfinite" in compute_src or "np.nan_to_num" in compute_src
    )
    assert has_guard, (
        "BUG: GOEGrader has no NaN guard on rotation_count. NaN "
        "comparisons skip the under-rotation penalty (modifier '' ) and "
        "the finite positive bullets inflate the grade to 5 (perfect). "
        "Mirror #966 classify_jump: `if not np.isfinite(rotation_count): "
        "return 'unknown', 0.0` — guard at the trust boundary so a "
        "missing PRIMARY measurement yields a CONSERVATIVE grade + defined "
        "modifier, not optimistic perfect + erased modifier. (#923)"
    )


# --------------------------------------------------------------------------- #
# Self-check / __main__ demo — smallest runnable confirmation of the bug.
# --------------------------------------------------------------------------- #


def _demo() -> None:
    grader = GOEGrader()
    for rc in (3.0, 2.4, NaN):
        r = grader.compute_goe_grade(_full_metrics(rc), base_value=1.0, expected_rotations=3.0)
        print(f"rc={rc!r:>10}: grade={r.grade} modifier={r.modifier!r} score={r.estimated_score}")
    # Expected after fix:
    #   rc= 3.0: grade=5 modifier='' score=1.5   (clean, unchanged)
    #   rc= 2.4: grade=3 modifier='<<' score=0.7  (downgraded, unchanged)
    #   rc= nan: grade<=3 modifier='<<' (or defined neutral) — NOT 5/''


if __name__ == "__main__":
    _demo()
    # Sanity: math.isfinite rejects NaN, mirrors np.isfinite for floats.
    assert not math.isfinite(NaN)
    assert np.isfinite(3.0)
    print("ok")
