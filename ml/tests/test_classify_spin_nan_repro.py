"""RED repro — `classify_spin` (spin_classifier.py:19-64) and `detect_spin`
(spin_classifier.py:67-126) leak NaN/-inf into the returned confidence /
duration when a non-finite input slips past the trust boundary. Issue #1053.

Root cause (spin_classifier.py:39-64):

    if duration_s >= spin.min_duration_s:
        score += 0.3
    else:
        score += 0.1 * (duration_s / spin.min_duration_s)   # NaN/-inf producer

    best = max(candidates, key=lambda x: x[1])
    return best[0], min(best[1], 1.0)                        # NaN/-inf propagates

The `else` branch on line 42 ACTIVELY PRODUCES NaN/-inf in the score:
- `0.1 * (NaN / x) = NaN`
- `0.1 * (-inf / x) = -inf`

That NaN/-inf propagates through `score += ...` into the candidate list, then
`min(NaN, 1.0) = NaN` and `min(-inf, 1.0) = -inf` on line 64 — violating the
documented [0, 1] confidence contract. JSON serialization crashes
(`json.dumps(allow_nan=False)`), the GOE composite poisons, the UI displays
`NaN` / `-inf` to the user.

`detect_spin` (line 109): `(end - start) / fps if fps > 0 else 0.0` — NaN fps
→ `NaN > 0` is False → silent NaN→0 coercion, indistinguishable from
`fps=0.0`. Already covered by #505 sibling test
(`audit/test_fps_zero_division_repro.py::test_detect_spin_fps_zero_no_infinite_duration`).
This file focuses on the `classify_spin` NaN/-inf family per the issue title.

Verified empirically:
    classify_spin(NaN,  0.1, 350.0) -> ('upright_spin', NaN)
    classify_spin(-inf, 0.1, 350.0) -> ('upright_spin', -inf)
    classify_spin(+inf, 0.1, 350.0) -> ('upright_spin', 0.7)  # safe (> branch)
    classify_spin(2.0, NaN, 350.0)  -> ('upright_spin', 0.7)  # safe (else branch finite)
    classify_spin(2.0, 0.1, NaN)    -> ('upright_spin', 0.8)  # safe (else branch finite)

Worse than `classify_jump` (tranche FQ): the NaN-bypass there is contained
(NaN rotation_count silently produces a "no match" with finite score). Here the
bypass ACTIVELY PRODUCES NaN/-inf in the score and propagates to the return.

Fix (NOT applied — repro only): guard the trust boundary at function entry.
A non-finite `duration_s` MUST NOT enter the `else` branch (line 42) — and
even if it did, the `min(..., 1.0)` clamp on line 64 MUST NOT propagate NaN/-
inf. Mirror the lazy root-cause fix: one `math.isfinite` guard at the function
entry that returns `("unknown", 0.0)` (the documented [0, 1] sentinel for
"no data"), keeping the contract intact on the all-finite path. Identity on
all-finite input — the existing `classify_upright_spin` / `classify_scratch_spin`
regressions must still pass.

These tests MUST fail (RED) against the current code. Repros, not fixes.
"""

import inspect
import math

from src.analysis.spin_classifier import classify_spin

# ---------------------------------------------------------------------------
# Bug 1: classify_spin NaN duration_s -> NaN confidence
# ---------------------------------------------------------------------------


def test_classify_spin_nan_duration_returns_finite_confidence_repro():
    """`duration_s=NaN` must not poison confidence. spin_classifier.py:42
    `0.1 * (NaN / x) = NaN` in the `else` branch propagates through
    `min(NaN, 1.0) = NaN` on line 64. The documented [0, 1] confidence
    contract is violated — `json.dumps(allow_nan=False)` crashes, GOE
    composite poisons, UI displays `NaN`.
    """
    name, conf = classify_spin(
        duration_s=float("nan"),
        hip_y_range=0.1,
        angular_velocity_mean=350.0,
    )

    assert math.isfinite(conf), (
        f"BUG 1: classify_spin leaked NaN into confidence under NaN duration: "
        f"name={name!r}, conf={conf}. spin_classifier.py:42 `0.1 * (NaN / x) = "
        f"NaN` in the else branch propagates through `min(NaN, 1.0) = NaN` on "
        f"line 64. The [0, 1] confidence contract is violated. #1053."
    )
    assert 0.0 <= conf <= 1.0, (
        f"BUG 1: classify_spin confidence {conf} outside documented [0, 1] "
        f"under NaN duration. #1053."
    )


# ---------------------------------------------------------------------------
# Bug 2: classify_spin -inf duration_s -> -inf confidence
# ---------------------------------------------------------------------------


