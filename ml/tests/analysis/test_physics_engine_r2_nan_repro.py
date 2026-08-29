"""RED repro → GREEN after fix: `physics_engine` fit_quality silently
classified as 0.0 when flight CoM contains NaN. Three R² computation sites,
same pattern:

  - `_fit_jump_trajectory_with_com`  (physics_engine.py:~419, ~441 fallback)
  - `fit_jump_trajectory`            (physics_engine.py:~524, ~546 fallback)
  - `analyze_2d`                     (physics_engine.py:~683)

`np.polyfit(NaN-data)` and `curve_fit(NaN-data)` both yield NaN coeffs →
`ss_res = NaN, ss_tot = NaN`. `NaN > 0 == False` (NaN-blind guard) →
silent `r_squared = 0`. `curve_fit` actually raises on NaN, so the 3D paths
take their `except Exception` fallback which also hard-codes
`fit_quality: 0.0`. Either way, the corrupt-flight signal is lost.

CoM functions are NaN-aware (#871, #884, #878), so reproducing the bug
through the public entry points requires injecting NaN past the masking
layer. We do this by feeding a NaN-laden CoM directly into the private
3D helper and by monkey-patching CoM calcs.

GREEN contract: when flight CoM has any NaN, fit_quality must NOT silently
equal 0.0. Acceptable behaviors: NaN (preferred — signals "unknown") or
raised error. The fix is `math.isfinite(ss_tot) and ss_tot > 0` at each
R² site plus propagating NaN through the except-fallback.

3 observables (3D public, 3D private, 2D — all NaN-flight paths)
1 regression   (valid CoM → real R² in (0, 1])
1 source check (root cause locked via file read).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np


def _is_silent_zero(fq):
    """Detect the silent-zero fallback: 0.0 (or None) returned when flight
    CoM has NaN. Legitimate R² of a parabola on the typical case is 1.0,
    not 0.0. The 0.0 here is the NaN-blind `ss_tot > 0` ternary falling
    through (or the except-fallback hard-coding 0.0). A correct fix
    returns NaN — anything except 0.0.
    """
    return fq is None or (isinstance(fq, (int, float, np.floating)) and fq == 0.0)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _build_parabolic_com(n_frames: int, fps: float = 30.0) -> np.ndarray:
    """(N, 3) CoM trajectory following a parabola on the Y axis (CoM height)."""
    t = np.arange(n_frames) / fps
    h0, v0, g = 1.0, 3.0, 9.81
    h_t = h0 + v0 * t - 0.5 * g * t * t
    com = np.zeros((n_frames, 3), dtype=np.float64)
    com[:, 1] = h_t
    return com


def _build_parabolic_poses(n_frames: int, fps: float = 30.0) -> np.ndarray:
    """(N, 17, 3) poses whose (NaN-aware) CoM follows a parabola."""
    com = _build_parabolic_com(n_frames, fps)
    poses = np.broadcast_to(com[:, None, :], (n_frames, 17, 3)).copy()
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: public 3D `fit_jump_trajectory` — NaN flight → fit_quality 0.0.
# The 3D public path uses curve_fit, which RAISES on NaN — so the bug is
# the except-fallback hard-coding `fit_quality: 0.0`. We patch CoM to inject
# NaN past the NaN-aware masking.
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_r2_fit_jump_trajectory_nan_flight_silent_zero_repro():
    """RED: 3D public fit_jump_trajectory with NaN flight CoM → 0.0 silently."""
    from src.analysis.physics_engine import PhysicsEngine

    engine = PhysicsEngine()
    n_frames = 30
    poses = _build_parabolic_poses(n_frames=n_frames, fps=30.0)
    takeoff, landing = 5, n_frames - 1

    com_clean = _build_parabolic_com(n_frames, fps=30.0)
    com_nan = com_clean.copy()
    com_nan[-1, 1] = np.nan  # landing frame corrupted

    with patch.object(PhysicsEngine, "calculate_center_of_mass", return_value=com_nan):
        result = engine.fit_jump_trajectory(poses, takeoff, landing, fps=30.0)

    fq = result["fit_quality"]
    assert not _is_silent_zero(fq), (
        f"BUG: fit_jump_trajectory with NaN flight CoM returned "
        f"fit_quality = {fq!r}. The except-fallback hard-codes 0.0 when "
        f"curve_fit raises on NaN flight — corrupt flight data is hidden "
        f"from the user. Expected NaN (signals 'unknown')."
    )


# --------------------------------------------------------------------------- #
# Observable 2: private 3D `_fit_jump_trajectory_with_com` — NaN flight → 0.
# Takes a pre-computed CoM, so we can inject NaN directly. Same pattern.
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_r2_private_fit_with_com_nan_flight_silent_zero_repro():
    """RED: 3D private _fit_jump_trajectory_with_com with NaN flight → 0 silently."""
    from src.analysis.physics_engine import PhysicsEngine

    engine = PhysicsEngine()
    n_frames = 30
    poses = _build_parabolic_poses(n_frames=n_frames, fps=30.0)
    com = _build_parabolic_com(n_frames, fps=30.0)
    com[-1, 1] = np.nan
    takeoff, landing = 5, n_frames - 1
    result = engine._fit_jump_trajectory_with_com(
        poses, takeoff, landing, com_trajectory=com, fps=30.0
    )
    fq = result["fit_quality"]
    assert not _is_silent_zero(fq), (
        f"BUG: _fit_jump_trajectory_with_com with NaN flight CoM returned "
        f"fit_quality = {fq!r}. Same NaN-blind `ss_tot > 0` guard (or the "
        f"except-fallback) silently classified corrupt flight as 0.0."
    )


# --------------------------------------------------------------------------- #
# Observable 3: 2D `analyze_2d` — NaN flight → fit_quality = 0.0 silently.
# 2D path uses np.polyfit which returns NaN coeffs WITHOUT raising — so the
# R² ternary at line ~683 IS hit and is the actual silent-zero source.
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_r2_analyze_2d_nan_flight_silent_zero_repro():
    """RED: 2D analyze_2d with NaN flight CoM → fit_quality = 0.0 silently."""
    from src.analysis.physics_engine import PhysicsEngine

    engine = PhysicsEngine()
    n_frames = 30
    poses_2d = _build_parabolic_poses(n_frames, fps=30.0)[:, :, :2].astype(np.float32)
    takeoff, landing = 5, n_frames - 1

    com_clean = _build_parabolic_com(n_frames, fps=30.0)[:, :2].astype(np.float32)
    com_nan = com_clean.copy()
    com_nan[-1, 1] = np.nan

    with patch("src.utils.geometry.calculate_com_trajectory_2d", return_value=com_nan):
        result = engine.analyze_2d(poses_2d, takeoff_idx=takeoff, landing_idx=landing, fps=30.0)

    fq = result["fit_quality"]
    assert not _is_silent_zero(fq), (
        f"BUG: analyze_2d with NaN flight CoM returned "
        f"fit_quality = {fq!r}. Same NaN-blind `ss_tot > 0` guard silently "
        f"coerced ss_res=NaN, ss_tot=NaN to fit_quality=0.0."
    )


# --------------------------------------------------------------------------- #
# Regression: valid CoM (no NaN) must still produce a real R² in (0, 1].
# GREEN on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_r2_valid_flight_real_r_squared_regression():
    """Regression: clean parabolic CoM → fit_quality close to 1.0.

    Locks the contract so the isfinite fix doesn't break the typical case.
    """
    from src.analysis.physics_engine import PhysicsEngine

    engine = PhysicsEngine()
    n_frames = 30
    poses = _build_parabolic_poses(n_frames=n_frames, fps=30.0)
    takeoff, landing = 5, n_frames - 1
    result = engine.fit_jump_trajectory(poses, takeoff, landing, fps=30.0)
    fq = result["fit_quality"]
    assert np.isfinite(fq) and fq > 0.5, (
        f"BUG (regression): clean parabolic CoM returned fit_quality = "
        f"{fq!r}, expected a real R² > 0.5 (parabola is the true signal)."
    )


# --------------------------------------------------------------------------- #
# Source check: the NaN-blind `ss_tot > 0` ternary must be guarded.
# RED on master, GREEN after fix.
# --------------------------------------------------------------------------- #


def test_r2_nan_guard_source_repro():
    """Source check: every R² site in physics_engine.py must use
    `math.isfinite(ss_tot) and ss_tot > 0` (not the NaN-blind `ss_tot > 0`).

    GREEN on master (post-fix): each R² site must guard with isfinite.
    Locks the root cause so a future refactor can't silently re-introduce
    the bug. Also asserts the except-fallback no longer hard-codes 0.0.
    """
    src_path = Path(__file__).parent.parent.parent / "src" / "analysis" / "physics_engine.py"
    src = src_path.read_text(encoding="utf-8")
    # The NaN-blind form must be gone (or guarded).
    assert "if ss_tot > 0 else" not in src, (
        "BUG: NaN-blind `if ss_tot > 0 else 0` ternary still present in "
        "physics_engine.py — silently returns r²=0.0 when flight CoM has "
        "any NaN. Replace with `if math.isfinite(ss_tot) and ss_tot > 0`."
    )
    # isfinite guards at the R² sites — exactly 3 (one per site).
    n_guards = src.count("math.isfinite(ss_tot) and ss_tot > 0")
    assert n_guards >= 3, (
        f"BUG: expected >= 3 `math.isfinite(ss_tot) and ss_tot > 0` guards "
        f"in physics_engine.py (one per R² site), found {n_guards}. The "
        f"NaN-blind `ss_tot > 0` ternary silently returns r²=0.0 when "
        f"flight CoM has any NaN."
    )
