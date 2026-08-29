"""RED repro guard — `classify_jump` (ml/src/analysis/jump_classifier.py)
NaN/inf `rotation_count` must not silently produce a low-confidence
named-jump classification (#1052, tranche FQ).

Family: NaN-tranche via `if diff < x` / `elif diff < x` thresholds in
the rotation-match scoring chain. Mirrors #912/#915/#962/#1007/#1041/
#1042/#1045/#1049 NaN-tranche family. Root cause: `abs(NaN - x) = NaN`,
`NaN < 0.3` is False, `NaN < 0.6` is False — both rotation-match bonuses
silently skipped, but toe_pick + direction bonuses survive, yielding a
named jump with positive false confidence. The caller (phase detector →
recommender → UI) cannot tell the input was bad.

Contract (GREEN — fix is in place on master via #1013, mirroring #1030
pattern in `compute_rotation_yaw_delta`):
  - `classify_jump(rotation_count=NaN, ...)` must return `("unknown", 0.0)`
    (or raise `ValueError`) — never a named jump with non-zero confidence.
  - Same for `rotation_count=+inf` and `rotation_count=-inf`.
  - All `ELEMENT_DEFS` are finite — only `rotation_count` can be NaN/inf.
  - Source check: `classify_jump` must contain an `isfinite` (or
    `isnan`/`nan_to_num`) guard on `rotation_count` BEFORE the threshold
    comparison `diff = abs(rotation_count - ...)`. Without this guard the
    silent NaN-bypass is back.
  - Regression: valid finite inputs (1.5 forward → axel, 1.0 toe_pick
    backward → toe_loop, 0.0 → any edge jump) still classify correctly
    with finite confidence in [0.0, 1.0].

This test file is the regression guard. If anyone reverts the
`np.isfinite(rotation_count)` guard at the top of `classify_jump`, these
tests will fail with explicit diff messages naming the bug. Currently
GREEN on master — see `audit/test_jump_classifier_nan_propagate_repro.py`
in the backend-save-audit worktree for the historical REPRO/RED-observable
coverage.

Methodology:
  1 source check (isfinite/nan_to_num guard, ordering)
  3 observable  (NaN, +inf, -inf → "unknown", 0.0)
  1 regression  (finite rotation_count → finite, in [0.0, 1.0])

Pure-Python (no GPU, no ONNX, no DB): the function is pure arithmetic
over float inputs. We feed synthetic NaN/inf rotation counts to isolate
the silent NaN-bypass.
"""

from __future__ import annotations

import inspect
import math

from src.analysis.jump_classifier import classify_jump

NAN = float("nan")
POS_INF = float("inf")
NEG_INF = float("-inf")


# =========================================================================== #
# Source check: root cause locked — the `classify_jump` function MUST have an
# `isfinite` (or `isnan`/`nan_to_num`) guard on `rotation_count` appearing
# BEFORE the threshold chain `diff = abs(rotation_count - ...)`. Without
# this guard, NaN/inf silently bypasses rotation matching while toe_pick
# + direction bonuses survive → false-positive named classification.
# =========================================================================== #


def test_classify_jump_source_has_nan_rotation_guard():
    """Source check: `classify_jump` has an `isfinite` (or `isnan`/
    `nan_to_num`) guard on `rotation_count` BEFORE the threshold
    comparison. If the guard is removed/regressed, this test fails
    — and the NaN/inf tests below flip to observable failure too.
    """
    src = inspect.getsource(classify_jump)

    # At least one NaN-guard idiom must be present.
    guard_tokens = ("np.isfinite", "math.isfinite", "isnan", "nan_to_num")
    guard_idxs = [src.find(tok) for tok in guard_tokens if src.find(tok) != -1]
    assert guard_idxs, (
        "classify_jump must guard rotation_count with isfinite / isnan / "
        "nan_to_num before the threshold chain. The silent NaN-bypass is "
        "back. Add e.g. `if not math.isfinite(rotation_count): return "
        '"unknown", 0.0` at the top of the function.'
    )

    # The guard must appear BEFORE the threshold comparison
    # `diff = abs(rotation_count - ...)` to actually prevent the bypass.
    diff_idx = src.find("diff = abs(rotation_count")
    assert diff_idx != -1, (
        "classify_jump threshold chain changed shape — update this test to "
        "match the new comparison pattern. The guard ordering must still "
        "precede any rotation_count threshold comparison."
    )
    first_guard = min(guard_idxs)
    assert first_guard < diff_idx, (
        f"NaN guard at offset {first_guard} must appear BEFORE the threshold "
        f"comparison at offset {diff_idx}. Otherwise the silent NaN-bypass "
        f"is back (NaN < x is False, rotation bonus silently 0, toe_pick + "
        f"direction bonuses still produce a named jump with false confidence)."
    )


