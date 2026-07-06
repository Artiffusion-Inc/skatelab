"""#948 repro: PoseSmoother / One-Euro kernel must not crash on freq=0.

RED contract (before fix): a corrupt video reports fps=0
(cv2.CAP_PROP_FPS=0). The One-Euro kernel `_one_euro_filter_sequence_numba`
computes `dt = 1.0 / freq` (line 73) and OneEuroFilter.filter_sequence does
`np.arange(len(x)) / self.freq` (line 320) — both ZeroDivisionError on
freq=0, killing the worker job at the smoothing step. The phase-detector
sibling (phase_detector.py:234) already guards fps=0. GREEN contract (after
fix): freq<=0 falls back to frame-based dt=1.0 — finite output, same shape.
"""

from __future__ import annotations

import numpy as np
import pytest


def _sample_2d() -> np.ndarray:
    poses = np.zeros((20, 17, 2), dtype=np.float32)
    t = np.arange(20) / 30.0
    poses[:, 0, 0] = 0.5 * np.sin(2 * np.pi * t)
    poses[:, 0, 1] = 0.3 * np.cos(2 * np.pi * t)
    return poses


def _sample_3d() -> np.ndarray:
    poses = np.zeros((20, 17, 3), dtype=np.float32)
    t = np.arange(20) / 30.0
    poses[:, 0, 0] = 0.5 * np.sin(2 * np.pi * t)
    poses[:, 0, 1] = 0.3 * np.cos(2 * np.pi * t)
    poses[:, 0, 2] = 0.1 * t
    return poses


def test_pose_smoother_smooth_freq_zero_no_crash() -> None:
    """PoseSmoother.smooth with freq=0 returns finite, same-shape array."""
    from src.utils.smoothing import PoseSmoother

    smoother = PoseSmoother(freq=0.0)
    out = smoother.smooth(_sample_2d())
    assert out.shape == (20, 17, 2)
    assert np.all(np.isfinite(out)), "freq=0 produced non-finite smoothed output"


def test_pose_smoother_smooth_3d_freq_zero_no_crash() -> None:
    """PoseSmoother.smooth_3d with freq=0 returns finite, same-shape array."""
    from src.utils.smoothing import PoseSmoother

    smoother = PoseSmoother(freq=0.0)
    out = smoother.smooth_3d(_sample_3d())
    assert out.shape == (20, 17, 3)
    assert np.all(np.isfinite(out)), "freq=0 produced non-finite 3D smoothed output"


def test_one_euro_filter_sequence_freq_zero_no_crash() -> None:
    """The numba kernel with freq=0 returns finite output (frame-based dt=1.0)."""
    from src.utils.smoothing import _one_euro_filter_sequence_numba

    x = (0.5 * np.sin(2 * np.pi * np.arange(20) / 30.0)).astype(np.float64)
    out = _one_euro_filter_sequence_numba(
        x, freq=0.0, min_cutoff=1.0, beta=0.007, derivative_cutoff=1.0
    )
    assert out.shape == x.shape
    assert np.all(np.isfinite(out))


def test_smoothing_valid_freq_unchanged() -> None:
    """freq=30 still produces a smoothed output (regression guard)."""
    from src.utils.smoothing import PoseSmoother

    smoother = PoseSmoother(freq=30.0)
    out = smoother.smooth(_sample_2d())
    assert out.shape == (20, 17, 2)
    assert np.all(np.isfinite(out))
