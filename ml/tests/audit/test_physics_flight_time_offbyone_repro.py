"""RED repro: physics_engine.analyze_2d flight_time off-by-one (inclusive end span).

Bug: physics_engine.py:628 `flight_frames = landing_idx - takeoff_idx` is the SPAN
     (exclusive end), but the inclusive COUNT is `landing_idx - takeoff_idx + 1`.
     :629 `flight_time = flight_frames / fps` inherits the span.
     INTERNAL INCONSISTENCY: :631 `com[takeoff_idx : landing_idx + 1, 1]` uses +1
     (inclusive slice) and :641 `np.arange(flight_frames + 1)` uses +1 (inclusive
     arange) — slice and arange treat the end as inclusive, but flight_time uses
     the exclusive span. flight_time is 1 frame short of the array it describes.

Repro:
  takeoff_idx=10, landing_idx=40, fps=30
  flight_frames -> 30 (span, BUG)
  flight_time   -> 30/30 = 1.0 (BUG)  vs 31/30 = 1.033 (CORRECT inclusive)

Prod impact:
  Display-only "Время полёта" report text (types.py:625) is 1 frame short.
  No GOE threshold crossing (the `airtime` metric routes through
  ElementPhase.airtime_sec — separate bug, see sibling repro). 2D fallback path
  used when 3D poses are unavailable.

Existing test_metrics_validation.py:938-955 ENCODED the bug
(`expected_time = (landing - takeoff) / fps`).
Sibling of #515/#516 (inclusive-end-duration-span off-by-one).
"""

import numpy as np
import pytest

from src.analysis.physics_engine import PhysicsEngine


class TestPhysicsFlightTimeOffByOne:
    """analyze_2d flight_time must count inclusive of the landing frame."""

    def test_flight_time_inclusive_count(self):
        """flight_time = (landing_idx - takeoff_idx + 1) / fps."""
        engine = PhysicsEngine(body_mass=60.0)
        fps = 30.0
        takeoff = 10
        landing = 40  # 10..40 inclusive = 31 frames

        n = 60
        rng = np.random.default_rng(42)
        poses = rng.random((n, 17, 2)).astype(np.float32)
        result = engine.analyze_2d(poses, takeoff_idx=takeoff, landing_idx=landing, fps=fps)

        # CORRECT inclusive: 31 frames / 30 fps = 1.0333... s.
        expected = (landing - takeoff + 1) / fps
        np.testing.assert_allclose(
            result["flight_time"],
            expected,
            rtol=1e-4,
            err_msg=(
                f"flight_time {result['flight_time']:.4f} != inclusive expected "
                f"{expected:.4f} (span bug: {(landing - takeoff) / fps:.4f})"
            ),
        )

    def test_flight_time_array_consistency(self):
        """flight_time must match the duration of the com slice actually used.

        analyze_2d slices com[takeoff:landing+1] (inclusive, N+1 rows) and builds
        t_flight = arange(flight_frames+1)/fps. flight_time should describe the
        same inclusive window, i.e. (flight_frames+1)/fps, not flight_frames/fps.
        """
        engine = PhysicsEngine(body_mass=60.0)
        fps = 30.0
        takeoff = 10
        landing = 40

        n = 60
        rng = np.random.default_rng(0)
        poses = rng.random((n, 17, 2)).astype(np.float32)
        result = engine.analyze_2d(poses, takeoff_idx=takeoff, landing_idx=landing, fps=fps)

        slice_len = landing - takeoff + 1  # com[takeoff:landing+1] has this many rows
        expected = slice_len / fps
        assert result["flight_time"] == pytest.approx(expected, abs=1e-6)