# =========================================================================== #
# Observable 1: `rotation_count = NaN` → ("unknown", 0.0). NOT a named jump
# with non-zero confidence. NaN must be rejected upfront.
# =========================================================================== #


def test_classify_jump_nan_rotation_count_returns_unknown_zero_confidence():
    """NaN rotation_count must NOT silently produce a named-jump
    classification. Must return `("unknown", 0.0)` (or raise).
    """
    name, conf = classify_jump(
        rotation_count=NAN,
        has_toe_pick_signal=False,
        takeoff_direction="backward",
    )
    assert name == "unknown", (
        f"NaN rotation_count must yield 'unknown', got {name!r} conf={conf}. "
        f"Silent NaN-bypass regression — fix removed? See #1052."
    )
    assert conf == 0.0, (
        f"NaN rotation_count must yield zero confidence, got {conf}. "
        f"Silent NaN-bypass regression — fix removed? See #1052."
    )
    assert math.isfinite(conf), (
        f"NaN rotation_count must yield finite confidence, got {conf} (NaN)."
    )


# =========================================================================== #
# Observable 2: `rotation_count = +inf` → ("unknown", 0.0). inf - x = inf,
# abs(inf) = inf, inf < 0.3 is False, inf < 0.6 is False. Same bypass as
# NaN. Must be rejected.
# =========================================================================== #


def test_classify_jump_pos_inf_rotation_count_returns_unknown_zero_confidence():
    """+inf rotation_count must NOT silently produce a named-jump
    classification. Must return `("unknown", 0.0)`.
    """
    name, conf = classify_jump(
        rotation_count=POS_INF,
        has_toe_pick_signal=False,
        takeoff_direction="backward",
    )
    assert name == "unknown", (
        f"+inf rotation_count must yield 'unknown', got {name!r} conf={conf}. "
        f"Silent inf-bypass regression — fix removed? See #1052."
    )
    assert conf == 0.0, f"+inf rotation_count must yield zero confidence, got {conf}."
    assert math.isfinite(conf), (
        f"+inf rotation_count must yield finite confidence, got {conf} (inf or NaN)."
    )


# =========================================================================== #
# Observable 3: `rotation_count = -inf` → ("unknown", 0.0). -inf - x = -inf,
# abs(-inf) = inf, same bypass. Must be rejected.
# =========================================================================== #


def test_classify_jump_neg_inf_rotation_count_returns_unknown_zero_confidence():
    """-inf rotation_count must NOT silently produce a named-jump
    classification. Must return `("unknown", 0.0)`.
    """
    name, conf = classify_jump(
        rotation_count=NEG_INF,
        has_toe_pick_signal=False,
        takeoff_direction="backward",
    )
    assert name == "unknown", (
        f"-inf rotation_count must yield 'unknown', got {name!r} conf={conf}. "
        f"Silent -inf-bypass regression — fix removed? See #1052."
    )
    assert conf == 0.0, f"-inf rotation_count must yield zero confidence, got {conf}."
    assert math.isfinite(conf), (
        f"-inf rotation_count must yield finite confidence, got {conf} (inf or NaN)."
    )


# =========================================================================== #
# Regression guard: valid finite inputs still classify correctly with
# finite confidence in [0.0, 1.0]. The NaN guard must not change the
# typical case.
# =========================================================================== #


def test_classify_jump_finite_rotation_count_regression_unchanged():
    """Regression: valid finite inputs (1.5 forward → axel,
    1.0 toe_pick backward → toe_loop) still classify with finite
    confidence in [0.0, 1.0]. The NaN guard must not change the
    typical case.
    """
    # Single axel: 1.5 rotations, no toe pick, forward.
    name, conf = classify_jump(
        rotation_count=1.5,
        has_toe_pick_signal=False,
        takeoff_direction="forward",
    )
    assert name == "axel", f"expected axel, got {name!r} conf={conf}"
    assert math.isfinite(conf), f"axel confidence must be finite, got {conf}"
    assert 0.0 <= conf <= 1.0, f"axel confidence out of range: {conf}"

    # Single toe loop: 1.0 rotations, toe pick, backward.
    name_t, conf_t = classify_jump(
        rotation_count=1.0,
        has_toe_pick_signal=True,
        takeoff_direction="backward",
    )
    assert name_t == "toe_loop", f"expected toe_loop, got {name_t!r} conf={conf_t}"
    assert math.isfinite(conf_t), f"toe_loop confidence must be finite, got {conf_t}"
    assert 0.0 <= conf_t <= 1.0, f"toe_loop confidence out of range: {conf_t}"
