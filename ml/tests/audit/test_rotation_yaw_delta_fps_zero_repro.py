"""RED repro — `BiomechanicsAnalyzer.compute_rotation_yaw_delta` (3D yaw
cross-check, metrics.py:1458) divides by `fps` for the physiological clamp
ceiling with no fps=0 guard:

    max_delta = np.radians(2400.0 / fps)   # line 1458 — int/0.0 → ZeroDivisionError
    clamped = np.abs(delta) > max_delta   # line 1459 — never reached
    delta = np.clip(delta, -max_delta, max_delta)  # line 1460

Corrupt / truncated video reports `cv2.CAP_PROP_FPS = 0` (OpenCV sentinel).
`meta.fps = 0.0` → pipeline `analyzer.analyze(smoothed_3d, phases, 0.0)` →
`_analyze_jump(..., fps=0.0)` → `compute_rotation_yaw_delta(poses_3d,
flight_indices, fps=0.0)` → `2400.0 / 0.0` → ZeroDivisionError. 3D yaw
cross-check aborts metric computation before the result list returns;
2D rotation count already computed in the same `_analyze_jump` call is
LOST (exception propagates). Session fails wholesale for a 3D-enabled
fps=0 video whose rotation metrics would otherwise compute.

Sibling consistency (#499 fps=0 family): the 2D sibling
`compute_total_rotation_from_poses` does NOT divide by fps (delegates to
`compute_total_rotation` which only multiplies). 10 sibling paths already
guard fps=0 (VideoMeta.duration_sec, ElementPhase.airtime_sec,
phase_detector:234, physics_engine 3D #937 + 2D #939, pose_tracker #952,
smoothing #948, analyzer_save #647, TAS inference/classifier #950,
spin_classifier #505). The 3D yaw clamp is the sibling that missed the guard.

The clamp ceiling `2400.0 / fps` caps per-frame deltas at ~2400 deg/s
(physiologically impossible rotation = tracking artifact). The clamp is
MEANT to cap degenerate dt (1/fps=inf tracking artifact); at fps=0 the
ceiling computation itself raises. The correct semantics at fps<=0:
"no clamp" — infinite ceiling → `np.clip(delta, -inf, inf)` is a no-op for
finite deltas → rotation count from raw deltas, NOT a crash.

The fix (NOT applied — repro only): guard the ceiling division:
    max_delta = np.radians(2400.0 / fps) if fps > 0 else np.inf
`np.clip(delta, -np.inf, np.inf)` is a no-op for finite deltas (rotation
count from raw deltas), and `np.abs(delta) > np.inf` is always False
(clamped mask all-False). Valid fps unchanged; fps=0 degrades to
"no physiological clamp" instead of a crash. One-line guard at the single
divide site — root-cause fix, smallest diff.

The correct contract: `compute_rotation_yaw_delta(poses_3d,
flight_indices, fps=0.0)` with finite poses must NOT raise
ZeroDivisionError — must return a finite `(total_deg, rotation_count,
clamped)` (clamped all-False, rotation_count from raw deltas), NOT crash.

RED now: the observable assertions below describe the CORRECT behavior —
fps=0 no crash, finite return. They FAIL because `2400.0 / 0.0` raises.
The source-check confirms the `if fps > 0` guard is present at the divide
site (root cause locked).

Pure-Python (no GPU, no DB): `compute_rotation_yaw_delta` is a
pure-data staticmethod over a 3D poses array.
"""

import inspect

import numpy as np

from src.analysis.metrics import BiomechanicsAnalyzer
from src.types import H36Key


def _flight_poses_3d(n_flight: int = 20) -> np.ndarray:
    """A (n_flight, 17, 3) 3D pose sequence with rotating shoulders so the
    yaw cross-check computes a nonzero rotation. LSHOULDER/RSHOULDER
    rotate around Z (depth) across frames — yaw = arctan2(rz-lz, rx-lx)
    sweeps as frames progress.
    """
    poses = np.zeros((n_flight, 17, 3), dtype=np.float32)
    # Shoulders at fixed y, rotating around Z (depth) axis.
    for f in range(n_flight):
        ang = f * (2 * np.pi / n_flight)  # one full rotation over the flight
        poses[f, H36Key.LSHOULDER] = [-0.2, 0.1, 0.0]
        poses[f, H36Key.RSHOULDER] = [0.2 * np.cos(ang), 0.1, 0.2 * np.sin(ang)]
    return poses


# --------------------------------------------------------------------------- #
# Observable 1: `compute_rotation_yaw_delta(fps=0.0)` — no crash, finite
# (total_deg, rotation_count, clamped).
# --------------------------------------------------------------------------- #


