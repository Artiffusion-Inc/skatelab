"""Repro tests — spin_peak_velocity takes global max, not spin-segment max (#858).

``_analyze_spin`` (metrics.py:590) computes ``spin_peak_velocity`` as
``np.max(angular_velocity)`` over the ENTIRE pose sequence, not over the
detected spin segment. ``detect_spin`` returns ``(is_spin, duration_s,
hip_y_range)`` — no spin frame mask — so the analyzer has no spin window and
silently falls back to the global max. A transient shoulder-vector jump
OUTSIDE the spin (arm swing on entry, exit flail, tracking glitch) is a
gradient spike that becomes the global max → reported "spin peak velocity"
reflects the noise, not the spin. A weak slow spin with an exit flail reads as
a hyper-fast spin (50× inflation), and ``is_good`` is wrong (too-fast, not
too-slow).

Fix (#858): ``detect_spin`` returns the per-frame spin mask so the analyzer can
mask: ``np.max(angular_velocity[spin_mask])`` (0.0 if no spin detected).
"""

from __future__ import annotations

import inspect

import numpy as np

from src.analysis.element_defs import get_element_def
from src.analysis.metrics import BiomechanicsAnalyzer
from src.analysis.spin_classifier import detect_spin
from src.types import ElementPhase


def _analyzer() -> BiomechanicsAnalyzer:
    return BiomechanicsAnalyzer(get_element_def("upright_spin"))


def _weak_spin_pose_with_exit_flail() -> np.ndarray:
    """45 frames: a slow real spin (frames 0-34) + a static gap (35-42) + an
    exit shoulder-flail spike (frame 43) where the shoulders snap, producing a
    gradient spike at frame 44 far above the real spin peak.

    The static gap separates the spin run from the flail run so the spin mask
    (the contiguous >=1.0 s run) excludes the flail. Real spin angular
    velocity ~250 deg/s (above the 200 deg/s detect_spin threshold); flail
    spike ~4000+ deg/s.
    """
    n = 45
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    # Real 2D shoulder rotation over frames 0-34 (~0.78 turns, slow).
    t = np.linspace(0, 2 * np.pi * 0.78, 35)
    poses[:35, 11, 0] = 0.5 + 0.1 * np.cos(t)  # LSHOULDER
    poses[:35, 11, 1] = 0.5 + 0.1 * np.sin(t)
    poses[:35, 14, 0] = 0.5 - 0.1 * np.cos(t)  # RSHOULDER
    poses[:35, 14, 1] = 0.5 - 0.1 * np.sin(t)
    # Static gap frames 35-42: hold last rotation pose (no gradient).
    poses[35:43] = poses[34]
    # Inject an exit flail at frame 43: shoulders snap (big step change).
    poses[43, 11, 0] = 0.9
    poses[43, 11, 1] = 0.5
    poses[43, 14, 0] = 0.1
    poses[43, 14, 1] = 0.5
    return poses


def test_non_spin_spike_does_not_dominate_spin_peak_velocity_repro():
    """#858: a non-spin exit-flail spike must not be reported as spin peak."""
    analyzer = _analyzer()
    poses = _weak_spin_pose_with_exit_flail()
    phases = ElementPhase(name="upright_spin", start=0, takeoff=0, peak=17, landing=44, end=45)
    results = analyzer.analyze(poses, phases, fps=30.0)
    peak = next(r for r in results if r.name == "spin_peak_velocity")
    # Real spin peak ~250 deg/s; flail spike ~4000+. Buggy reports the spike.
    assert peak.value < 500.0, (
        f"#858 RED: spin_peak_velocity={peak.value} deg/s — the global max over "
        "the whole sequence is reported, so an exit-flail gradient spike (4000+ "
        "deg/s) dominates instead of the real spin peak (~250 deg/s). Peak must be "
        "restricted to the detected spin segment."
    )


def test_weak_spin_reports_weak_peak_not_global_spike_repro():
    """#858: a weak slow spin reports its real (weak) peak, and is_good flags
    'too slow' (< 300), not 'too fast' (> 600) due to a flail spike."""
    analyzer = _analyzer()
    poses = _weak_spin_pose_with_exit_flail()
    phases = ElementPhase(name="upright_spin", start=0, takeoff=0, peak=17, landing=44, end=45)
    results = analyzer.analyze(poses, phases, fps=30.0)
    peak = next(r for r in results if r.name == "spin_peak_velocity")
    # Real spin peak ~250 deg/s, below the (300, 600) ideal range → too_slow, not too_high.
    assert peak.value < 300.0, (
        f"#858 RED: weak spin reported peak={peak.value} (>300) — the flail spike "
        "inflated the value, masking that the actual spin is too slow. is_good would "
        "flag 'too fast' instead of the correct 'too slow'."
    )


def test_clean_uniform_spin_peak_unchanged_repro():
    """#858 regression guard: a clean uniform spin (every frame spinning) peak
    is unchanged by the masking fix — global max == spin-segment max."""
    analyzer = _analyzer()
    n = 30
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    # Real 2D rotation: shoulder vector = -2R*(cos t, sin t) → angle = t+π
    # (linear in t) → uniform angular velocity ~372 deg/s (>200 threshold) so
    # detect_spin fires on every frame (is_spin=True, mask == all frames).
    t = np.linspace(0, 2 * np.pi, n)
    poses[:, 11, 0] = 0.5 + 0.1 * np.cos(t)  # LSHOULDER
    poses[:, 11, 1] = 0.5 + 0.1 * np.sin(t)
    poses[:, 14, 0] = 0.5 - 0.1 * np.cos(t)  # RSHOULDER
    poses[:, 14, 1] = 0.5 - 0.1 * np.sin(t)
    phases = ElementPhase(name="upright_spin", start=0, takeoff=0, peak=15, landing=29, end=n)
    results = analyzer.analyze(poses, phases, fps=30.0)
    peak = next(r for r in results if r.name == "spin_peak_velocity")
    # Uniform spin: peak must be a finite, nonzero value (mask == all frames).
    assert peak.value > 0.0 and np.isfinite(peak.value), (
        f"#858: clean uniform spin peak={peak.value} — masking must not zero out a "
        "real spin where every frame is spinning."
    )


def test_detect_spin_returns_spin_mask_repro():
    """#858 GREEN: detect_spin must return the per-frame spin mask so callers
    can restrict peak/mean to the detected spin segment."""
    # The return must carry the spin mask (4-tuple, not the old 3-tuple).
    src = inspect.getsource(detect_spin)
    # Old form returned a 3-tuple and never exposed is_spinning to callers.
    assert "is_spinning" in src, (
        "#858: detect_spin must compute and return the per-frame spin mask so the "
        "analyzer can mask np.max(angular_velocity) to the spin segment."
    )
