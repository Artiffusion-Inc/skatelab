"""RED repro — Issue #1224: GOE grader rotation shortfall silently drops
downgrade on NaN rotation_count.

`detect_modifier()` in ml/src/analysis/goe_grader.py reads
`mv.get("rotation_count", expected_rotations)`. When the metric value is
NaN (e.g. occluded shoulder during fast rotation — a NORMAL data quality
case, see #966), the shortfall chain:

    shortfall = expected_rotations - actual   # NaN
    if shortfall >= 0.5: ...                  # NaN >= 0.5 is False
    if shortfall > 0.25: ...                  # NaN >  0.25 is False
    if 0 < shortfall <= 0.25: ...             # 0 < NaN is False

silently falls through to no modifier and inflates the GOE grade (NaN
treated as "perfect rotation match"). Conservative fix: a non-finite
`rotation_count` reads as severe under-rotation and triggers the `<<`
modifier (mirrors #966 `classify_jump` — NaN rotation_count → "unknown").

These tests pin the contract. Pre-fix: tests fail (modifier="" for NaN,
grade inflates). Post-fix: tests pass (modifier="<<", conservative grade).
"""

from __future__ import annotations

import math

import numpy as np
import pytest


def _metrics_with_rotation_count(rotation_count):
    """Build a minimal metric set with the given rotation_count value."""
    from src.types import MetricResult

    return [
        MetricResult("rotation_count", rotation_count, "rot", True, (0, 10)),
    ]


def test_nan_rotation_count_triggers_double_less_modifier():
    """Issue #1224 / Tranche KJ: NaN rotation_count must trigger '<<'.

    Pre-fix: shortfall=NaN, all comparisons False, returns "" — silent
    data-quality hidden as perfect match (grade inflates).
    Post-fix: NaN guard returns "<<" — conservative severe under-rotation.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader.detect_modifier(
        {"rotation_count": float("nan")},
        expected_rotations=3.0,
    )
    assert result == "<<", (
        f"NaN rotation_count must trigger '<<' (conservative severe "
        f"under-rotation), got {result!r}. Pre-fix: silently returns '' "
        f"and inflates grade by hiding a data-quality problem as a "
        f"perfect match."
    )


def test_inf_rotation_count_triggers_double_less_modifier():
    """Issue #1224: +Inf rotation_count must also trigger '<<'.

    np.isfinite catches both NaN and ±Inf. Only a finite rotation count
    can be safely thresholded.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader.detect_modifier(
        {"rotation_count": float("inf")},
        expected_rotations=3.0,
    )
    assert result == "<<", (
        f"+Inf rotation_count must trigger '<<', got {result!r}. "
        f"Pre-fix: shortfall=-Inf, 'shortfall >= 0.5' is False, returns ''."
    )


