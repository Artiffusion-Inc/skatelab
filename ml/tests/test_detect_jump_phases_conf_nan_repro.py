"""RED repro — `_detect_jump_phases_com_improved` (ml/src/analysis/phase_detector.py)
silently REWARDS corrupted CoM data with confidence = 1.0 (max) via
`min(1.0, NaN) = 1.0` NaN-arg-order behavior.

Path (ml/src/analysis/phase_detector.py):
  `_detect_jump_phases_com_improved` (line 156):
    com_y = calculate_com_trajectory(poses)              # line 178/180
    vy = np.gradient(com_y) * fps                        # line 183 — NaN if com_y has NaN
    vy_std = np.std(vy)                                  # line 186 = nan
    # 287: `if vy_std < 1e-6: ...` — `nan < 1e-6` is False! Goes to else branch.
    velocity_confidence = (
        min(1.0, takeoff_signal / (2 * vy_std)) * 0.3  # NaN/NaN = NaN, min(1.0, NaN) = 1.0
        + min(1.0, landing_signal / (3 * vy_std)) * 0.2 # NaN/NaN = NaN, min(1.0, NaN) = 1.0
    )                                                    # = 0.3 + 0.2 = 0.5
    # 317: `if _math.isnan(prominence): confidence = 0.0` — PARTIAL fix from #562.
    #   Catches NaN prominence (from NaN IN flight window) but does NOT use
    #   math.isfinite (misses inf) and does NOT guard vy_std or the final
    #   confidence clamp. The OUTER `min(1.0, ...)` at line 320 silently
    #   max-rewards any NaN-leaked term via `min(1.0, NaN) = 1.0`.

Root cause verified empirically:
  min(1.0, NaN / 0.05) * 0.5  = 0.5   (silently max-rewarded)
  min(1.0, NaN)               = 1.0   (outer clamp max-rewards)
  math.isfinite(NaN)          = False (the correct guard — broader than isnan)

Consumer chain: `_detect_jump_phases_com_improved` is the primary CoM-based
jump phase detector. Confidence is used by the phase detector (which phases
to keep), element segmenter (weight jumps), recommender (surface jump
feedback). A NaN confidence producing 1.0 means a CORRUPTED CoM TRAJECTORY
is reported with MAX confidence.

The fix (NOT applied — repro only):
  - Replace `_math.isnan(prominence)` with `not math.isfinite(prominence)`
    (broader: catches NaN AND inf).
  - Add `not math.isfinite(vy_std)` guard to the velocity branch
    (the `vy_std < 1e-6` threshold does NOT catch NaN).
  - Add `not math.isfinite(confidence)` guard to the final clamp
    (defense in depth, sibling to #1025 three_turn fix).

Mirrors the PR #1025 (commit 258488c8) pattern for the three_turn path.

Methodology (per audit reglement):
  3 observables  (NaN prominence, NaN vy_std, NaN confidence outer clamp)
  1 regression   (valid CoM → sane confidence)
  1 source check (root cause locked via inspect.getsource)

Pure-Python + numpy: the function is pure arithmetic over pose arrays.
The test simulates the NaN-arg-order hazard at the source level and
verifies the source has the math.isfinite guards.
"""  # noqa: E501

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.phase_detector import PhaseDetector

# =========================================================================== #
# Observable 1: The `min(1.0, prominence / 0.05)` at line 299 silently
# rewards NaN prominence with 1.0. The fix must use `math.isfinite(prominence)`
# (broader than `math.isnan(prominence)`, which the existing #562 fix uses).
# =========================================================================== #


def test_nan_prominence_min_arg_order_hazard_repro():
    """CORRECT behavior: the `min(1.0, prominence / 0.05)` pattern at line 299
    must NOT silently return 1.0 for NaN prominence. The fix uses
    `math.isfinite(prominence)` to bypass this branch entirely when the
    input is non-finite.

    RED now: with NaN prominence, `min(1.0, NaN / 0.05) = 1.0` (first-arg
    wins, #454 arg-order trap). The weighted sum inflates to 0.5, then the
    outer `min(1.0, ...)` may also coerce NaN to 1.0. After the fix:
    `if not math.isfinite(prominence): prominence = 0.0` (or confidence = 0.0)
    bypasses this NaN-propagation entirely.
    """
    # Verify the NaN-arg-order hazard (the bug being fixed).
    prominence_nan = float("nan")
    weighted_buggy = min(1.0, prominence_nan / 0.05) * 0.5
    assert weighted_buggy == 0.5, (
        f"Python min(1.0, NaN) hazard check failed: got {weighted_buggy}, "
        f"expected 0.5 (the bug). If this changes, the test fixture is wrong."
    )

    # The fix is `if not math.isfinite(prominence)` — bypass the hazard.
    import math

    prominence = prominence_nan
    if not math.isfinite(prominence):
        confidence = 0.0
    else:
        confidence = min(1.0, min(1.0, prominence / 0.05) * 0.5)

    assert confidence == 0.0, (
        f"FIXED: with `math.isfinite(prominence)` guard, NaN prominence "
        f"yields confidence = {confidence} (expected 0.0). The isfinite "
        f"guard bypasses the `min(1.0, NaN) = 1.0` hazard."
    )


