"""RED repro: classify_jump NaN rotation_count silent misclassification (#966).

Root cause: no isfinite guard on rotation_count before threshold chain.
NaN < x is always False → rotation bonus silently 0 for all candidates,
but toe_pick/direction bonuses survive → max() picks a named jump with
positive false confidence.
"""

import inspect
import math

from src.analysis.jump_classifier import classify_jump

NAN = float("nan")


def test_classify_jump_source_has_nan_guard():
    """Source-check: isfinite/nan guard added before threshold chain (root-cause lock)."""
    src = inspect.getsource(classify_jump)
    assert "np.isfinite" in src or "math.isfinite" in src or "isnan" in src, (
        "classify_jump must guard rotation_count with isfinite/isnan before thresholds"
    )
    # And the guard must precede the threshold comparison `diff = abs(rotation_count - ...)`.
    guard_idx = min(
        [src.find(tok) for tok in ("np.isfinite", "math.isfinite", "isnan") if src.find(tok) != -1]
    )
    diff_idx = src.find("diff = abs(rotation_count")
    assert guard_idx != -1 and diff_idx != -1 and guard_idx < diff_idx, (
        "NaN guard must appear before the threshold comparison"
    )


def test_nan_rotation_count_returns_unknown_low_confidence():
    name, conf = classify_jump(NAN, has_toe_pick_signal=False, takeoff_direction="backward")
    assert name == "unknown", (
        f"NaN rotation_count must not yield named jump, got {name!r} conf={conf}"
    )
    assert conf == 0.0, f"NaN rotation_count must yield zero confidence, got {conf}"


def test_nan_rotation_count_not_confident_for_every_takeoff_style():
    for toe_pick in (False, True):
        for direction in ("forward", "backward"):
            name, conf = classify_jump(
                NAN, has_toe_pick_signal=toe_pick, takeoff_direction=direction
            )
            assert conf < 0.1, (
                f"NaN rot toe_pick={toe_pick} dir={direction}: confident {name!r} conf={conf}"
            )
            assert name == "unknown", (
                f"NaN rot must be unknown, got {name!r} for toe_pick={toe_pick} dir={direction}"
            )


def test_nan_diff_comparison_silently_skips_rotation_bonus_semantics():
    """Lock NaN-comparison semantics: abs(NaN - x) < threshold is False, not raise."""
    assert not (abs(NAN - 1.0) < 0.3)
    assert not (abs(NAN - 1.0) < 0.6)


def test_finite_rotation_count_classifies_correctly_regression():
    """Regression guard: finite rotation_count classification unchanged."""
    name, conf = classify_jump(1.5, has_toe_pick_signal=False, takeoff_direction="forward")
    assert name == "axel", f"expected axel, got {name!r}"
    assert conf > 0.5, f"axel confidence too low: {conf}"
    # Single toe loop (toe pick, backward, rotations=1 in ElementDef)
    name_t, conf_t = classify_jump(1.0, has_toe_pick_signal=True, takeoff_direction="backward")
    assert name_t == "toe_loop", f"expected toe_loop, got {name_t!r}"
    assert conf_t > 0.5, f"single toe_loop confidence too low: {conf_t}"
