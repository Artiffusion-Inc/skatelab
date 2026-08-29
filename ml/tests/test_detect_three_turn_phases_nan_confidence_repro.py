"""RED repro — `PhaseDetector.detect_three_turn_phases` inflates the
three-turn `confidence` to the 1.0 ceiling when a single NaN joint sits on a
flat-baseline frame OUTSIDE the turn.

Path (ml/src/analysis/phase_detector.py):
  `detect_three_turn_phases` (line 554):
    edge_ind = analyzer.compute_edge_indicator(poses, side='left')  # 580
    edge_derivative = np.gradient(edge_ind)                         # 584
    change_points, _ = find_peaks(np.abs(edge_derivative), ...)     # 587
    # peak detection is NaN-safe (find_peaks skips NaN frames) — turn_center
    # and phase boundaries remain CORRECT.
    max_change = float(np.max(np.abs(edge_derivative)))             # 620
    confidence = min(1.0, max_change / 0.5)                         # 621

`compute_edge_indicator` (metrics.py:1320) returns a NaN-bearing series when
ANY frame has NaN LHIP/LSHOULDER (occlusion — common in spins/crossovers/fast
rotation): `spine_vector = shoulder - hip` -> NaN, `arctan2(NaN)` -> NaN,
`np.clip(NaN, -1, 1)` -> NaN (clip does NOT mask NaN).

A single NaN LSHOULDER on a flat-baseline frame (e.g. frame 10, OUTSIDE the
turn at frame 30) -> `np.gradient(edge_ind)` propagates NaN to its 3-point
stencil neighbors -> `np.max(np.abs(edge_derivative))` over a NaN-bearing
array = NaN -> `confidence = min(1.0, NaN / 0.5) = min(1.0, NaN) = 1.0`
(Python `min` first-arg-wins on NaN, #454 arg-order trap). Confidence
collapses to the CEILING (false-HIGH) instead of the real finite edge-change
magnitude (~0.85).

Consequences:
  1. A caller gating `confidence >= 0.9` ACCEPTs a NaN-corrupted turn that
     should be rejected at ~0.85.
  2. Bug is silent: `np.gradient(NaN)=NaN`, `np.max(NaN-bearing)=NaN`,
     `min(1.0, NaN)=1.0` — no exception, only a RuntimeWarning. A structurally
     valid `PhaseDetectionResult` with `confidence=1.0` is returned.
  3. `detect_three_turn_phases` is the PUBLIC three-turn entry for every
     three-turn video.
  4. Sibling to #978/#924 (count_rotations NaN guard, same file) and the
     #454 `min(1.0, NaN) = 1.0` arg-order family. The fix mirrors the
     nan_to_num-before-min pattern.

The fix (NOT applied — repro only): guard `max_change` with `np.isfinite`
before the cap, OR use `np.nanmax` and fall back to 0.0 when no finite values
exist. NaN must NOT yield `confidence = 1.0`.

Contract: a NaN joint on ANY frame (flat-baseline or turn) must NOT inflate
`confidence` to 1.0. Confidence must reflect the real finite edge-change
magnitude (~0.85 for a clean turn), or degrade to 0.0 when the signal is
fully corrupted — never the 1.0 ceiling via `min(1.0, NaN)`.

Pure-Python (no GPU, no DB): `detect_three_turn_phases` and
`compute_edge_indicator` are pure-data functions over a poses array.
"""

import inspect

import numpy as np

from src.analysis.phase_detector import PhaseDetector
from src.types import H36Key


def _three_turn_poses(
    n: int = 60,
    nan_frame: int | None = None,
    delta: float = 0.12,
) -> np.ndarray:
    """A 60-frame 2D pose sequence with a sharp edge change at frame 30.

    LHIP is fixed at (0, 0.5); LSHOULDER starts at (0, 0) (flat, edge=0) and
    shifts to (2*delta, 0) across frames 29..30, producing a finite
    `max_change` (~0.43) and a finite sub-1.0 clean confidence (~0.85).

    When `nan_frame` is set, LSHOULDER on that single frame is NaN — the
    occlusion case. `compute_edge_indicator` propagates NaN through
    `spine_vector = shoulder - hip` -> `arctan2(NaN)` -> `clip(NaN)`, and
    `np.gradient` spreads the NaN to its 3-point stencil neighbors. The peak
    detection (`find_peaks`) still finds the real turn at frame ~30 (it skips
    NaN frames), but `np.max(np.abs(edge_derivative))` over the NaN-bearing
    array returns NaN -> `min(1.0, NaN) = 1.0` inflates confidence.
    """
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    for f in range(n):
        poses[f, H36Key.LHIP] = [0.0, 0.5]
        poses[f, H36Key.LSHOULDER] = [0.0, 0.0]
    # Edge change at frame 30: shoulder x goes 0 -> 2*delta over frames 29..30.
    for f in range(29, 31):
        poses[f, H36Key.LSHOULDER] = [delta * (f - 29) * 2, 0.0]
    for f in range(31, n):
        poses[f, H36Key.LSHOULDER] = [delta * 2, 0.0]
    if nan_frame is not None:
        poses[nan_frame, H36Key.LSHOULDER] = [np.nan, np.nan]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: a NaN joint on a flat-baseline frame must NOT inflate