def test_compute_rotation_yaw_delta_fps_zero_no_crash_repro():
    """CORRECT behavior: `compute_rotation_yaw_delta(poses_3d,
    flight_indices, fps=0.0)` must return a finite `(total_deg,
    rotation_count, clamped)`, NOT raise ZeroDivisionError.

    RED now: `2400.0 / 0.0` (line 1458) raises ZeroDivisionError before
    `clamped` / `np.clip`. After the fix: `... if fps > 0 else np.inf` →
    np.clip no-op for finite deltas → rotation_count from raw deltas.
    """
    poses = _flight_poses_3d()
    flight = np.arange(poses.shape[0])
    total_deg, rot_count, clamped = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
        poses, flight, fps=0.0
    )
    assert np.isfinite(total_deg), (
        f"BUG: compute_rotation_yaw_delta(fps=0.0) leaked non-finite "
        f"total_deg={total_deg!r}. 2400.0/fps ZeroDivisionError today; "
        f"guard must yield inf ceiling → clip no-op → finite total."
    )
    assert np.isfinite(rot_count), (
        f"BUG: compute_rotation_yaw_delta(fps=0.0) leaked non-finite rotation_count={rot_count!r}."
    )
    assert isinstance(clamped, np.ndarray), (
        f"BUG: clamped must be a ndarray, got {type(clamped).__name__}."
    )


# --------------------------------------------------------------------------- #
# Observable 2: fps<=0 family — negative fps, -0.0 also no crash (mirror
# the `fps > 0` guard; `fps <= 0` all hit the inf-ceiling branch).
# --------------------------------------------------------------------------- #


def test_compute_rotation_yaw_delta_nonpositive_fps_no_crash_repro():
    """CORRECT behavior: fps=-1.0 and fps=-0.0 must also not crash. The
    `fps > 0` guard treats all nonpositive fps as "no clamp" (inf ceiling).
    """
    poses = _flight_poses_3d()
    flight = np.arange(poses.shape[0])
    for fps in (-1.0, -0.0, 0.0):
        total_deg, rot_count, _ = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
            poses, flight, fps=fps
        )
        assert np.isfinite(total_deg) and np.isfinite(rot_count), (
            f"BUG: fps={fps} leaked non-finite (total={total_deg!r}, "
            f"count={rot_count!r}). Guard `fps > 0 else inf` covers all "
            f"nonpositive fps."
        )


# --------------------------------------------------------------------------- #
# Observable 3: fps=0 → clamped mask all-False (inf ceiling → no delta
# exceeds inf). Locks the "no clamp at fps<=0" contract.
# --------------------------------------------------------------------------- #


def test_compute_rotation_yaw_delta_fps_zero_clamped_all_false_repro():
    """CORRECT behavior: at fps=0 the inf ceiling means no delta exceeds
    it → `clamped` is all-False. The clamp is disabled (not crashed).

    RED now: crashes at line 1458 before `clamped` is computed. After the
    fix: `np.abs(delta) > np.inf` is always False → clamped all-False.
    """
    poses = _flight_poses_3d()
    flight = np.arange(poses.shape[0])
    _, _, clamped = BiomechanicsAnalyzer.compute_rotation_yaw_delta(poses, flight, fps=0.0)
    assert not clamped.any(), (
        f"BUG: fps=0 clamped should be all-False (inf ceiling → no delta "
        f"exceeds inf), got {clamped.tolist()}. Clamp disabled at fps<=0."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps unchanged — fps=30 reports finite nonzero
# rotation_count.
# --------------------------------------------------------------------------- #


def test_compute_rotation_yaw_delta_valid_fps_unchanged_repro():
    """Regression guard: fps=30 must still report a finite rotation_count.
    The fps>0 guard must not change the valid-fps case. PASSES today;
    locks the contract so the guard cannot regress the normal path.
    """
    poses = _flight_poses_3d()
    flight = np.arange(poses.shape[0])
    total_deg, rot_count, _ = BiomechanicsAnalyzer.compute_rotation_yaw_delta(
        poses, flight, fps=30.0
    )
    assert np.isfinite(total_deg) and np.isfinite(rot_count), (
        f"BUG (regression): fps=30 should report finite rotation, got "
        f"total={total_deg!r}, count={rot_count!r}. The fps>0 guard must "
        f"not change the valid-fps case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `if fps > 0` guard at the 2400.0/fps
# divide site.
# --------------------------------------------------------------------------- #


def test_compute_rotation_yaw_delta_fps_zero_guard_source_repro():
    """GREEN contract source check: the fps=0 crash is fixed by a
    `if fps > 0 else np.inf` guard at the `2400.0 / fps` divide site
    (line 1458). inf ceiling → np.clip no-op for finite deltas → rotation
    count from raw deltas, not a crash. Mirrors the #499 fps=0 family
    guard pattern.
    """
    src = inspect.getsource(BiomechanicsAnalyzer.compute_rotation_yaw_delta)
    assert "2400.0 / fps" in src and "fps > 0" in src, (
        "BUG: compute_rotation_yaw_delta must guard "
        "`np.radians(2400.0 / fps) if fps > 0 else np.inf` at the clamp "
        "ceiling divide (line 1458). Corrupt video fps=0 → "
        "ZeroDivisionError today. inf ceiling → np.clip no-op, finite "
        "rotation_count from raw deltas."
    )
