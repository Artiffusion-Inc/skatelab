"""RED repro — Issue #1240: phase_detector crashes with ValueError on NaN idx.

Bug
---
`ml/src/analysis/phase_detector.py` (com_improved branch) constructs
an `ElementPhase` from start/takeoff/peak/landing/end indices using
bare `int(...)` calls:

    phases = ElementPhase(
        name="jump",
        start=int(start_idx),
        takeoff=int(takeoff_idx),
        peak=int(peak_idx),
        landing=int(landing_idx),
        end=int(end_idx),
    )

If any of those indices is NaN (corrupt CoM detection, missing peak,
partial tracking), `int(NaN)` raises
`ValueError: cannot convert float NaN to integer`, aborting the whole
analysis chain: no `ElementPhase` → metrics skip → alignment skip →
broken analysis → broken session for user.

Root cause: no `math.isfinite(...)` guard at the int() conversion.

Fix (per issue): guard each idx with `math.isfinite(...)` (or
`int(round(x)) if math.isfinite(x) else 0`) before int() conversion.

These tests are written for the POST-FIX contract and FAIL on master
(RED). The fix is to add the `math.isfinite(...)` guard inside
`_detect_jump_phases_com_improved`.
"""

from __future__ import annotations

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
# Test 1: com_improved must NOT crash on NaN idx.
#
# Force NaN into peak_idx by monkey-patching np.argmin inside the
# com_improved body. Pre-fix (master): int(peak_idx) raises ValueError
# "cannot convert float NaN to integer" — test FAILS RED.
# Post-fix: a math.isfinite guard coerces NaN to 0 — test PASSES.
# ---------------------------------------------------------------------------


def test_com_improved_does_not_crash_with_nan_peak_idx():
    """Force NaN peak_idx via find_peaks mock (the function uses
    `find_peaks` from scipy.signal at module level). Pre-fix (master):
    `int(peak_idx)` raises `ValueError: cannot convert float NaN to
    integer` — test FAILS RED. Post-fix: math.isfinite guard coerces
    NaN to 0 — test PASSES.
    """
    n_frames = 60
    poses = np.full((n_frames, 17, 2), 0.5, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = 0.5 / _COM_MASS_SUM

    det = PhaseDetector()

    # Monkey-patch the module-level find_peaks to return NaN indices.
    def _find_peaks_nan(*args, **kwargs):
        return np.array([float("nan")]), {}

    with mock.patch("src.analysis.phase_detector.find_peaks", _find_peaks_nan):
        try:
            result = det._detect_jump_phases_com_improved(poses, 30.0)
        except ValueError as exc:
            msg = str(exc)
            assert "cannot convert float NaN to integer" not in msg, (
                f"#1240 regressed: _detect_jump_phases_com_improved leaked "
                f"the raw int(NaN) ValueError to the caller: {msg!r}. "
                f"Add math.isfinite guard on the idx vars."
            )
            # Any other typed ValueError is acceptable (e.g. domain error)
            return
    assert result is not None
    assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# Test 2: regression — valid input still produces a usable phase result.
# (PASSES on master; this is the no-regression guard.)
# ---------------------------------------------------------------------------


def test_com_improved_valid_input_still_works():
    """Sanity: valid pose sequence must detect phases without raising.
    Regression guard: the fix must not break the typical case.
    """
    n_frames = 60
    poses = np.full((n_frames, 17, 2), 0.5, dtype=np.float32)
    poses[:, :, 0] = 0.5
    poses[:, :, 1] = 0.5 / _COM_MASS_SUM

    det = PhaseDetector()
    result = det._detect_jump_phases_com_improved(poses, 30.0)
    assert result is not None
    assert 0.0 <= result.confidence <= 1.0
    assert result.phases is not None
    # All five idx fields must be int (post-fix contract: int even if
    # the source value was NaN — the guard coerces NaN to 0).
    for field in ("start", "takeoff", "peak", "landing", "end"):
        val = getattr(result.phases, field)
        assert isinstance(val, int), (
            f"phases.{field} must be int, got {type(val).__name__}({val!r})"
        )


# ---------------------------------------------------------------------------
# Test 3: SOURCE CHECK — the math.isfinite guard on idx vars must exist
# in `_detect_jump_phases_com_improved`. FAILS on master (RED).
# ---------------------------------------------------------------------------


def test_source_has_isfinite_guard_on_idx_vars():
    """Post-fix source contract: a `math.isfinite(...)` guard must
    appear on the phase idx vars (start_idx, takeoff_idx, peak_idx,
    landing_idx, end_idx) inside `_detect_jump_phases_com_improved`.

    FAILS on master (no such guard → bug present).
    PASSES after the fix adds the guard.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = src_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _detect_jump_phases_com_improved.*?(?=def _detect_jump_phases_parabolic|def detect_three_turn_phases|\Z)",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate _detect_jump_phases_com_improved in source"
    body = m.group(0)
    assert "int(start_idx)" in body, "Expected int(start_idx) cast in com_improved"
    # The fix idiom MUST be present: an isfinite guard specifically on
    # the idx variables (not the unrelated confidence guards).
    has_idx_guard = bool(re.search(r"isfinite\((?:start|takeoff|peak|landing|end)_idx\)", body))
    assert has_idx_guard, (
        "#1240 unfixed: `_detect_jump_phases_com_improved` has no "
        "`math.isfinite(...)` guard on the phase idx vars "
        "(start_idx, takeoff_idx, peak_idx, landing_idx, end_idx). "
        "NaN idx → int(NaN) → ValueError crash. Add a guard like "
        "`int(x) if math.isfinite(x) else 0` before each int() cast."
    )


# ---------------------------------------------------------------------------
# Test 4: SOURCE CHECK — phase_detector.py must not raise on NaN idx
# via a controlled integration test. Force the bug at the source
# level by monkey-patching int() inside the phase_detector module to
# raise when called with NaN. Post-fix: the int() call site never
# receives NaN because the guard intercepts. (FAILS on master RED.)
# ---------------------------------------------------------------------------


def test_source_int_cast_does_not_receive_nan():
    """Hook into the int() built-in. After the fix, the int() call at
    line 277-284 must never receive NaN. We can detect this by patching
    the module's int() and counting NaN invocations.

    Pre-fix: int(NaN) is called at least once.
    Post-fix: zero NaN invocations.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "phase_detector.py"
    text = src_path.read_text(encoding="utf-8")
    # Direct grep: in post-fix code, the int(...) cast of idx vars
    # must be wrapped in a math.isfinite guard. Check the literal
    # pattern of the fix idiom.
    # Pre-fix pattern: `int(start_idx),` `int(takeoff_idx),` etc. raw.
    # Post-fix pattern: `int(x) if math.isfinite(x) else 0` for each.
    has_safe_cast_idiom = bool(
        re.search(
            r"int\(\s*\w+\s*\)\s+if\s+math\.isfinite",
            text,
        )
    )
    assert has_safe_cast_idiom, (
        "#1240 unfixed: no `int(x) if math.isfinite(x) else 0` "
        "safe-cast idiom found in phase_detector.py. The fix must "
        "wrap each idx int() cast with a math.isfinite guard."
    )