# confidence to the 1.0 ceiling.
# --------------------------------------------------------------------------- #


def test_nan_joint_confidence_not_inflated_to_ceiling_repro():
    """CORRECT behavior: a three-turn with ONE NaN LSHOULDER on a flat-baseline
    frame (frame 10, OUTSIDE the turn at frame 30) must report a confidence
    that is FINITE and NOT 1.0 — the NaN must NOT collapse confidence to the
    1.0 ceiling via `min(1.0, NaN)`.

    RED now: NaN LSHOULDER on frame 10 -> `compute_edge_indicator` returns a
    NaN-bearing series -> `np.gradient` propagates NaN -> `np.max(np.abs(...))`
    = NaN -> `confidence = min(1.0, NaN / 0.5) = 1.0` (#454 arg-order trap).
    After the fix: NaN is guarded (isfinite / nan_to_num) and confidence
    reflects the real finite edge-change magnitude (~0.85), or degrades to 0.0
    — never 1.0.
    """
    det = PhaseDetector()
    r_valid = det.detect_three_turn_phases(_three_turn_poses(nan_frame=None), 30.0)
    assert np.isfinite(r_valid.confidence) and 0.0 < r_valid.confidence < 1.0, (
        f"test fixture broken: all-valid three-turn reported confidence "
        f"{r_valid.confidence}, expected finite in (0, 1). The fixture needs a "
        f"sharp edge change at frame 30 so the all-valid baseline is finite "
        f"sub-1.0 — otherwise the NaN-vs-valid contrast is meaningless."
    )

    r_nan = det.detect_three_turn_phases(_three_turn_poses(nan_frame=10), 30.0)

    assert np.isfinite(r_nan.confidence), (
        f"BUG: detect_three_turn_phases returned confidence={r_nan.confidence} "
        f"(non-finite) for a NaN-poisoned three-turn (LSHOULDER NaN on frame 10). "
        f"Confidence must be finite (NaN guard / 0.0 sentinel)."
    )
    assert r_nan.confidence != 1.0, (
        f"BUG: detect_three_turn_phases returned confidence={r_nan.confidence} "
        f"for a NaN-poisoned three-turn (LSHOULDER NaN on frame 10, a flat-"
        f"baseline frame OUTSIDE the turn). A single NaN joint makes "
        f"`np.max(np.abs(edge_derivative)) = NaN`, and `min(1.0, NaN / 0.5) = "
        f"1.0` (#454 arg-order trap: `1.0 < nan` is False, first arg wins) "
        f"inflates confidence to the 1.0 ceiling — a false BEST on a corrupted "
        f"signal. NaN must NOT yield 1.0. (Sanity: all-valid = "
        f"{r_valid.confidence:.4f}.)"
    )


# --------------------------------------------------------------------------- #
# Observable 2: the NaN joint must not inflate confidence ABOVE the all-valid
# baseline — graceful degradation, not false BEST.
# --------------------------------------------------------------------------- #


def test_nan_joint_confidence_not_above_valid_baseline_repro():
    """CORRECT behavior: a NaN-poisoned three-turn must report a confidence
    that is FINITE and NOT greater than the all-valid baseline. The real
    finite `max_change` (~0.43) gives ~0.85; a NaN joint must not push it
    higher (let alone to 1.0).

    RED now: NaN inflates confidence from ~0.85 to 1.0 — ABOVE the all-valid
    baseline. After the fix: NaN is masked out of the max (nanmax) or guarded
    to 0.0, so confidence is <= the all-valid baseline.
    """
    det = PhaseDetector()
    r_valid = det.detect_three_turn_phases(_three_turn_poses(nan_frame=None), 30.0)
    r_nan = det.detect_three_turn_phases(_three_turn_poses(nan_frame=10), 30.0)

    assert np.isfinite(r_nan.confidence) and r_nan.confidence <= r_valid.confidence + 1e-6, (
        f"BUG: detect_three_turn_phases returned confidence={r_nan.confidence} "
        f"for a NaN-poisoned three-turn (LSHOULDER NaN on frame 10), which is "
        f"GREATER than the all-valid baseline ({r_valid.confidence:.4f}) or "
        f"non-finite. A NaN joint on a flat-baseline frame must not inflate "
        f"confidence above the real finite edge-change magnitude. "
        f"`min(1.0, NaN) = 1.0` collapses to the ceiling (false BEST)."
    )