def test_classify_spin_neg_inf_duration_returns_finite_confidence_repro():
    """`duration_s=-inf` must not poison confidence. spin_classifier.py:42
    `0.1 * (-inf / x) = -inf` in the `else` branch propagates through
    `min(-inf, 1.0) = -inf` on line 64. Same family as Bug 1 — non-finite
    `duration_s` cannot enter the active producer.
    """
    name, conf = classify_spin(
        duration_s=float("-inf"),
        hip_y_range=0.1,
        angular_velocity_mean=350.0,
    )

    assert math.isfinite(conf), (
        f"BUG 2: classify_spin leaked -inf into confidence under -inf "
        f"duration: name={name!r}, conf={conf}. spin_classifier.py:42 "
        f"`0.1 * (-inf / x) = -inf` in the else branch propagates through "
        f"`min(-inf, 1.0) = -inf` on line 64. #1053."
    )
    assert 0.0 <= conf <= 1.0, (
        f"BUG 2: classify_spin confidence {conf} outside documented [0, 1] "
        f"under -inf duration. #1053."
    )


# ---------------------------------------------------------------------------
# Bug 3: classify_spin +inf duration_s must stay safe (regression)
# ---------------------------------------------------------------------------
# +inf is currently safe (it routes through the `if duration_s >=
# min_duration_s` branch — all positive finite `min_duration_s` make
# `+inf >= 1.0` True, so the active producer on line 42 is skipped). This
# pins that behavior: a fix MUST NOT regress the +inf path into the broken
# else-branch. If a future refactor moves the guard inside the if-branch, this
# test catches the regression.


def test_classify_spin_pos_inf_duration_stays_finite_repro():
    """`duration_s=+inf` must keep producing a finite confidence. Currently
    safe because `+inf >= min_duration_s` is True for all positive finite
    `min_duration_s`, routing to the `score += 0.3` branch (finite). The fix
    MUST NOT regress this path — e.g. by checking isfinite inside the if-branch
    in a way that turns +inf into NaN.
    """
    name, conf = classify_spin(
        duration_s=float("inf"),
        hip_y_range=0.1,
        angular_velocity_mean=350.0,
    )

    assert math.isfinite(conf), (
        f"BUG 3: classify_spin produced non-finite confidence under +inf "
        f"duration: name={name!r}, conf={conf}. The +inf path is currently "
        f"safe and the fix MUST preserve it. #1053."
    )
    assert 0.0 <= conf <= 1.0, (
        f"BUG 3: classify_spin confidence {conf} outside documented [0, 1] "
        f"under +inf duration. #1053."
    )


# ---------------------------------------------------------------------------
# Regression: classify_spin valid inputs unchanged (identity on finite)
# ---------------------------------------------------------------------------


def test_classify_spin_valid_inputs_unchanged_repro():
    """Regression — the fix must be identity on all-finite input. A normal
    upright-spin call (duration=2.0, hip_y=0.05, omega=400) MUST still
    classify as `upright_spin` with a confidence in (0.5, 1.0] (mirrors
    test_spin_classifier.py::test_classify_upright_spin).
    """
    name, conf = classify_spin(
        duration_s=2.0,
        hip_y_range=0.05,
        angular_velocity_mean=400.0,
    )

    assert name == "upright_spin", (
        f"REGRESSION: classify_spin mis-classified on valid input: "
        f"name={name!r}, conf={conf}. Fix must be identity on all-finite input."
    )
    assert math.isfinite(conf), (
        f"REGRESSION: classify_spin produced non-finite confidence on valid input: conf={conf}."
    )
    assert 0.5 < conf <= 1.0, (
        f"REGRESSION: classify_spin confidence {conf} outside expected "
        f"(0.5, 1.0] for valid upright-spin input."
    )


# ---------------------------------------------------------------------------
# Source check: spin_classifier.classify_spin must have a finite guard
# ---------------------------------------------------------------------------


def test_classify_spin_has_isfinite_guard_repro():
    """Source-level guard check: `classify_spin` MUST defend against non-finite
    `duration_s` at the trust boundary. Acceptable defenses (in order of
    laziness): `math.isfinite`, `np.isfinite`, `math.isfinite` + clamp,
    or a raise/return on non-finite. The current source has NEITHER — line 42
    `0.1 * (duration_s / spin.min_duration_s)` is unguarded and line 64
    `min(best[1], 1.0)` propagates NaN/-inf. This test pins the fix in source.
    """
    source = inspect.getsource(classify_spin)

    has_isfinite = "math.isfinite" in source or "np.isfinite" in source or "isfinite" in source
    has_nan_to_num = "nan_to_num" in source
    has_explicit_finite_check = "isnan(" in source or "isinf(" in source

    assert has_isfinite or has_nan_to_num or has_explicit_finite_check, (
        "BUG SRC: classify_spin has NO finite guard on `duration_s`. "
        "spin_classifier.py:42 `0.1 * (duration_s / spin.min_duration_s)` "
        "is unguarded — NaN/-inf `duration_s` propagates through to the "
        "`min(..., 1.0)` clamp on line 64. Fix must add `math.isfinite` "
        "(or equivalent) at the trust boundary. #1053."
    )