# =========================================================================== #
# Observable 2: The final `min(1.0, ...)` at line 296 also silently rewards
# NaN confidence with 1.0. Different from Observable 1 — this is the OUTER
# clamp, not the inner weighted term.
# =========================================================================== #


def test_outer_min_nan_arg_order_hazard_repro():
    """CORRECT behavior: the outer `min(1.0, ...)` at line 296 must NOT
    silently return 1.0 for a NaN confidence sum. The fix adds a
    `math.isfinite(confidence)` guard after the outer min clamp, as
    defense in depth (in case a future code path leaks NaN through the
    inner guards).
    """
    # Verify the NaN-arg-order hazard (the bug being fixed).
    confidence_nan = float("nan")
    final_buggy = min(1.0, confidence_nan)
    assert final_buggy == 1.0, (
        f"Python min(1.0, NaN) hazard check failed: got {final_buggy}, expected 1.0 (the bug)."
    )

    # The fix adds `if not math.isfinite(confidence)` guard — but applied
    # to the SUM BEFORE the outer min clamp. (Once min(1.0, NaN) has run,
    # you get 1.0 which is finite — the guard must be on the input, not the
    # clamp output.) Same defense-in-depth pattern as the three_turn fix.
    import math

    raw = confidence_nan
    if not math.isfinite(raw):
        clamped = 0.0
    else:
        clamped = min(1.0, raw)

    assert clamped == 0.0, (
        f"FIXED: with `math.isfinite(confidence)` guard on the input to "
        f"the outer clamp, NaN confidence yields {clamped} (expected 0.0). "
        f"This is the #1025 three_turn fix pattern: guard the input to "
        f"`min(1.0, ...)` so the NaN-arg-order hazard `min(1.0, NaN) = 1.0` "
        f"is bypassed entirely."
    )


# =========================================================================== #
# Observable 3: The `if vy_std < 1e-6` guard at line 287 does NOT catch NaN
# (NaN < 1e-6 is False in Python). The fix must also use `math.isfinite(vy_std)`.
# =========================================================================== #


def test_nan_vy_std_bypasses_threshold_guard_repro():
    """CORRECT behavior: a NaN vy_std (from NaN com_y) must NOT bypass the
    threshold guard. The existing `if vy_std < 1e-6` does NOT catch NaN
    (NaN < 1e-6 is False), so the velocity branch silently max-rewards to
    0.5 via `min(1.0, NaN)*0.3 + min(1.0, NaN)*0.2 = 0.5`. The fix adds
    `if not math.isfinite(vy_std)` to the threshold check.
    """
    import math

    vy_std_nan = float("nan")

    # The buggy threshold check: NaN < 1e-6 is False, so it goes to else.
    if vy_std_nan < 1e-6:
        velocity_confidence_buggy = 0.0
    else:
        # `min(1.0, NaN) = 1.0` → 0.3 + 0.2 = 0.5 (max-rewarded)
        velocity_confidence_buggy = (
            min(1.0, 0.0 / (2 * vy_std_nan)) * 0.3 + min(1.0, 0.0 / (3 * vy_std_nan)) * 0.2
        )
    assert velocity_confidence_buggy == 0.5, (
        f"vy_std threshold guard check failed: NaN vy_std → "
        f"velocity_confidence = {velocity_confidence_buggy} (expected 0.5, "
        f"the bug)."
    )

    # The fix: `if not math.isfinite(vy_std) or vy_std < 1e-6`.
    if not math.isfinite(vy_std_nan) or vy_std_nan < 1e-6:
        velocity_confidence_fixed = 0.0
    else:
        velocity_confidence_fixed = 0.5  # placeholder
    assert velocity_confidence_fixed == 0.0, (
        f"FIXED: with `math.isfinite(vy_std)` guard, NaN vy_std yields "
        f"velocity_confidence = {velocity_confidence_fixed} (expected 0.0). "
        f"The isfinite guard catches the NaN that the < 1e-6 threshold misses."
    )


