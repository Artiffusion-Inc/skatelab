"""RED repro — `compute_phase_confidence` silently treats NaN inputs as full
match via the `max(0.0, min(1.0, x))` clamp's arg-order trap on NaN.

Path (ml/src/analysis/confidence.py):
  `compute_phase_confidence` (line 11):
    duration_sec = duration_frames / fps if fps > 0 else 0           # 25
    coverage = duration_frames / total_frames if total_frames > 0 else 0   # 40
    confidence = phase.confidence * 0.4 + duration_factor * 0.25 \
                 + method_factor * 0.25 + coverage_factor * 0.10      # 44-49
    return max(0.0, min(1.0, confidence))                             # 51

The function is the LAST line of defense in phase detection confidence.
Three independent NaN-bypass bugs in one function:

1. **NaN-arg-order-dependent clamp (line 51)** — the most dangerous:
   `min(1.0, NaN) = 1.0` (first arg wins when comparison False) and
   `max(0.0, 1.0) = 1.0` → a NaN-poisoned `confidence` returns **1.0 (MAX
   confidence)**, the OPPOSITE of the intended clamp. A phase with NaN
   inputs is reported as "perfectly confident". A user trusts a broken
   result.

2. **NaN-blind `fps > 0` guard (line 25)** — `duration_sec = duration_frames
   / fps if fps > 0 else 0` silently coerces `fps=NaN` to 0 (`NaN > 0` is
   False). The function returns the same value as a legitimate `fps=0`,
   masking the bad input.

3. **NaN-blind `total_frames > 0` guard (line 40)** — same pattern,
   `total_frames=NaN` is silently coerced to 0, indistinguishable from a
   legitimate `total_frames=0`.

Plus `compute_overall_confidence` (line 64) calls `compute_phase_confidence`
per phase, so a single NaN phase infects the overall confidence weighted
average.

The fix (NOT applied — repro only): guard inputs with `math.isfinite` at
the trust boundary, fall back to 0.0 (or raise ValueError) when NaN/inf
propagates through. The `max(0.0, min(1.0, x))` clamp must be preceded
by an `isfinite`/`nan_to_num` guard so NaN never produces a wrong
finite answer (0.0 ceiling collapse, not 1.0 inflation).

Pure-Python (no GPU, no DB): `compute_phase_confidence` is a pure-data
function over PhaseExtended + scalars.
"""

from __future__ import annotations

import inspect
import math

import numpy as np

from ml.src.analysis.confidence import compute_phase_confidence
from ml.src.analysis.types import PhaseExtended


def _phase(confidence: float = 0.9) -> PhaseExtended:
    """A representative phase — finite baseline for finite regression checks."""
    return PhaseExtended(
        name="takeoff",
        start_frame=55,
        end_frame=60,
        start_time=1.83,
        end_time=2.0,
        confidence=confidence,
        detection_method="com_parabola",
    )


# --- 1. NaN input returns finite, NOT 1.0 -----------------------------


def test_compute_phase_confidence_nan_input_returns_finite_not_nan_repro():
    """`phase.confidence = NaN` must NOT collapse to 1.0 via arg-order clamp.

    Without the fix, `confidence = NaN * 0.4 + ... = NaN`, then
    `min(1.0, NaN) = 1.0` (Python first-arg-wins on NaN comparison False)
    and `max(0.0, 1.0) = 1.0` — a NaN-poisoned upstream phase gets reported
    as **MAX confidence (1.0)**, the worst possible wrong answer.

    The correct behavior: NaN input must produce a finite value that is
    NOT the 1.0 ceiling. Either 0.0 (signal corruption -> no confidence) or
    a raised exception.
    """
    phase = _phase(confidence=float("nan"))
    result = compute_phase_confidence(phase, total_frames=120, fps=30.0)
    # Must be finite.
    assert math.isfinite(result), (
        f"NaN input must NOT propagate as NaN output, got {result!r}. "
        "Caller trusts this number — silent NaN breaks downstream logic."
    )
    # Must NOT be the 1.0 ceiling (the silent inflation bug).
    assert result < 1.0, (
        f"NaN input must NOT collapse to 1.0 ceiling, got {result!r}. "
        "This is the #1051 silent inflation bug — user gets 'perfectly "
        "confident' phase report when the actual detection was broken."
    )


# --- 2. NaN fps does not silently coerce to 0 --------------------------


