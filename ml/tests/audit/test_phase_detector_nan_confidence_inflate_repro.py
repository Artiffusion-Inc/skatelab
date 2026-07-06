"""RED repro — `PhaseDetector.detect_phases` (jump path) inflates the
detection `confidence` to 1.0 when a keypoint is NaN across all frames — a
false BEST on a degenerate/occluded input.

Path (ml/src/analysis/phase_detector.py):
  `detect_phases` (line 72) → `detect_jump_phases` (127) →
  `_detect_jump_phases_parabolic` (309):
    com_y = calculate_com_trajectory(poses)              # line 350
    com_smooth = com_y.astype(float64)                   # 359
    baseline = _median_filter(com_smooth, size=...)      # 363 — NaN propagates
    excursion = com_smooth - baseline                    # 366
    threshold = float(np.std(excursion))                # 367 = nan
    if threshold < 1e-6: ...                             # 368 — `nan < 1e-6` is False
    elevated = com_smooth < baseline - threshold         # 374 — all NaN-compares False
    segments = []                                         # 404 — no segments
    return self._detect_jump_phases_com_improved(...)    # 405 — fallback

  `_detect_jump_phases_com_improved` (149):
    com_y = calculate_com_trajectory(poses)              # 173 — NaN
    vy = np.gradient(com_y) * fps                        # 176 — NaN
    vy_std = np.std(vy)                                  # 179 = nan
    find_peaks(-vy, height=2*vy_std, distance=10)         # 183 — height=nan → empty
    find_peaks(vy, height=3*vy_std, distance=10)         # 187 — height=nan → empty
    # empty candidates → fallback peak = len(poses)//2, takeoff = peak-10, landing = peak+10
    airtime = (landing - takeoff) / fps                  # 234 ≈ 0.67 > 0.3 gate
    # 273: takeoff < peak < landing holds (5 < 15 < 25)
    flight_com = com_y[takeoff : landing + 1]            # 274 — has NaN
    prominence = float(np.max(flight_com) - np.min(flight_com))  # 275 = nan
    # 287: vy_std < 1e-6 — `nan < 1e-6` is False → velocity_confidence branch
    velocity_confidence = min(1.0, takeoff_signal/(2*vy_std))*0.3 + min(1.0, ...)*0.2
                                                          # `min(1.0, nan) = 1.0` (#454)
    confidence = min(1.0, min(1.0, prominence/0.05)*0.5 + velocity_confidence)
                                                          # `min(1.0, nan/0.05)=1.0`, sum > 1
                                                          # `min(1.0, ...) = 1.0`

Result: `confidence = 1.0` (false BEST) for a NaN-poisoned input, vs a
finite, lower confidence (~0.39) for the all-valid same input.

`calculate_com_trajectory` (geometry.py:287-335) is a weighted sum of ALL 17
keypoint Y-coordinates. One NaN keypoint across all frames → `com_y` is all
NaN → the whole detection chain collapses as above. Same root cause as
BM/BN/BP/BQ/BR/BS/BT/BV/BW (CoM plain weighted sum, no NaN handling), plus
the #454 `min(1.0, nan) = 1.0` arg-order trap on the confidence clamps.

Consequences (prod impact — `confidence` is user-facing, drives whether the
analysis report is trusted):
  1. A video where one keypoint is consistently occluded (NaN) — common with
     landing-leg knee, or any joint off-frame — gets `confidence = 1.0`
     (MAXIMUM), higher than a clean all-valid jump (~0.39). The report claims
     a near-certain phase detection on a degenerate input — false BEST.
  2. Downstream, `confidence` gates whether the element's metrics are
     displayed / scored / recommended. A 1.0 confidence on NaN input means
     garbage metrics (NaN-leaked from BM/BN/BP/.../BW) are presented as
     trustworthy.
  3. The CoM weighted sum means the bug triggers on NaN in ANY of the 17
     keypoints — wide blast radius, same as the CoM tranches.
  4. Existing tests miss it: `test_phase_detector*` feed all-valid keypoints.
     No test feeds a NaN keypoint through `detect_phases` and asserts the
     confidence is NOT inflated.
  5. The #454 arg-order trap (`min(1.0, nan) = 1.0`) is the inflation
     mechanism — the same class of bug as BP/BQ/BR GOE clamps.

The fix (NOT applied — repro only):
  - guard `confidence` against NaN: `if not np.isfinite(confidence):
    confidence = 0.0` before return; and/or
  - guard the inputs: `prominence = ...; if not np.isfinite(prominence):
    prominence = 0.0`; `if not np.isfinite(vy_std): velocity_confidence = 0.0`;
    `if not np.isfinite(threshold): threshold = 0.0` (parabolic path).
  - NaN-aware CoM in `calculate_com_trajectory` (mask NaN keypoints,
    renormalize masses) — fixes every CoM-based metric at once.
  - `min(1.0, nan)` → `min(1.0, np.nan_to_num(x))` or a NaN guard before the
    clamp (same fix as #454 across the clamps).

The correct contract: a NaN keypoint must NOT inflate `confidence` to 1.0.
The detector must degrade gracefully (NaN guard → 0.0 confidence, or the
finite value from the valid keypoints) — NOT report a near-certain detection
on NaN input.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN-poisoned input must report a confidence that is NOT inflated above the
all-valid baseline (and is finite), NOT 1.0. They FAIL because the NaN
collapses the detection chain and `min(1.0, nan) = 1.0` inflates the
confidence. After the fix: NaN is guarded and the confidence is finite and
≤ the all-valid baseline. The source-check test confirms the
`prominance = float(np.max(flight_com) - np.min(flight_com))` (not
nanmax/nanmin) line and the unguarded confidence clamp are present (root
cause locked).

Pure-Python (no GPU, no DB): `detect_phases` and `calculate_com_trajectory`
are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.phase_detector import PhaseDetector
from src.types import H36Key
from src.utils.geometry import calculate_com_trajectory


def _pose_seq(n: int = 30, nan_keypoint: str | None = None) -> np.ndarray:
    """A 30-frame 2D pose sequence with a mild flight arc (CoM dips during
    frames 8..21), so the all-valid detection has a finite, sub-1.0 confidence
    (~0.39) with real takeoff/peak/landing.

    When `nan_keypoint` is set, that keypoint is NaN across ALL frames — the
    occlusion case. `calculate_com_trajectory` is a weighted sum over all 17
    keypoints, so the CoM is all-NaN → the detection chain collapses
    (empty find_peaks, fallback peak=len//2, prominence=nan) → `min(1.0,
    nan) = 1.0` inflates confidence to 1.0.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.HEAD] = [0.0, 0.0]
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1]
        poses[f, H36Key.RSHOULDER] = [0.2, 0.1]
        poses[f, H36Key.LHIP] = [-0.1, 0.5]
        poses[f, H36Key.RHIP] = [0.1, 0.5]
        poses[f, H36Key.LKNEE] = [-0.1, 0.9]
        poses[f, H36Key.RKNEE] = [0.1, 0.9]
        poses[f, H36Key.LFOOT] = [-0.1, 1.0]
        poses[f, H36Key.RFOOT] = [0.1, 1.0]
    # Mild flight arc: CoM dips (rises in image coords, Y decreases) frames 8..21.
    for f in range(8, 22):
        poses[f, :, 1] -= 0.01 * (f - 8) * (21 - f) * 0.1
    if nan_keypoint:
        kp = {"rknee": H36Key.RKNEE, "rwrist": H36Key.RWRIST, "lfoot": H36Key.LFOOT}[nan_keypoint]
        poses[:, kp] = [np.nan, np.nan]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN keypoint must NOT inflate confidence above the all-valid
# baseline (graceful degradation), NOT report 1.0.
# --------------------------------------------------------------------------- #


def test_nan_knee_confidence_not_inflated_above_valid_repro():
    """CORRECT behavior: a jump sequence with ONE occluded keypoint (NaN across
    all frames) must report a confidence that is FINITE and NOT greater than
    the all-valid baseline — graceful degradation. It must NOT report
    `confidence = 1.0` (false BEST), which is HIGHER than the all-valid
    detection (~0.39) on a degenerate, NaN-poisoned input.

    RED now: `RKNEE` NaN across all frames → `calculate_com_trajectory` is a
    weighted sum over all 17 keypoints, so `com_y` is all-NaN → parabolic path
    `threshold = np.std(excursion) = nan`, `nan < 1e-6` False, `elevated` all
    NaN-compares False → `segments = []` → fallback `_detect_jump_phases_com_improved`
    → `vy = np.gradient(nan) = nan`, `vy_std = nan`, `find_peaks(height=nan)`
    empty → fallback peak=len//2, takeoff=peak-10, landing=peak+10, airtime≈0.67
    passes the 0.3 gate → `prominence = np.max(nan)-np.min(nan) = nan` →
    `min(1.0, nan/0.05) = 1.0` (#454 arg-order trap) → `velocity_confidence`
    also `min(1.0, nan) = 1.0` → `confidence = min(1.0, ...) = 1.0`. After the
    fix: NaN is guarded and confidence is finite, ≤ all-valid baseline.
    """
    det = PhaseDetector()

    # Baseline: all-valid mild arc → finite sub-1.0 confidence.
    r_valid = det.detect_phases(_pose_seq(30, None), 30.0, "waltz_jump")
    assert np.isfinite(r_valid.confidence) and 0.0 < r_valid.confidence < 1.0, (
        f"test fixture broken: all-valid mild-arc jump reported confidence "
        f"{r_valid.confidence}, expected finite in (0, 1). The fixture needs a "
        f"mild flight arc (`Y -= 0.01*(f-8)*(21-f)*0.1` on frames 8..21) so the "
        f"all-valid baseline is finite sub-1.0 — otherwise the NaN-vs-valid "
        f"contrast is meaningless."
    )

    # One occluded keypoint across all frames — NaN-poisoned input.
    r_nan = det.detect_phases(_pose_seq(30, "rknee"), 30.0, "waltz_jump")

    # CORRECT contract: NaN-poisoned confidence must be FINITE and NOT exceed
    # the all-valid baseline — graceful degradation, NOT false BEST 1.0.
    assert np.isfinite(r_nan.confidence), (
        f"BUG: PhaseDetector.detect_phases returned confidence={r_nan.confidence} "
        f"(non-finite) for a NaN-poisoned jump (RKNEE NaN across all frames). "
        f"Confidence must be finite (NaN guard / 0.0 sentinel)."
    )
    assert r_nan.confidence <= r_valid.confidence + 1e-6, (
        f"BUG: PhaseDetector.detect_phases returned confidence={r_nan.confidence} "
        f"for a NaN-poisoned jump (RKNEE NaN across all frames), which is GREATER "
        f"than the all-valid baseline ({r_valid.confidence:.4f}). A NaN keypoint "
        f"collapses the CoM (all-NaN), the parabolic path falls back to "
        f"`_detect_jump_phases_com_improved`, where `vy_std = nan`, find_peaks "
        f"return empty, the fallback peak=len//2 sets airtime≈0.67 (passes the "
        f"0.3 gate), `prominence = np.max(nan)-np.min(nan) = nan`, and "
        f"`min(1.0, nan/0.05) = 1.0` (#454 arg-order trap: `1.0 < nan` is False, "
        f"so the first arg wins) inflates confidence to 1.0 — a false BEST on a "
        f"degenerate input. (Sanity: all-valid = {r_valid.confidence:.4f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the bug triggers on NaN in ANY keypoint (CoM weighted sum),
# not just the knee — a NaN wrist also inflates to 1.0.
# --------------------------------------------------------------------------- #


def test_nan_wrist_confidence_not_inflated_to_one_repro():
    """CORRECT behavior: a jump with ONE occluded WRIST (NaN across all frames)
    must also NOT inflate confidence to 1.0. The CoM weighted sum includes
    the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist poisons the
    CoM the same way as a NaN knee. The bug has a wide blast radius — ANY of
    the 17 keypoints, same as the CoM tranches.

    RED now: `RWRIST` NaN → CoM all-NaN → same collapse → confidence=1.0.
    After the fix: graceful degradation on any occluded keypoint.
    """
    det = PhaseDetector()
    r_valid = det.detect_phases(_pose_seq(30, None), 30.0, "waltz_jump")
    r_nan = det.detect_phases(_pose_seq(30, "rwrist"), 30.0, "waltz_jump")

    assert np.isfinite(r_nan.confidence) and r_nan.confidence <= r_valid.confidence + 1e-6, (
        f"BUG: PhaseDetector.detect_phases returned confidence={r_nan.confidence} "
        f"for a NaN-poisoned jump (RWRIST NaN across all frames), > all-valid "
        f"baseline ({r_valid.confidence:.4f}) or non-finite. The CoM weighted sum "
        f"includes the arms (r_forearm = (RELBOW + RWRIST) / 2), so a NaN wrist "
        f"poisons the CoM the same way as a NaN knee. The bug has a wide blast "
        f"radius — ANY of the 17 keypoints. A fix that only guards the knee (or "
        f"only the legs) would leave the arm/head keypoints broken."
    )


# --------------------------------------------------------------------------- #
# Observable 3: occluding LKNEE vs RKNEE must give the same confidence —
# symmetric in which side is occluded.
# --------------------------------------------------------------------------- #


def test_nan_knee_confidence_is_symmetric_left_right_repro():
    """CORRECT behavior: occluding LKNEE vs RKNEE (NaN across all frames) must
    give the same confidence — both poison the CoM weighted sum identically
    (one NaN term). The detector must be symmetric in which side is occluded.

    RED now: both inflate to 1.0 (symmetric today, both false BEST). This is a
    regression guard that PASSES today only after the fix (both finite and
    equal, ≤ all-valid). It locks the symmetry contract so a fix that only
    handles one side does not pass.
    """
    det = PhaseDetector()
    r_valid = det.detect_phases(_pose_seq(30, None), 30.0, "waltz_jump")
    poses_r = _pose_seq(30, "rknee")
    poses_l = _pose_seq(30, None)
    poses_l[:, H36Key.LKNEE] = [np.nan, np.nan]

    r_right = det.detect_phases(poses_r, 30.0, "waltz_jump")
    r_left = det.detect_phases(poses_l, 30.0, "waltz_jump")

    # Both must be finite (the fix) AND equal — symmetric in which side.
    assert np.isfinite(r_right.confidence) and np.isfinite(r_left.confidence), (
        f"BUG (symmetry): occluding LKNEE/RKNEE gives non-finite confidence "
        f"({r_left.confidence} vs {r_right.confidence}). Both must be finite "
        f"(NaN guard) before the symmetry contract can be checked."
    )
    assert abs(r_right.confidence - r_left.confidence) < 1e-6, (
        f"BUG (symmetry): occluding LKNEE vs RKNEE gives different confidence "
        f"({r_left.confidence:.4f} vs {r_right.confidence:.4f}). Both poison the "
        f"CoM weighted sum identically (one NaN term) — the detector must be "
        f"symmetric in which side is occluded. A fix that only handles one side "
        f"would break this."
    )
    # And neither should exceed the all-valid baseline (graceful degradation).
    assert (
        r_right.confidence <= r_valid.confidence + 1e-6
        and r_left.confidence <= r_valid.confidence + 1e-6
    ), (
        f"BUG: occluded-keypoint confidence ({r_left.confidence:.4f} / "
        f"{r_right.confidence:.4f}) exceeds the all-valid baseline "
        f"({r_valid.confidence:.4f}) — false BEST on NaN input."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid jump still reports finite sub-1.0 confidence.
# --------------------------------------------------------------------------- #


def test_all_valid_confidence_unchanged_repro():
    """Regression guard: an all-valid jump must still report a finite, sub-1.0
    confidence. The fix (NaN guard / NaN-aware CoM / `min(1.0, nan_to_num(x))`)
    must not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    det = PhaseDetector()
    r = det.detect_phases(_pose_seq(30, None), 30.0, "waltz_jump")
    assert np.isfinite(r.confidence) and 0.0 < r.confidence < 1.0, (
        f"BUG (regression): all-valid jump reported confidence {r.confidence}, "
        f"expected finite in (0, 1). The no-NaN case must be unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — np.max - np.min prominence (not nanmax/
# nanmin) + unguarded confidence clamp + CoM plain weighted sum.
# --------------------------------------------------------------------------- #


def test_phase_detector_confidence_inflate_source_repro():
    """GREEN contract source check: the confidence-inflation bug is fixed in
    BOTH places.

    `_detect_jump_phases_com_improved` guards confidence against a non-finite
    prominence so the #454 `min(1.0, nan) = 1.0` trap cannot inflate confidence
    to 1.0 on degenerate input. `calculate_com_trajectory` masks NaN keypoints
    so an occluded joint cannot NaN-poison the CoM (the source-level fix that
    repairs every CoM-based metric).
    """
    src = inspect.getsource(PhaseDetector._detect_jump_phases_com_improved)
    # The prominence is still derived from the flight CoM (max - min).
    assert "prominence = float(np.max(flight_com) - np.min(flight_com))" in src, (
        "BUG: _detect_jump_phases_com_improved must still derive prominence from the flight CoM."
    )
    # The #454 arg-order trap is defused: a NaN guard on prominence forces
    # confidence to 0.0 instead of inflating via `min(1.0, nan) = 1.0`.
    assert "_math.isnan(prominence)" in src and "confidence = 0.0" in src, (
        "BUG: _detect_jump_phases_com_improved must guard prominence against "
        "NaN so the confidence clamp cannot inflate to 1.0 via "
        "`min(1.0, nan) = 1.0` (#454, #886)."
    )

    # And the CoM trajectory is NaN-aware — masking NaN keypoints so an
    # occluded joint cannot poison the CoM. Same root cause as
    # BM/BN/BP/BQ/BR/BS/BT/BV/BW.
    com_src = inspect.getsource(calculate_com_trajectory)
    assert "np.isfinite" in com_src, (
        "BUG: calculate_com_trajectory must mask NaN keypoints (np.isfinite) "
        "so a single occluded joint cannot NaN-poison the CoM and inflate "
        "phase-detection confidence."
    )