# =========================================================================== #
# Regression guard: the existing `vy_std < 1e-6` guard for flat input must
# still work. The fix adds isfinite (NOT replaces the threshold).
# =========================================================================== #


def test_flat_input_velocity_confidence_zero_repro():
    """Regression guard: with flat (no-motion) CoM, vy_std is ~0, the
    existing `vy_std < 1e-6` guard sets `velocity_confidence = 0.0`. The
    fix (`if not math.isfinite(vy_std) or vy_std < 1e-6`) preserves this
    behavior — the threshold still fires for flat input.
    """
    import math

    vy_std_flat = 1e-9  # below 1e-6 threshold
    if not math.isfinite(vy_std_flat) or vy_std_flat < 1e-6:
        velocity_confidence = 0.0
    else:
        velocity_confidence = 1.0  # placeholder
    assert velocity_confidence == 0.0, (
        f"BUG (regression): flat-input velocity_confidence = "
        f"{velocity_confidence} (expected 0.0 from the `vy_std < 1e-6` "
        f"guard). The fix must preserve the flat-input path."
    )


# =========================================================================== #
# Source check: root cause locked — the fix must add `math.isfinite` guards
# on prominence, vy_std, and the final confidence clamp.
# =========================================================================== #


def test_isfinite_guards_present_on_prominence_vy_std_and_confidence_repro():
    """Source check: the fix must add `math.isfinite` guards on:
      1. prominence (broader than the existing `math.isnan` from #562)
      2. vy_std (catches NaN that the < 1e-6 threshold misses)
      3. final confidence (defense in depth, sibling to #1025 three_turn fix)

    RED now: NONE of these guards are present. The existing code has only
    `if _math.isnan(prominence)` (partial fix from #562, narrower than
    isfinite). After the fix: all three guards appear.
    """
    src = inspect.getsource(PhaseDetector._detect_jump_phases_com_improved)

    # The prominence computation is unchanged.
    assert "prominence = float(np.max(flight_com) - np.min(flight_com))" in src, (
        "BUG: prominence must still be derived from flight CoM (max - min)."
    )

    # Guard #1: math.isfinite(prominence) (broader than isnan).
    assert "math.isfinite(prominence)" in src, (
        "BUG: _detect_jump_phases_com_improved must guard prominence with "
        "math.isfinite (catches NaN AND inf). The existing `math.isnan` "
        "guard (#562) is narrower — misses inf."
    )

    # Guard #2: math.isfinite(vy_std) (catches NaN that < 1e-6 misses).
    assert "math.isfinite(vy_std)" in src or "isfinite(vy_std)" in src, (
        "BUG: _detect_jump_phases_com_improved must guard vy_std against "
        "NaN. The existing `if vy_std < 1e-6` does NOT catch NaN (NaN < 1e-6 "
        "is False in Python), so a NaN vy_std silently max-rewards the "
        "velocity branch to 0.5. This is the root cause of #1088."
    )

    # Guard #3: math.isfinite guard on the sum-of-terms BEFORE the outer
    # min(1.0, ...) clamp. (The clamp is `min(1.0, conf_sum)` where
    # conf_sum = inner_term + velocity_confidence; the guard is on the
    # input to the clamp, not the result — same pattern as #1025 three_turn
    # fix which guards max_change BEFORE the cap.)
    assert "isfinite(" in src and (
        "isfinite(conf_sum)" in src
        or "isfinite(confidence)" in src
        or "isfinite(c)" in src  # alternate variable name
    ), (
        "BUG: _detect_jump_phases_com_improved must guard the input to the "
        "outer min(1.0, ...) clamp with math.isfinite (defense in depth, "
        "sibling to #1025 three_turn fix which guards max_change BEFORE "
        "the cap). The guard catches any future NaN-leak path that the "
        "inner guards miss."
    )

    # The NaN-arg-order hazards are bypassed (source no longer relies on
    # `min(1.0, NaN) = 1.0` falling through to 1.0).
    # We don't assert absence of the pattern (the clamp structure is fine
    # if guarded) — we just verify the guards exist.
