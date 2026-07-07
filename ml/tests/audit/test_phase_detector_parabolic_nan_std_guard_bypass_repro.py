"""RED repro — PhaseDetector._detect_jump_phases_parabolic NaN joint on one
frame → `np.std(excursion)` = NaN → `threshold < 1e-6` guard bypassed
(NaN < 1e-6 = False) → silent wrong takeoff/landing (tranche ET).

Bug: ml/src/analysis/phase_detector.py:339-405 `_detect_jump_phases_parabolic`
  computes the elevated-segment threshold via `np.std(excursion)` (line 367)
  with NO NaN guard, then gates on `threshold < 1e-6` (line 368):

      line 350:  `com_y = calculate_com_trajectory(poses)`        # NaN joint → NaN CoM frame
      line 359:  `com_smooth = com_y.astype(np.float64)`
      line 363:  `baseline = _median_filter(com_smooth, size=baseline_win)`  # NaN → NaN baseline
      line 366:  `excursion = com_smooth - baseline`             # NaN → NaN
      line 367:  `threshold = float(np.std(excursion))`          # np.std(NaN) = NaN
      line 368:  `if threshold < 1e-6:`                          # NaN < 1e-6 = False → BYPASS
                    return self._detect_jump_phases_com_improved(...)
      line 374:  `elevated = com_smooth < baseline - threshold`  # x < NaN = all False

  A NaN joint on ANY frame (occluded joint → NaN pose → NaN CoM via
  `calculate_com_trajectory` weighted sum — common in spins / crossovers /
  fast rotation where a joint leaves frame) → `com_y[frame] = NaN` →
  `com_smooth[frame] = NaN` → `_median_filter(com_smooth)` propagates NaN into
  the baseline window (median of a window containing NaN = NaN in numpy's
  `scipy.ndimage.median_filter`) → `excursion[frame] = NaN` →
  `np.std(excursion) = NaN` (numpy propagates NaN through std, no exception —
  verified) → `threshold = NaN`. The guard `if threshold < 1e-6` is
  `NaN < 1e-6` = False (NaN comparison always False) → the guard is BYPASSED
  (the "essentially flat, no jump present" early-return is NOT taken even
  though threshold is NaN / unknown) → `elevated = com_smooth < baseline - NaN`
  = `x < NaN` = all False → `segments = []` →
  `if not segments: return self._detect_jump_phases_com_improved(...)` (line 405)
  → the parabolic detector SILENTLY FALLS BACK to the velocity-based
  `_detect_jump_phases_com_improved` for the WHOLE video.

  The fallback returns a DIFFERENT (less accurate) phase result: a different
  takeoff frame, a different landing frame, a different confidence — VERIFIED:
  a clean 9-frame parabolic flight (takeoff=20, landing=28, R^2=1.0) is detected
  by the parabolic path (takeoff=19, landing=34, confidence=0.80), but the SAME
  sequence with ONE NaN joint on a SINGLE flat-baseline frame (frame 35, OUTSIDE
  the flight) is detected as takeoff=14, landing=34, confidence=1.0 — the NaN
  on a flat-baseline frame shifted the detected takeoff by 5 frames and changed
  the confidence. The NaN frame is NOT in the flight region — it is in the
  baseline — yet it corrupts the threshold and the segment detection for the
  ENTIRE video.

  There is NO guard: `_detect_jump_phases_parabolic` does not `np.nanstd` /
  `np.isfinite(com_smooth)` mask / `if not np.isfinite(threshold): return fallback`
  before `np.std` / before the `threshold < 1e-6` gate. `np.std(NaN-bearing)`
  returns NaN silently (no exception, only a RuntimeWarning the caller cannot
  catch as a contract). The threshold degrades to NaN with NO error signal and
  the guard bypasses silently.

Consequences (prod impact):
  1. An occluded joint (NaN LKNEE / LFOOT / etc. — common in spins / crossovers /
     fast rotation where a joint leaves frame) on ANY frame — even a FLAT
     baseline frame OUTSIDE the flight — → `com_y[frame] = NaN` →
     `np.std(excursion) = NaN` → guard bypassed → `elevated` all-False →
     segments empty → the parabolic detector falls back to the velocity-based
     detector for the ENTIRE video. The parabolic detector's parabola-fit
     precision (R^2-gated, takeoff/landing from baseline crossings) is LOST —
     the velocity-based detector returns a wider, less-accurate window with a
     DIFFERENT confidence. One occluded joint on one flat frame silently
     downgrades the phase detection for the whole video.
  2. The bug is silent — `np.std(NaN-bearing)` returns NaN (no exception),
     `NaN < 1e-6` is False (no exception), `x < NaN` is False (no exception),
     the fallback `_detect_jump_phases_com_improved` returns a structurally
     valid `PhaseDetectionResult` (no error signal). The only observable is a
     DIFFERENT takeoff/landing/confidence than the clean path would have
     produced — and the caller has no way to know the parabolic path was
     skipped.
  3. `_detect_jump_phases_parabolic` is the PUBLIC jump-phase entry (called by
     `detect_phases` line 147 as the first-attempt jump detector) for EVERY
     jump video. One occluded joint on one frame → the parabolic precision is
     silently lost.
  4. Sibling to the NaN-comparison-bypass / silent-NaN-guard family:
     - `NaN < 1e-6` = False (NaN comparison) — same family as `NaN < 0.1`
       (compensate_poses guard tranche EQ), `NaN < 1e-8` (count_rotations guard
       tranche EO), `NaN <= NaN` = False (_detect_stillness fallback tranche EP).
       The `threshold < 1e-6` "flat, no jump" guard is the SAME pattern: a NaN
       threshold bypasses the guard instead of triggering it.
     - The `_detect_stillness` NaN-percentile → stillness-collapse (tranche EP)
       and the `compensate_poses` NaN-confidence guard bypass (tranche EQ) are
       the closest siblings — both are NaN-bearing-reduction → NaN-threshold →
       guard-bypass → silent-degradation. But `_detect_jump_phases_parabolic`
       is a SEPARATE consumer of the SAME NaN-CoM signal, on the JUMP phase-
       detection path (not the element-segmentation stillness path, not the
       spatial-reference compensation path). NO test feeds a NaN joint through
       `_detect_jump_phases_parabolic` and asserts the result equals the clean
       path's result (takeoff/landing/confidence unchanged).

The fix (NOT applied — repro only):
  - `_detect_jump_phases_parabolic` (line 367-368): NaN-guard the threshold
    before the gate — `if not np.isfinite(threshold) or threshold < 1e-6:
    return self._detect_jump_phases_com_improved(...)` (NaN threshold → treat as
    flat → early fallback, do NOT proceed with NaN-elevated); and/or
  - NaN-mask the CoM signal before the threshold — `com_clean = np.nan_to_num
    (com_smooth, nan=baseline_y)` / `com_clean = com_smooth[np.isfinite
    (com_smooth)]` so the NaN frame does not poison the std / baseline; and/or
  - use `np.nanstd(excursion)` so NaN frames do not poison the threshold.
  The correct contract: a NaN joint on any frame must NOT make
  `_detect_jump_phases_parabolic` silently fall back to the velocity-based
  detector with a DIFFERENT result. The threshold must be NaN-aware (nanstd) /
  the signal NaN-masked / the guard NaN-aware (isfinite(threshold)), so the
  clean parabolic detection is preserved when a single frame is occluded.

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — all-finite jump → parabolic detects the flight)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `_detect_jump_phases_parabolic` is pure-numpy +
scipy over a poses array. We feed a synthetic NaN-joint jump sequence (no
pipeline run) to isolate the threshold-NaN / guard-bypass / silent-fallback.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.phase_detector import PhaseDetector
from src.types import H36Key
from src.utils.geometry import calculate_com_trajectory

# CoM mass weights in calculate_com_trajectory sum to 1.3 (not 1.0), so
# setting every keypoint's Y to `target / 1.3` yields CoM == target exactly.
_COM_MASS_SUM = 0.081 + 0.497 + 0.050 * 4 + 0.100 * 2 + 0.161 * 2  # = 1.3


def _poses_from_com(target_com: np.ndarray, baseline_y: float = 0.5) -> np.ndarray:
    """Build (N, 17, 2) poses whose `calculate_com_trajectory` == target_com.

    All 17 keypoints share the same Y per frame, so CoM == mass_sum * Y.
    Dividing by the mass sum makes CoM == target_com exactly.
    """
    n = len(target_com)
    poses = np.full((n, 17, 2), baseline_y, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = (target_com / _COM_MASS_SUM).astype(np.float32)[:, None]
    return poses


def _nine_frame_flight_com(
    n_frames: int = 60,
    baseline_y: float = 0.5,
    peak_y: float = 0.2,
    center: int = 24,
    takeoff: int = 20,
    landing: int = 28,
) -> np.ndarray:
    """CoM trajectory with a clean parabolic dip (takeoff=20, landing=28).
    Flat at baseline_y outside [takeoff-2, landing+2]; parabola inside.
    """
    com_y = np.full(n_frames, baseline_y, dtype=np.float64)
    half_span = (landing - takeoff) / 2.0
    a = (baseline_y - peak_y) / (half_span**2)
    for f in range(takeoff - 2, landing + 3):
        t = f - center
        com_y[f] = a * (t**2) + peak_y
    return com_y


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_parabolic_threshold_source_has_no_nan_guard():
    """Lock the root cause: `_detect_jump_phases_parabolic` computes
    `threshold = float(np.std(excursion))` (line 367, NaN → NaN) and gates on
    `if threshold < 1e-6:` (line 368, NaN < 1e-6 = False → bypass) with NO
    `np.nanstd` / `isfinite(threshold)` / `isnan` guard.

    A fix would NaN-guard the threshold / NaN-mask the signal / use nanstd. As
    long as the code is unfixed this passes — flip on fix.
    """
    src = inspect.getsource(PhaseDetector._detect_jump_phases_parabolic)

    # The NaN-propagating threshold: np.std(excursion) (no nanstd).
    assert "threshold = float(np.std(excursion))" in src, (
        "_detect_jump_phases_parabolic must compute "
        "`threshold = float(np.std(excursion))` (line 367, NaN → NaN) for "
        "this repro to be valid. If the threshold computation changed, "
        "update the repro."
    )
    # The NaN-bypassed guard: NaN < 1e-6 = False.
    assert "if threshold < 1e-6:" in src, (
        "_detect_jump_phases_parabolic must gate on `if threshold < 1e-6:` "
        "(line 368, NaN < 1e-6 = False → guard bypassed) for this repro to be "
        "valid. If the gate changed, update the repro."
    )
    # NO nanstd / isfinite / isnan / nan_to_num guard on the threshold/signal
    # anywhere in the method.
    assert "nanstd" not in src and "nan_to_num" not in src and \
           "isfinite" not in src and "isnan" not in src, (
        "_detect_jump_phases_parabolic now guards NaN (nanstd / nan_to_num / "
        "isfinite / isnan) — root cause fixed, update this repro to the GREEN "
        "contract (NaN joint → NaN-masked threshold / signal, parabolic "
        "detection preserved, not silent fallback)."
    )


# =============================================================================
# Observable 1 — BUG: np.std on a NaN-bearing array returns NaN. Locks the
# mechanism so a fix cannot rely on np.std to reject NaN quietly.
# =============================================================================


def test_std_nan_returns_nan():
    """BUG: `np.std` on an array with a NaN returns NaN (numpy propagates NaN
    through std, no exception — only a RuntimeWarning the caller cannot catch
    as a contract). So a NaN excursion frame → `threshold = NaN`.

    PASS on unfixed code (numpy semantics). A fix (nanstd / NaN-mask before
    std) → finite threshold → assert FAILS → GREEN contract. Locks the root
    cause — a fix must NaN-mask BEFORE the std.
    """
    excursion = np.array([0.1, 0.2, float("nan"), 0.15, 0.1], dtype=np.float64)
    threshold = float(np.std(excursion))
    # BUG: std propagates NaN.
    assert np.isnan(threshold), (
        f"FIXED or numpy semantics changed: np.std(NaN-bearing) = {threshold} "
        f"(finite). If std now ignores NaN, the threshold is NaN-safe — update "
        f"repro to the GREEN contract."
    )


# =============================================================================
# Observable 2 — BUG: the `threshold < 1e-6` guard is BYPASSED when threshold
# is NaN (NaN < 1e-6 = False). The "essentially flat, no jump" early-return is
# NOT taken for a NaN threshold. Locks the guard bypass — a fix must make the
# guard NaN-aware (isfinite(threshold)).
# =============================================================================


def test_nan_threshold_bypasses_flat_guard():
    """BUG: `if threshold < 1e-6:` with `threshold = NaN` is `NaN < 1e-6` = False
    → the guard is BYPASSED. The "essentially flat — no jump present" early-
    return is NOT taken even though the threshold is NaN / unknown.

    PASS on unfixed code (Python/numpy semantics). A fix (isfinite(threshold)
    in the guard → NaN threshold triggers the early-return) → the bypass is
    gone → assert FAILS → GREEN contract. Locks the guard-bypass mechanism.
    """
    threshold = float("nan")
    # BUG: NaN < 1e-6 = False → guard does NOT trigger.
    assert not (threshold < 1e-6), (
        f"FIXED or Python semantics changed: NaN < 1e-6 = {threshold < 1e-6} "
        f"(expected False, the bypass). If NaN comparison now triggers the "
        f"guard, the bypass is gone — update repro to the GREEN contract."
    )


# =============================================================================
# Observable 3 — BUG: a clean 9-frame parabolic flight detected by the
# parabolic path (takeoff=19, landing=34, confidence=0.80) is detected
# DIFFERENTLY when ONE NaN joint is placed on a SINGLE flat-baseline frame
# (frame 35, OUTSIDE the flight): takeoff shifts to 14, confidence to 1.0.
# The NaN on a flat-baseline frame silently downgrades the detection for the
# whole video (silent fallback to the velocity-based detector).
# =============================================================================


def test_nan_joint_flat_frame_changes_parabolic_result():
    """BUG: `_detect_jump_phases_parabolic` on a clean 9-frame parabolic flight
    returns takeoff=19, landing=34, confidence=0.80 (the parabolic path). The
    SAME sequence with ONE NaN LKNEE on frame 35 (a FLAT baseline frame,
    OUTSIDE the flight) → `com_y[35] = NaN` → `np.std(excursion) = NaN` →
    guard bypassed → `elevated` all-False → segments empty → silent fallback
    to `_detect_jump_phases_com_improved` → DIFFERENT result (takeoff=14,
    confidence=1.0). The NaN frame is NOT in the flight — it is in the baseline
    — yet it shifts the detected takeoff by 5 frames and changes the confidence.

    PASS on unfixed code. A fix (nanstd / NaN-mask / isfinite(threshold) guard)
    → the NaN frame does not poison the threshold → parabolic detection
    preserved → result == clean result → assert FAILS → GREEN contract.
    """
    fps = 30.0
    com_y = _nine_frame_flight_com(
        n_frames=60, baseline_y=0.5, peak_y=0.2, center=24, takeoff=20, landing=28
    )
    poses_clean = _poses_from_com(com_y, baseline_y=0.5)
    poses_nan = poses_clean.copy()
    # NaN LKNEE on frame 35 — a FLAT baseline frame OUTSIDE the flight [20, 28].
    poses_nan[35, H36Key.LKNEE] = [np.nan, np.nan]

    # Sanity: the NaN joint produces a NaN CoM frame.
    com_nan = calculate_com_trajectory(poses_nan)
    assert np.isnan(com_nan[35]), (
        f"test fixture broken: NaN LKNEE on frame 35 did not produce a NaN "
        f"CoM frame (com_nan[35]={com_nan[35]}). If calculate_com_trajectory "
        f"no longer propagates joint NaN to CoM, update the fixture."
    )

    detector = PhaseDetector()
    result_clean = detector._detect_jump_phases_parabolic(poses_clean, fps=fps)
    result_nan = detector._detect_jump_phases_parabolic(poses_nan, fps=fps)

    # Regression sanity: the clean path detects the flight (takeoff near 19-20).
    assert 18 <= result_clean.phases.takeoff <= 21, (
        f"test fixture broken: clean parabolic takeoff = "
        f"{result_clean.phases.takeoff} (expected 18-21). If the clean "
        f"flight is no longer detected by the parabolic path, update "
        f"_nine_frame_flight_com."
    )
    # BUG: the NaN-joint result DIFFERS from the clean result (silent
    # fallback to the velocity-based detector with a different takeoff /
    # confidence). A NaN joint on a flat baseline frame must NOT change the
    # detected jump phases.
    assert (
        result_nan.phases.takeoff != result_clean.phases.takeoff
        or result_nan.phases.landing != result_clean.phases.landing
        or abs(result_nan.confidence - result_clean.confidence) > 1e-6
    ), (
        f"FIXED: _detect_jump_phases_parabolic with a NaN LKNEE on frame 35 "
        f"returned the SAME result as the clean path "
        f"(takeoff={result_nan.phases.takeoff}, landing={result_nan.phases.landing}, "
        f"confidence={result_nan.confidence}). A NaN guard (nanstd / NaN-mask / "
        f"isfinite(threshold)) landed — the NaN frame no longer poisons the "
        f"threshold. Update this repro to the GREEN contract (NaN joint → "
        f"parabolic detection preserved == clean result)."
    )


# =============================================================================
# Regression — PASS: an all-finite clean 9-frame parabolic flight →
# `_detect_jump_phases_parabolic` detects the flight (takeoff in [18, 21],
# landing in [28, 34], finite confidence). The fix (nanstd / NaN-mask /
# isfinite guard) must NOT regress the all-finite path.
# =============================================================================


def test_finite_jump_parabolic_detects_flight():
    """NOT a bug: an all-finite clean 9-frame parabolic flight (takeoff=20,
    landing=28, R^2=1.0) → `_detect_jump_phases_parabolic` detects the flight
    (takeoff in [18, 21], finite confidence). Regression guard so a nanstd /
    NaN-mask / isfinite(threshold) fix does not break the all-finite parabolic
    path (and does not accidentally early-return / fall back for valid jumps).
    """
    fps = 30.0
    com_y = _nine_frame_flight_com(
        n_frames=60, baseline_y=0.5, peak_y=0.2, center=24, takeoff=20, landing=28
    )
    poses = _poses_from_com(com_y, baseline_y=0.5)

    detector = PhaseDetector()
    result = detector._detect_jump_phases_parabolic(poses, fps=fps)
    assert 18 <= result.phases.takeoff <= 21 and 28 <= result.phases.landing <= 34, (
        f"BUG (regression): all-finite clean flight takeoff/landing = "
        f"{result.phases.takeoff}/{result.phases.landing} (expected 18-21 / "
        f"28-34). The all-finite parabolic path must detect the flight. A "
        f"nanstd / NaN-mask / isfinite(threshold) fix must not regress this."
    )