def test_neg_inf_rotation_count_triggers_double_less_modifier():
    """Issue #1224: -Inf rotation_count must also trigger '<<'.

    Symmetric guard: -Inf is just as non-finite as NaN / +Inf and must
    not pass the shortfall thresholds.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    result = grader.detect_modifier(
        {"rotation_count": float("-inf")},
        expected_rotations=3.0,
    )
    assert result == "<<", (
        f"-Inf rotation_count must trigger '<<', got {result!r}. "
        f"Pre-fix: shortfall=+Inf, 'shortfall >= 0.5' is True and returns "
        f"'<<' accidentally — but for the wrong reason. The guard makes "
        f"the contract explicit."
    )


def test_nan_rotation_count_does_not_inflate_compute_goe_grade():
    """Issue #1224: full pipeline — NaN rotation_count must not yield
    estimated_score == bv (no modifier → full credit on a downgrade).

    Pre-fix: modifier="" so bv is full, estimated_score = bv * 1.0 = bv
    → looks like a perfect jump despite missing rotation data.
    Post-fix: modifier="<<" applies 0.7 BV multiplier (per #560), so
    estimated_score = 0.7 * bv (or lower depending on grade).
    """
    from src.analysis.goe_grader import GOEGrader
    from src.types import MetricResult

    grader = GOEGrader()
    metrics = [
        MetricResult("rotation_count", float("nan"), "rot", False, (0, 0)),
        MetricResult("airtime", 0.5, "s", True, (0.3, 0.6)),
    ]
    base_value = 8.0  # triple axel
    expected = 3.0
    result = grader.compute_goe_grade(metrics, base_value=base_value, expected_rotations=expected)

    assert result.modifier == "<<", (
        f"NaN rotation_count must produce modifier='<<', got "
        f"{result.modifier!r}. Hidden NaN data quality as perfect match "
        f"is the exact bug class issue #1224 names."
    )
    # With modifier='<<', adjusted BV = 8.0 * 0.7 = 5.6.
    # Grade is 0 (only 1 positive possible from the metrics above? No —
    # airtime=0.5 ≥ 0.3 yes, but rotation_speed is missing so 'effortless'
    # needs both; 'height_length' needs max_height too). With grade=0,
    # estimated_score = 5.6 (post-fix) vs 8.0 (pre-fix, full BV).
    assert result.estimated_score < base_value, (
        f"NaN rotation_count must NOT yield estimated_score == base_value "
        f"({base_value}); that would mean the downgraded jump got full "
        f"credit. Got estimated_score={result.estimated_score}. "
        f"Pre-fix path: modifier='' → bv=8.0 → estimated_score=8.0."
    )


def test_nan_rotation_count_via_metricresult_list_matches_dict():
    """Issue #1224: NaN propagation through list[MetricResult] path.

    `detect_modifier` accepts both dict and list[MetricResult]. Both
    paths must guard NaN identically.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    dict_result = grader.detect_modifier({"rotation_count": float("nan")}, expected_rotations=2.5)
    list_result = grader.detect_modifier(
        _metrics_with_rotation_count(float("nan")), expected_rotations=2.5
    )
    assert dict_result == list_result == "<<", (
        f"dict and list[MetricResult] paths must agree on NaN guard. "
        f"dict={dict_result!r}, list={list_result!r}. Mismatch means one "
        f"caller still has the silent-drop bug."
    )


def test_finite_rotation_count_thresholds_unchanged_by_nan_guard():
    """Issue #1224: guard must not break the finite path.

    Sanity: pre-existing thresholds (>= 0.5, > 0.25, 0 < x <= 0.25) must
    still work for normal rotation_count values. This guards against
    over-broad NaN guard (e.g. `if actual != actual` followed by
    break-the-world).
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    # shortfall 1.0 → '<<'
    assert grader.detect_modifier({"rotation_count": 2.0}, expected_rotations=3.0) == "<<"
    # shortfall 0.4 → '<'
    assert grader.detect_modifier({"rotation_count": 2.6}, expected_rotations=3.0) == "<"
    # shortfall 0.1 → 'q'
    assert grader.detect_modifier({"rotation_count": 2.9}, expected_rotations=3.0) == "q"
    # shortfall 0.0 → ''
    assert grader.detect_modifier({"rotation_count": 3.0}, expected_rotations=3.0) == ""
    # over-rotation (shortfall negative) → ''
    assert grader.detect_modifier({"rotation_count": 3.5}, expected_rotations=3.0) == ""


def test_missing_rotation_count_uses_expected_no_modifier():
    """Issue #1224: missing key (not NaN — key absent) keeps prior behavior.

    The .get(..., expected_rotations) default still applies when the
    key is absent. The NaN guard only fires when the value is present
    but non-finite. Regression check that we did not widen the guard.
    """
    from src.analysis.goe_grader import GOEGrader

    grader = GOEGrader()
    # No rotation_count key at all — default expected=3.0 → shortfall=0 → ''
    result = grader.detect_modifier({}, expected_rotations=3.0)
    assert result == "", (
        f"Missing rotation_count key must fall back to expected and "
        f"return '' (no modifier), got {result!r}."
    )


# ponytail: this exists — every assertion in this file is a contract on
# detect_modifier's NaN/Inf behaviour. Tranche KJ contract, see #1224.
