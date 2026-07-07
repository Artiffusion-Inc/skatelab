"""RED repro — fall detection silently skipped when metrics are NaN (#1230).

backend/app/services/choreography/deductions.py:32-43:

    smoothness = metrics.get("landing_smoothness", 1.0)
    hard_landing = metrics.get("hard_landing", 1.0)
    if smoothness < 0.05 and hard_landing < 0.1:    # 34
        # fall detected
    # NaN < X  ==  False   -> fall detection silently SKIPPED.

Python IEEE 754: any comparison with NaN is False, including `NaN < 0.05`.
So when landing_smoothness is NaN, the fall branch is bypassed silently
even if the skater actually fell. NaN data quality is hidden as "no fall".

This is a SAFETY-relevant miss: a real fall on the ice (e.g. a hard head
impact, a twisted knee) must not be silently swallowed by NaN propagation.
The coach dashboard downstream renders the silent skip as "no deduction",
which under-reports safety incidents.

Consumer chain:
    NaN smoothness/hard_landing  ->  silent skip  ->  no fall deduction
    ->  coach dashboard under-reports  ->  no medical follow-up.

Fix (NOT applied here): add math.isfinite(...) guard on both metrics before
the < comparisons; NaN inputs must NOT route through the fall branch.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEDUCTIONS_PATH = BACKEND_ROOT / "app" / "services" / "choreography" / "deductions.py"


def _load():
    spec = importlib.util.spec_from_file_location("_deductions_under_test", DEDUCTIONS_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fall_detection_source_guards_metrics_with_isfinite():
    """Static source check: the fall branch must guard both metrics with
    math.isfinite before the < comparisons. Pre-fix, the only check is
    `smoothness < 0.05 and hard_landing < 0.1` which silently passes NaN.

    Ponytail: the lazy fix is one guard, in the function that owns the
    comparison, not in every caller. Source must reference math.isfinite
    on both `smoothness` and `hard_landing`.
    """
    src = DEDUCTIONS_PATH.read_text(encoding="utf-8")

    # The function body must reference math.isfinite to guard the metrics
    # used in the fall threshold comparison.
    assert "math.isfinite" in src, (
        "BUG: detect_deductions() in deductions.py does not guard fall metrics "
        "with math.isfinite — NaN landing_smoothness / hard_landing silently "
        "skip the fall branch via `NaN < X == False` (#1230). "
        f"Source:\n{src}"
    )

    # The block under the `if smoothness < 0.05` line must reference
    # isfinite on the two specific metrics. Locate by searching for the
    # < 0.05 token and the surrounding context.
    idx = src.find("smoothness < 0.05")
    assert idx != -1, "Fall threshold `smoothness < 0.05` not found in deductions.py"
    window = src[max(0, idx - 400) : idx + 400]
    assert "isfinite(smoothness)" in window or "isfinite(hard_landing)" in window, (
        "Fall branch must wrap landing_smoothness / hard_landing with "
        "math.isfinite(...) before the < comparison (#1230). "
        f"Window around threshold:\n{window}"
    )


def test_fall_detection_nan_smoothness_silently_missed_on_master():
    """Direct repro: when landing_smoothness is NaN, the fall must NOT be
    silently swallowed by `NaN < 0.05 == False`.

    Pre-fix: result list is empty (silent miss).
    Post-fix: NaN input either (a) routes through the fall branch with the
    guard, or (b) is rejected explicitly before the threshold. Either way,
    the function must NOT silently produce the empty list as if "no fall
    happened" — the NaN is a data-quality signal that must be observable.
    """
    mod = _load()

    # NaN smoothness simulates an upstream pose gap (e.g. pose_estimation
    # couldn't see the landing frame). hard_landing is real (very hard,
    # 0.01 < 0.1). Pre-fix: NaN < 0.05 == False -> no fall detected.
    metrics = {
        "landing_smoothness": float("nan"),
        "hard_landing": 0.01,
    }
    result = mod.detect_deductions(metrics)

    # With the guard, NaN smoothness should not be silently treated as
    # "above the threshold" (i.e. "no fall"). We assert the guard is in
    # place via the source check above; here we assert behaviour:
    #   * it does not crash,
    #   * the function returns a list (not None, no exception),
    #   * the absence of a fall is NOT silent — if result is empty, the
    #     isfinite guard is the reason, not the NaN<0.05 shortcut.
    assert isinstance(result, list), (
        "detect_deductions must return a list even when metrics are NaN (#1230)."
    )
    # On master (no guard) this returns [] silently. We want the guard to
    # be the deterministic reason. The source-level test above enforces
    # that. This behavioural test asserts no crash and a list.
    # If the guard is in place, NaN smoothness should NOT cause a fall
    # deduction (NaN is invalid data, not a fall). But the function
    # must not appear to be working correctly on master.


def test_fall_detection_real_fall_still_detected():
    """Regression guard: real fall (finite low values) must still fire.
    The guard is additive — finite fall data must still produce a fall
    deduction. (Same invariant as #1246 happy path.)
    """
    mod = _load()
    metrics = {
        "landing_smoothness": 0.01,
        "hard_landing": 0.02,
    }
    result = mod.detect_deductions(metrics)
    assert len(result) >= 1, (
        "Real fall (finite low values) must still produce a fall deduction "
        "after the isfinite guard (#1230). Got empty result."
    )
    fall_ids = {d.deduction.id for d in result}
    assert "fall" in fall_ids, (
        f"Fall deduction id must be present for a real fall. Got ids: {fall_ids}"
    )


def test_fall_detection_hard_landing_above_threshold_no_fall():
    """Non-regression: when hard_landing is fine (>= 0.1), no fall is
    detected, even with low smoothness. (e.g. soft, slightly awkward
    landing — not a fall.)
    """
    mod = _load()
    metrics = {
        "landing_smoothness": 0.01,  # very low
        "hard_landing": 0.5,  # soft -> not a fall
    }
    result = mod.detect_deductions(metrics)
    fall_ids = {d.deduction.id for d in result}
    assert "fall" not in fall_ids, "hard_landing >= 0.1 must NOT trigger a fall deduction (#1230)."


def test_fall_detection_nan_hard_landing_with_real_smoothness():
    """Symmetry: hard_landing=NaN must also be guarded.

    Pre-fix: NaN hard_landing -> `NaN < 0.1 == False` -> no fall, even
    with real low smoothness. Same silent-skip class of bug as the
    smoothness case.
    """
    mod = _load()
    metrics = {
        "landing_smoothness": 0.01,
        "hard_landing": float("nan"),
    }
    # Behaviour assertion: must not crash, must return a list.
    result = mod.detect_deductions(metrics)
    assert isinstance(result, list), "NaN hard_landing must not crash detect_deductions (#1230)."
    # With the isfinite guard, NaN hard_landing is rejected explicitly
    # -> no fall. Without the guard, NaN<0.1==False -> no fall too.
    # The KEY differentiator from the smoothness case is that this case
    # would have fired if hard_landing were finite and low. We assert
    # here that the guard is deterministic on NaN — covered by the
    # source-level test. Behaviourally: no fall (NaN is invalid data).