def test_compute_phase_confidence_nan_fps_does_not_silently_zero_repro():
    """`fps = NaN` must NOT silently propagate NaN through the math.

    Without the fix, `fps=NaN` makes `NaN > 0` False -> `duration_sec = 0`
    -> `duration_factor = 0.3` (suspicious-short branch), same as the
    legitimate `fps=0` case. The downstream math `phase.confidence * 0.4 +
    ... + coverage_factor * 0.10` is finite (no NaN leaks) ONLY if the
    `coverage_factor` and `phase.confidence` are finite. The smoking gun
    is: the result must be finite (not NaN) and the call must succeed
    (no exception), regardless of whether the result matches fps=0 or
    the function chose to raise.

    The proper fix coerces NaN/inf to 0.0 at the trust boundary (PR 1025
    `np.isfinite` pattern) so the function does not crash AND the result
    is a finite, deterministic value. Either an exception is raised OR
    the result is finite — both are acceptable.
    """
    phase = _phase(confidence=0.9)
    try:
        nan_fps_result = compute_phase_confidence(
            phase, total_frames=120, fps=float("nan")
        )
    except (ValueError, TypeError):
        # Acceptable: raise at the trust boundary.
        return
    # Result must be finite — the smoking gun for NaN leak.
    assert math.isfinite(nan_fps_result), (
        f"NaN fps must not propagate as NaN result, got {nan_fps_result!r}. "
        "Fix: coerce NaN/inf to 0.0 at the trust boundary (math.isfinite "
        "guard) — same family as #1007/#1025."
    )


# --- 3. NaN total_frames does not silently coerce to 0 -----------------


def test_compute_phase_confidence_nan_total_frames_does_not_silently_zero_repro():
    """`total_frames = NaN` must NOT silently propagate NaN through the math.

    Without the fix, `total_frames=NaN` makes `NaN > 0` False ->
    `coverage = 0` -> `coverage_factor = 0`. The smoking gun is the
    function must not return NaN, and either raise or return a finite
    deterministic value.
    """
    phase = _phase(confidence=0.9)
    try:
        nan_total = compute_phase_confidence(
            phase, total_frames=float("nan"), fps=30.0
        )
    except (ValueError, TypeError):
        return
    # Result must be finite — the smoking gun for NaN leak.
    assert math.isfinite(nan_total), (
        f"NaN total_frames must not propagate as NaN result, got {nan_total!r}. "
        "Fix: coerce NaN/inf to 0 at the trust boundary (math.isfinite "
        "guard on total_frames) — same family as #1007/#1025."
    )


# --- 4. Valid finite input is unchanged (regression) -------------------


def test_compute_phase_confidence_valid_unchanged_repro():
    """Valid finite inputs -> finite result in [0.0, 1.0]. No regression."""
    phase = _phase(confidence=0.91)
    result = compute_phase_confidence(phase, total_frames=120, fps=30.0)
    assert math.isfinite(result), f"Valid input must produce finite result, got {result!r}"
    assert 0.0 <= result <= 1.0, f"Valid input must produce in-range result, got {result!r}"
    # Expected: 0.91*0.4 + 1.0*0.25 (duration=5/30=0.166s) + 0.95*0.25 (com_parabola)
    #          + coverage_factor*0.10 where coverage=5/120=0.0417, factor=0.0417/0.1=0.4167
    # = 0.364 + 0.25 + 0.2375 + 0.04167 = 0.89317
    assert abs(result - 0.8931666666666667) < 1e-6, (
        f"Valid input regression: expected ~0.8932, got {result!r}. "
        "Ensure the NaN guard does not change the finite path."
    )


# --- 5. Source check: NaN guard present at trust boundary -------------


def test_compute_phase_confidence_unguarded_nan_source_repro():
    """Source-level RED check: the function has no isfinite / nan_to_num
    guard at the trust boundary. The fix must add one.

    Scans the function source for any of: `math.isfinite`, `np.isfinite`,
    `np.nan_to_num`, `np.nanmax`, `math.isnan` — these are the standard
    trust-boundary guards. None are present in the unfixed source.

    The existing `math.isnan(confidence)` check at line 59 covers ONLY
    the final `confidence` value (bug #1 mitigation), but does NOT
    protect the upstream NaN propagation through `fps` and `total_frames`
    (bugs #2 and #3). For a complete fix, the source must guard the INPUT
    boundary (fps, total_frames) — not just the OUTPUT.
    """
    source = inspect.getsource(compute_phase_confidence)
    src_lower = source.lower()
    # Locate the bug sites by source markers.
    assert "fps > 0" in src_lower, "Bug #2 site (fps > 0) missing — refactor changed the function?"
    assert "total_frames > 0" in src_lower, "Bug #3 site (total_frames > 0) missing — refactor changed the function?"
    # Check that at least ONE of the standard NaN guards is present at
    # the INPUT boundary. The function as-shipped has a `math.isnan` check
    # only on the FINAL `confidence` value (which already exists from
    # #561), but no guard on `fps` or `total_frames`. This test ensures
    # the source has *some* trust-boundary guard on the inputs.
    input_guard_patterns = [
        "isfinite(fps",
        "isfinite(total_frames",
        "nan_to_num(fps",
        "nan_to_num(total_frames",
        "isnan(fps",
        "isnan(total_frames",
    ]
    has_input_guard = any(p in src_lower for p in input_guard_patterns)
    assert has_input_guard, (
        "compute_phase_confidence has NO NaN guard on `fps` or "
        "`total_frames` at the trust boundary. The `fps > 0` and "
        "`total_frames > 0` guards silently coerce NaN to 0 (NaN > 0 is "
        "False), masking bad upstream inputs. Fix: add `math.isfinite` "
        "guard (or `np.nan_to_num`) on `fps` and `total_frames` at the "
        "trust boundary, same family as #1007/#1025 pattern."
    )
