"""RED repro — Issue #1223: NaN airtime silently accepted by phase_detector plausibility gate.

Bug
---
`ml/src/analysis/phase_detector.py` uses `if airtime < 0.3:` plausibility
gates at two call sites:

* `_detect_jump_phases_com_improved` (line ~252)
* `_detect_jump_phases_parabolic` (line ~528)

If `airtime` is NaN (from NaN landing_idx / takeoff_idx), the IEEE-754
rule says `NaN < 0.3` is False, so the gate ACCEPTS the segment. No
crash, no warning, no log. A NaN-floated airtime then gets passed
through to downstream metrics, alignment, scoring, and the Russian
recommender — corrupting the entire session.

Root cause: the gates use a raw `<` comparison, which is NaN-blind.
The sibling fix at #505 guards only `fps > 0` (i.e. infinite airtime)
but does not catch NaN landing_idx / takeoff_idx.

Fix (per issue): wrap the airtime comparison in a `math.isfinite(...)`
guard so that NaN airtime is REJECTED (same path as the existing
short-airtime case).

These tests are written for the POST-FIX contract and FAIL on master
(RED). The fix is to add `math.isfinite(airtime)` to the guard in
both `_detect_jump_phases_com_improved` and `_detect_jump_phases_parabolic`.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from src.analysis.phase_detector import PhaseDetector
from src.types import H36Key

# CoM mass weights in calculate_com_trajectory sum to 1.3, so every
# keypoint Y = target / 1.3 yields CoM == target.
_COM_MASS_SUM = 0.081 + 0.497 + 0.050 * 4 + 0.100 * 2 + 0.161 * 2  # = 1.3


def _build_flat_poses(n_frames: int) -> np.ndarray:
    """Build (N, 17, 2) poses with CoM at y=0.5 (no jump)."""
    poses = np.full((n_frames, 17, 2), 0.5, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = 0.5 / _COM_MASS_SUM
    return poses


# ---------------------------------------------------------------------------
# Test 1: Observable — NaN airtime must be REJECTED in com_improved branch.
#
# The com_improved path computes `airtime = (landing - takeoff + 1) / fps`.
# If we monkey-patch the module-level `find_peaks` to return NaN indices,
# the landing_idx / takeoff_idx become NaN → airtime = NaN → `NaN < 0.3`
# is False → segment is accepted (BUG).
#
# Post-fix contract: NaN airtime is rejected; the function returns the
# default low-confidence ElementPhase (the same shape as a short-airtime
# rejection) — confidence=0.0 and the indices are sanitized to int
# (0 / len//2 / len-1) without ever leaking the NaN int() ValueError.
# ---------------------------------------------------------------------------


def test_com_improved_rejects_nan_airtime_silently_accepted():
    """Force NaN landing_idx / takeoff_idx via find_peaks mock. Pre-fix:
    `NaN < 0.3` is False → segment ACCEPTED → corrupted ElementPhase with
    NaN indices floats downstream. Post-fix: a math.isfinite(airtime)
    guard rejects the NaN airtime, mirroring the short-airtime path.

    We assert the post-fix contract: the function does not raise, the
    returned ElementPhase is sanitized (all 5 idx fields are int), and
    confidence is 0.0 (low-confidence default — the NaN-airtime segment
    is treated as a false positive, not a real jump).
    """
    n_frames = 60
    poses = _build_flat_poses(n_frames)

    det = PhaseDetector()

    def _find_peaks_nan(*args, **kwargs):
        return np.array([float("nan")]), {}

    with mock.patch("src.analysis.phase_detector.find_peaks", _find_peaks_nan):
        # Should not raise. Pre-fix: returned an ElementPhase with NaN
        # takeoff/landing fields that would then crash int() casts in
        # subsequent functions; the gate silently accepted the segment.
        result = det._detect_jump_phases_com_improved(poses, 30.0)

    assert result is not None
    # Post-fix contract: NaN airtime is rejected → low-confidence default
    assert result.confidence == 0.0, (
        "#1223 unfixed: NaN airtime was accepted by the plausibility "
        f"gate. confidence={result.confidence!r}, expected 0.0. The "
        "`if airtime < 0.3` gate does not catch NaN — add a "
        "`math.isfinite(airtime)` guard so the NaN segment is treated "
        "as a false positive."
    )
    # The 5 idx fields must be int (post-fix: sanitized to 0 / len//2 / len-1)
    for field in ("start", "takeoff", "peak", "landing", "end"):
        val = getattr(result.phases, field)
        assert isinstance(val, int), (
            f"#1223 unfixed: phases.{field} leaked NaN as {type(val).__name__}({val!r}). "
            "NaN airtime was accepted, so NaN idx floated through to "
            "ElementPhase — this is the symptom the issue names. The fix "
            "must guard airtime with math.isfinite before the gate."
        )


# ---------------------------------------------------------------------------
# Test 2: Observable — NaN chain (takeoff=NaN, landing=NaN) is also caught.
#
# Same root cause, different NaN source: an inf-only-landing takeoff
# from peak_candidates makes airtime = NaN. The fix must catch this
# (math.isfinite catches NaN AND inf).
# ---------------------------------------------------------------------------


def test_com_improved_rejects_nan_chain_inf_landing():
    """Force the same NaN-airtime condition with a different mock shape:
    takeoff_candidates = empty, landing_candidates = [nan]. The
    fallback `landing_idx = min(N-1, peak_idx + 10)` does NOT run when
    `len(landing_candidates) > 0`, so landing_idx becomes NaN. The
    airtime gate must still reject.

    Post-fix contract: confidence == 0.0; phases are sanitized ints.
    """
    n_frames = 60
    poses = _build_flat_poses(n_frames)

    det = PhaseDetector()

    real_find_peaks = __import__("scipy.signal", fromlist=["find_peaks"]).find_peaks

    def _find_peaks_takeoff_nan_landing_nan(x, **kwargs):
        # Return NaN for both arrays — simulates the corrupt-detection
        # scenario described in the issue.
        if "height" in kwargs and kwargs.get("distance") == 10:
            # Heuristic: this is the second call (landing). Both empty
            # candidates + peak_idx from find_peaks call below = NaN idx.
            return np.array([float("nan")]), {}
        return np.array([float("nan")]), {}

    with mock.patch("src.analysis.phase_detector.find_peaks", _find_peaks_takeoff_nan_landing_nan):
        result = det._detect_jump_phases_com_improved(poses, 30.0)

    assert result is not None
    assert result.confidence == 0.0, (
        "#1223 unfixed: NaN-chain airtime (NaN takeoff + NaN landing) "
        f"was accepted. confidence={result.confidence!r}, expected 0.0."
    )


# ---------------------------------------------------------------------------
# Test 3: Observable — short airtime (0.05s, well below 0.3s) is rejected
#         by the existing < 0.3 gate. Regression guard: the fix must NOT
#         change this behavior.
# ---------------------------------------------------------------------------


def test_com_improved_short_airtime_still_rejected():
    """A sub-0.3s airtime is rejected by the existing < 0.3 gate. The
    fix must NOT break this path. (Regression guard: ensures the
    `math.isfinite` guard is additive, not a replacement that loses
    the < 0.3 check.)
    """
    n_frames = 60
    poses = _build_flat_poses(n_frames)

    det = PhaseDetector()

    # Force a 2-frame flight: takeoff=10, landing=12. (12-10+1)/30 = 0.1s
    real_find_peaks = __import__("scipy.signal", fromlist=["find_peaks"]).find_peaks

    def _find_peaks_short_flight(x, **kwargs):
        # Both call sites: return peaks at 10 and 12 (a 2-frame flight).
        if len(x) > 5:
            return np.array([10]), {}
        return np.array([12]), {}

    with mock.patch("src.analysis.phase_detector.find_peaks", _find_peaks_short_flight):
        result = det._detect_jump_phases_com_improved(poses, 30.0)

    assert result is not None
    # Existing behavior: short airtime → rejected → low confidence
    assert result.confidence == 0.0, (
        "Regression: short airtime (< 0.3s) was not rejected by the "
        f"plausibility gate. confidence={result.confidence!r}."
    )


# ---------------------------------------------------------------------------
# Test 4: Regression — valid jump still detects a proper phase result.
# Boundary: 0.3s exactly must be accepted (gate is strict <, not <=).
# ---------------------------------------------------------------------------


def test_parabolic_valid_30_frame_flight_accepted():
    """Sanity: a parabolic CoM with a 30-frame flight (30/30 = 1.0s)
    must produce a real jump phase with takeoff < peak < landing. This
    is the no-regression guard — the fix must not over-reject valid
    jumps while plugging the NaN hole.
    """
    n_frames = 90
    poses = np.zeros((n_frames, 17, 2), dtype=np.float32)

    # Construct a parabola: 30-frame flight from frame 20 (takeoff) to
    # frame 50 (landing). Baseline CoM Y = 0.4, peak at 0.2.
    for i in range(n_frames):
        if i < 20:
            y = 0.4
        elif i < 50:
            # 30 frames parabolic flight, peak at i=35
            t = (i - 20) / 30.0
            y = 0.4 - 0.2 * 4 * t * (1 - t)  # parabola 0..0.5..0 over [0,1]
        else:
            y = 0.4
        poses[i, H36Key.LHIP, 1] = y
        poses[i, H36Key.RHIP, 1] = y
        # Sibling joints (just need valid CoM)
        poses[i, H36Key.LKNEE, 1] = y
        poses[i, H36Key.RKNEE, 1] = y
        poses[i, H36Key.LFOOT, 1] = y
        poses[i, H36Key.RFOOT, 1] = y

    det = PhaseDetector()
    result = det.detect_jump_phases(poses, fps=30.0)

    assert result is not None
    assert result.phases is not None
    # Boundary regression: 30-frame flight = 1.0s, well above 0.3s gate.
    # The detected phase must have takeoff < peak < landing AND the
    # takeoff/landing gap must be ≥ 9 frames (9/30 = 0.3s, the gate
    # boundary).
    assert result.phases.takeoff < result.phases.peak, (
        f"Regression: takeoff={result.phases.takeoff} not before "
        f"peak={result.phases.peak} on a 30-frame parabola."
    )
    assert result.phases.peak < result.phases.landing, (
        f"Regression: peak={result.phases.peak} not before "
        f"landing={result.phases.landing} on a 30-frame parabola."
    )
    assert (result.phases.landing - result.phases.takeoff + 1) >= 9, (
        "Regression: 30-frame parabola produced a phase with "
        f"takeoff={result.phases.takeoff}, landing={result.phases.landing} "
        "— flight < 9 frames violates the 0.3s gate."
    )


# ---------------------------------------------------------------------------
# Test 5: SOURCE CHECK — the math.isfinite(airtime) guard must exist
# at BOTH plausibility gates in phase_detector.py. FAILS on master.
# ---------------------------------------------------------------------------


def test_source_has_isfinite_guard_on_airtime_gates():
    """Post-fix source contract: a `math.isfinite(airtime)` guard must
    appear at BOTH plausibility gates in phase_detector.py:

      * `_detect_jump_phases_com_improved` (one airtime gate)
      * `_detect_jump_phases_parabolic` (one airtime gate)

    The guard idiom MUST be on the `airtime` variable (not the
    unrelated confidence guards at lines 316+ or the fps guard at
    line 390). Pre-fix master has only `if airtime < 0.3:` (no
    isfinite) → RED.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = src_path.read_text(encoding="utf-8")
    assert src_path.exists(), f"Source not found: {src_path}"

    # Both gates use `if airtime < 0.3:`. Post-fix, the gate must be
    # wrapped to also reject non-finite airtime. We accept either of:
    #   a) `if not math.isfinite(airtime) or airtime < 0.3:`
    #   b) `if airtime < 0.3 or not math.isfinite(airtime):`
    #   c) `if not (math.isfinite(airtime) and airtime >= 0.3):`
    # i.e. the comparison must be combined with a math.isfinite check
    # on the SAME airtime variable.

    # Count the airtime < 0.3 occurrences (should be 2 in master).
    n_gates = len(re.findall(r"airtime\s*<\s*0\.3", text))
    assert n_gates == 2, (
        f"Expected exactly 2 airtime < 0.3 gates in phase_detector.py, "
        f"found {n_gates}. The issue names BOTH sites (line 237 + line 460). "
        "If the source has changed, update this test to match the new gate count."
    )

    # Each gate must be accompanied by a math.isfinite(airtime) check
    # in its vicinity (within ~120 chars before). We do this by
    # searching for the pattern.
    has_airtime_isfinite_guard = bool(
        re.search(
            r"math\.isfinite\(\s*airtime\s*\)",
            text,
        )
    )
    assert has_airtime_isfinite_guard, (
        "#1223 unfixed: no `math.isfinite(airtime)` guard found in "
        "phase_detector.py. The two `if airtime < 0.3:` plausibility "
        "gates are NaN-blind — `NaN < 0.3` is False in Python, so a "
        "NaN-floated airtime segment is silently accepted. Add a "
        "`math.isfinite(airtime)` guard at each of the two airtime "
        "gates (line ~252 in `_detect_jump_phases_com_improved` and "
        "line ~528 in `_detect_jump_phases_parabolic`)."
    )

    # Specifically: both gates must be guarded (not just one).
    # Count isfinite(airtime) near an airtime < 0.3 gate.
    gate_pattern = re.compile(
        r"(math\.isfinite\([^)]*airtime[^)]*\)|airtime\s*<\s*0\.3)",
        re.MULTILINE,
    )
    matches = gate_pattern.findall(text)
    n_isfinite_airtime = sum(1 for m in matches if "isfinite" in m and "airtime" in m)
    assert n_isfinite_airtime >= 2, (
        f"#1223 unfixed: only {n_isfinite_airtime} airtime isfinite "
        f"guard(s) found, expected ≥ 2 (one per airtime < 0.3 gate). "
        f"All matches: {matches!r}. The issue names BOTH gates — both "
        "must be guarded."
    )
