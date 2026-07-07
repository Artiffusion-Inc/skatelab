"""RED repro — Issue #1301: seg_excursion NaN silent no-detection.

Bug
---
`ml/src/analysis/phase_detector.py` (parabolic branch) computes the
segment score as `score = r_squared * seg_excursion`, where:

    seg_excursion = float(baseline[peak_frame] - com_smooth[peak_frame])

If `baseline[peak_frame]` or `com_smooth[peak_frame]` is NaN, seg_excursion
propagates NaN. Then:

    if score > best_score:    # best_score = -1.0
        # NaN > -1.0 is False (NaN-cmp rule)
        # candidate silently NOT selected
        # best_score stays at -1.0
        # best_result stays None
        # falls through to fallback "no good parabola" path

This produces silent no-detection: the user gets placeholder phase
boundaries even though a real (NaN-corrupt) candidate was found.
Downstream metrics compute on wrong segments and emit a wrong
biomechanical report.

Root cause: no `math.isfinite(seg_excursion)` guard before the
`if score > best_score` comparison.

Fix (per issue): add `math.isfinite(seg_excursion)` (or
`np.isfinite(baseline[peak_frame]) and np.isfinite(com_smooth[peak_frame])`)
guard before the comparison, skipping the corrupt candidate.

These tests are written for the POST-FIX contract and FAIL on master
(RED). The fix is to add the `math.isfinite(...)` guard inside
`_detect_jump_phases_parabolic` before `if score > best_score:`.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from src.analysis.phase_detector import PhaseDetector

# CoM mass weights in calculate_com_trajectory sum to 1.3, so every
# keypoint Y = target / 1.3 yields CoM == target.
_COM_MASS_SUM = 0.081 + 0.497 + 0.050 * 4 + 0.100 * 2 + 0.161 * 2  # = 1.3


def _poses_from_com(target_com: np.ndarray, baseline_y: float = 0.5) -> np.ndarray:
    """Build (N, 17, 2) poses whose calculate_com_trajectory == target_com."""
    n = len(target_com)
    poses = np.full((n, 17, 2), baseline_y, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = (target_com / _COM_MASS_SUM).astype(np.float32)[:, None]
    return poses


# ---------------------------------------------------------------------------
# Test 1: SOURCE CHECK — `_detect_jump_phases_parabolic` must guard
# `seg_excursion` with `math.isfinite(...)` (or equivalent) before the
# `if score > best_score` comparison. FAILS on master (RED).
# ---------------------------------------------------------------------------


def test_source_has_isfinite_guard_on_seg_excursion():
    """Post-fix source contract: a `math.isfinite(seg_excursion)` (or
    equivalent) guard must appear inside the
    `_detect_jump_phases_parabolic` function, BEFORE the
    `if score > best_score` comparison that selects the winning
    segment. Pre-fix: no such guard → NaN seg_excursion → score=NaN →
    `NaN > -1.0` is False → candidate silently rejected → silent
    no-detection. Post-fix: corrupt candidate is skipped, real
    candidates still selected.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = src_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _detect_jump_phases_parabolic.*?(?=def _scan_to_baseline|def detect_three_turn_phases|def detect_phases|def detect_jump_phases|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate _detect_jump_phases_parabolic in source"
    body = m.group(0)

    # The `seg_excursion = float(baseline[peak_frame] - com_smooth[peak_frame])`
    # assignment must exist.
    assert "seg_excursion" in body, "Expected seg_excursion reference in parabolic"
    assert "score = r_squared * seg_excursion" in body, "Expected score computation"

    # The fix idiom MUST be present: a `math.isfinite(...)` or
    # `np.isfinite(...)` guard on seg_excursion (or its components)
    # before the `if score > best_score` block.
    has_guard = bool(
        re.search(
            r"(?:math|np)\.isfinite\(\s*(?:seg_excursion|baseline\[peak_frame\]|com_smooth\[peak_frame\]|baseline\[peak_frame\]\s*-\s*com_smooth\[peak_frame\])\s*\)",
            body,
        )
    )
    assert has_guard, (
        "#1301 unfixed: `_detect_jump_phases_parabolic` has no "
        "`math.isfinite(...)` guard on `seg_excursion` (or its "
        "components) before the `if score > best_score` comparison. "
        "NaN seg_excursion → score=NaN → `NaN > -1.0` is False → "
        "candidate silently rejected → silent no-detection. Add a "
        "guard like `if not math.isfinite(seg_excursion): continue` "
        "before the `if score > best_score:` block."
    )


# ---------------------------------------------------------------------------
# Test 2: BEHAVIORAL — when seg_excursion is NaN, the candidate must
# be skipped (not silently selected via the NaN-cmp rule).
#
# We force NaN by monkey-patching `calculate_com_trajectory` to inject
# a NaN spike at one mid-trajectory frame. After the call, the result
# (if any) must have a finite confidence — NaN must not leak through
# to the final score.
# ---------------------------------------------------------------------------


def test_nan_seg_excursion_does_not_silently_propagate():
    """Force `seg_excursion` to be NaN by monkey-patching
    `calculate_com_trajectory` to inject a NaN spike at one mid-arc
    frame. Pre-fix: the parabolic branch produces a NaN seg_excursion
    → score=NaN → `NaN > -1.0` is False → fallback path → no
    detection. Post-fix: NaN-candidate is skipped, then either
    another candidate wins or fallback returns a clean result. In
    either case, the returned `result.confidence` MUST be finite.
    """
    n_frames = 80
    # Build a clean jump trajectory (low CoM Y at peak).
    target_com = np.full(n_frames, 0.5, dtype=np.float32)
    target_com[30:50] = 0.3  # jump arc — CoM drops in image coords
    poses = _poses_from_com(target_com)

    det = PhaseDetector()

    from src.analysis import phase_detector as pd_mod

    original_calc = pd_mod.calculate_com_trajectory

    def _calc_with_nan(poses_arg, **kwargs):
        com = original_calc(poses_arg, **kwargs)
        # Inject NaN at one mid-trajectory frame (within the jump arc).
        com[40] = float("nan")
        return com

    with mock.patch.object(pd_mod, "calculate_com_trajectory", _calc_with_nan):
        # Must not raise. Pre-fix and post-fix both pass this assertion.
        result = det._detect_jump_phases_parabolic(poses, 30.0)

    # Post-fix contract: the function must not silently propagate
    # NaN into best_score. If a result is returned, its confidence
    # must be finite (not NaN/inf).
    if result is not None:
        assert math.isfinite(result.confidence), (
            f"#1301: result.confidence is not finite ({result.confidence!r}). "
            f"NaN seg_excursion leaked through to the final score."
        )


# ---------------------------------------------------------------------------
# Test 3: SOURCE CHECK — the seg_excursion computation must be
# guarded, not just the score. Pre-fix computes
# `seg_excursion = float(baseline[peak_frame] - com_smooth[peak_frame])`
# at line 552, then `score = r_squared * seg_excursion`, then
# `if score > best_score:`. The guard must intervene between
# computation and the if-statement. FAILS on master (RED).
# ---------------------------------------------------------------------------


def test_source_seg_excursion_guard_is_between_compute_and_cmp():
    """Post-fix: the order in the source must be:
        1. `seg_excursion = float(baseline[peak_frame] - com_smooth[peak_frame])`
        2. `if not isfinite(seg_excursion): continue`  # the guard
        3. `score = r_squared * seg_excursion`
        4. `if score > best_score:`

    Pre-fix (master) has no step 2: NaN seg_excursion flows directly
    to step 3, then NaN score flows to step 4, where NaN-cmp silently
    fails. Post-fix must insert step 2.

    FAILS on master (no isfinite(seg_excursion) anywhere between the
    compute and the cmp lines). PASSES once the guard is added.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = src_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _detect_jump_phases_parabolic.*?(?=def _scan_to_baseline|def detect_three_turn_phases|def detect_phases|def detect_jump_phases|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate _detect_jump_phases_parabolic in source"
    body = m.group(0)

    # Locate the seg_excursion compute line and the score-cmp line.
    seg_match = re.search(
        r"seg_excursion\s*=\s*float\(\s*baseline\[peak_frame\]\s*-\s*com_smooth\[peak_frame\]\s*\)",
        body,
    )
    cmp_match = re.search(r"if\s+score\s*>\s*best_score", body)
    assert seg_match, "seg_excursion assignment not found in source"
    assert cmp_match, "if score > best_score line not found in source"

    seg_pos = seg_match.start()
    cmp_pos = cmp_match.start()
    between = body[seg_pos:cmp_pos]

    # Between the compute and the cmp, there MUST be at least one
    # isfinite(...) call on seg_excursion or its components.
    has_guard = bool(
        re.search(
            r"(?:math|np)\.isfinite\(\s*(?:seg_excursion|baseline\[peak_frame\]|com_smooth\[peak_frame\])\s*\)",
            between,
        )
    )
    assert has_guard, (
        "#1301 unfixed: no `math.isfinite(seg_excursion)` (or component) "
        "guard between the seg_excursion assignment and the "
        "`if score > best_score` comparison. NaN seg_excursion → "
        "NaN score → `NaN > -1.0` is False → candidate silently "
        "rejected. Add `if not math.isfinite(seg_excursion): continue` "
        "(or guard the inputs `baseline[peak_frame]` / `com_smooth[peak_frame]`)."
    )


# ---------------------------------------------------------------------------
# Test 4: REGRESSION — valid input (no NaN) still produces a phase
# result. PASSES on master; serves as a no-regression guard for the fix.
# ---------------------------------------------------------------------------


def test_valid_input_still_detects_phases():
    """Sanity: valid pose sequence must detect phases without raising.
    Regression guard: the fix must not break the typical case.
    """
    n_frames = 80
    target_com = np.full(n_frames, 0.5, dtype=np.float32)
    target_com[30:50] = 0.3  # jump arc
    poses = _poses_from_com(target_com)

    det = PhaseDetector()
    result = det._detect_jump_phases_parabolic(poses, 30.0)
    assert result is not None
    assert 0.0 <= result.confidence <= 1.0
    assert result.phases is not None
    assert result.phases.takeoff < result.phases.peak < result.phases.landing


# ---------------------------------------------------------------------------
# Test 5: STRUCTURAL — the seg_excursion guard must use a
# skip-iteration pattern (continue) rather than silently
# nan_to_num-ing the value to 0.0, which would corrupt scoring
# downstream. Verify by checking that the guard uses a `continue`
# or `if not ... : continue` pattern.
# ---------------------------------------------------------------------------


def test_seg_excursion_guard_skips_candidate():
    """Post-fix: the isfinite guard around seg_excursion must skip
    the corrupt candidate (continue), not silently coerce NaN to 0.0
    via np.nan_to_num (which would still pass the > -1.0 cmp and
    pollute the score with a fake-0 excursion).

    FAILS on master (no guard at all). PASSES once the guard is
    added with a `continue` skip pattern.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = src_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _detect_jump_phases_parabolic.*?(?=def _scan_to_baseline|def detect_three_turn_phases|def detect_phases|def detect_jump_phases|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate _detect_jump_phases_parabolic in source"
    body = m.group(0)

    # The guard must be a `continue`-style skip. Look for an isfinite
    # check on seg_excursion / peak_frame values followed (within ~80 chars)
    # by a `continue` keyword.
    guard_pattern = re.compile(
        r"(?:math|np)\.isfinite\(\s*(?:seg_excursion|baseline\[peak_frame\]|com_smooth\[peak_frame\])\s*\)"
        r"[\s\S]{0,80}?\bcontinue\b"
    )
    assert guard_pattern.search(body), (
        "#1301 unfixed: the seg_excursion isfinite guard is missing or "
        "does not `continue` to skip the corrupt candidate. NaN "
        "seg_excursion → NaN score → `NaN > -1.0` is False → silent "
        "no-detection. Add `if not math.isfinite(seg_excursion): continue` "
        "between the seg_excursion compute and the `if score > best_score:` "
        "comparison."
    )