# --------------------------------------------------------------------------- #
# Observable 3: NaN on a turn frame (frame 30, the actual edge change) also
# must not inflate confidence to 1.0 — the guard must hold regardless of
# where the NaN lands.
# --------------------------------------------------------------------------- #


def test_nan_on_turn_frame_confidence_not_inflated_repro():
    """CORRECT behavior: a NaN LSHOULDER on the turn frame itself (frame 30,
    the edge change) must also NOT inflate confidence to 1.0. The guard must
    hold regardless of where the NaN lands — flat-baseline or turn frame.

    RED now: NaN on frame 30 -> `np.gradient` propagates NaN -> `np.max = NaN`
    -> `min(1.0, NaN) = 1.0`. After the fix: NaN guarded, confidence finite
    and not 1.0.
    """
    det = PhaseDetector()
    r_nan = det.detect_three_turn_phases(_three_turn_poses(nan_frame=30), 30.0)

    assert np.isfinite(r_nan.confidence) and r_nan.confidence != 1.0, (
        f"BUG: detect_three_turn_phases returned confidence={r_nan.confidence} "
        f"for a three-turn with LSHOULDER NaN on the turn frame (frame 30). The "
        f"NaN must not inflate confidence to the 1.0 ceiling regardless of "
        f"where it lands. `min(1.0, NaN) = 1.0` is the inflation mechanism."
    )


# --------------------------------------------------------------------------- #
# Regression guard: all-valid three-turn still reports finite sub-1.0
# confidence — the fix must not change the no-NaN case.
# --------------------------------------------------------------------------- #


def test_all_valid_three_turn_confidence_unchanged_repro():
    """Regression guard: an all-valid three-turn must still report a finite,
    sub-1.0 confidence. The fix (NaN guard / nan_to_num before the cap) must
    not change the no-NaN case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    det = PhaseDetector()
    r = det.detect_three_turn_phases(_three_turn_poses(nan_frame=None), 30.0)
    assert np.isfinite(r.confidence) and 0.0 < r.confidence < 1.0, (
        f"BUG (regression): all-valid three-turn reported confidence "
        f"{r.confidence}, expected finite in (0, 1). The no-NaN case must be "
        f"unchanged by the fix."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded `np.max` + `min(1.0, ...)` cap,
# and a NaN guard (isfinite / nan_to_num / nanmax) is present before the cap.
# --------------------------------------------------------------------------- #


def test_detect_three_turn_phases_nan_guard_source_repro():
    """GREEN contract source check: the confidence-inflation bug is fixed at
    the cap site. The `np.max(np.abs(edge_derivative))` line and the
    `min(1.0, max_change / 0.5)` cap are present, AND a NaN guard
    (`np.isfinite` / `np.nan_to_num` / `np.nanmax`) is applied before the cap
    so a NaN-bearing `edge_derivative` cannot yield `confidence = 1.0` via
    `min(1.0, NaN)`.
    """
    src = inspect.getsource(PhaseDetector.detect_three_turn_phases)
    # Root cause line present (regression guard for the cap site).
    assert "min(1.0, max_change / 0.5)" in src, (
        "BUG: detect_three_turn_phases must still cap confidence with `min(1.0, max_change / 0.5)`."
    )
    # The #454 arg-order trap is defused: a NaN guard is present before the cap.
    assert "np.isfinite" in src or "np.nan_to_num" in src or "np.nanmax" in src, (
        "BUG: detect_three_turn_phases must guard max_change against NaN "
        "(np.isfinite / np.nan_to_num / np.nanmax) before the "
        "`min(1.0, max_change / 0.5)` cap, so a NaN-bearing edge_derivative "
        "cannot inflate confidence to 1.0 via `min(1.0, NaN) = 1.0` (#454, "
        "#1007)."
    )
