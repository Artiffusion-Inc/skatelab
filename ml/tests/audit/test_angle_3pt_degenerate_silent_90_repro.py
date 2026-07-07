"""RED repro: angle_3pt_rad silently returns 90 deg on degenerate inputs.

Issue #1055: the ``+ 1e-8`` epsilon in the denominator masks the degenerate
case (zero-length ``ba`` or ``bc`` vector). ``cos = 0 / 1e-8 = 0`` then
``arccos(0) = pi/2`` => the function returns 90 deg for an angle that is
mathematically UNDEFINED. The caller in ``compute_joint_angles``
(``ml/src/analysis/angles.py:93-100``) cannot distinguish a legitimate
90 deg joint from a degenerate joint and silently propagates the
wrong value to the biomechanics analysis downstream.

Contract under test: a degenerate joint MUST NOT return a finite 90 deg.
A correct implementation returns NaN, raises, or otherwise flags the
degenerate case so the caller can mask it.
"""

from __future__ import annotations

import inspect
import math

import numpy as np

from src.utils.geometry import angle_3pt, angle_3pt_rad

P = np.array([0.0, 0.0])
P_DIFF = np.array([1.0, 1.0])


class TestAngle3ptRadDegenerateRepro:
    """RED repro: angle_3pt_rad MUST NOT silently return 90 deg on degenerate inputs."""

    def test_angle_3pt_all_same_point_does_not_silently_return_90_repro(self):
        """A = B = C (all same point) is undefined — MUST NOT be 90 deg."""
        angle = angle_3pt(P, P, P)
        # On unfixed code: returns 90.0 (BUG — silent wrong answer).
        # On fixed code: returns NaN or raises.
        assert not (np.isfinite(angle) and np.isclose(angle, 90.0)), (
            f"angle_3pt(p, p, p) returned {angle}; degenerate joint must NOT be 90 deg"
        )

    def test_angle_3pt_a_equals_b_does_not_silently_return_90_repro(self):
        """A = B (zero-length ``ba``) is undefined — MUST NOT be 90 deg."""
        angle = angle_3pt(P, P, P_DIFF)
        assert not (np.isfinite(angle) and np.isclose(angle, 90.0)), (
            f"angle_3pt(p, p, p_diff) returned {angle}; zero-length ba must NOT be 90 deg"
        )

    def test_angle_3pt_b_equals_c_does_not_silently_return_90_repro(self):
        """B = C (zero-length ``bc``) is undefined — MUST NOT be 90 deg."""
        angle = angle_3pt(P_DIFF, P, P)
        assert not (np.isfinite(angle) and np.isclose(angle, 90.0)), (
            f"angle_3pt(p_diff, p, p) returned {angle}; zero-length bc must NOT be 90 deg"
        )

    def test_angle_3pt_valid_inputs_unchanged_repro(self):
        """Regression: valid (non-degenerate) inputs must still be correct."""
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 0.0])
        c = np.array([1.0, 1.0])

        angle = angle_3pt(a, b, c)
        assert np.isfinite(angle)
        assert 0.0 <= angle <= 180.0
        assert np.isclose(angle, 90.0)

        angle_rad = angle_3pt_rad(a, b, c)
        assert np.isfinite(angle_rad)
        assert np.isclose(angle_rad, math.pi / 2)

    def test_angle_3pt_rad_degenerate_guard_source_repro(self):
        """Source check: ``+ 1e-8`` epsilon MUST NOT mask the degenerate case.

        The bug is the silent epsilon in the denominator. Either the epsilon
        is removed (caller catches the resulting ZeroDivisionError → NaN) or
        an explicit ``norm < eps`` guard returns NaN. This test rejects the
        pre-fix shape and locks in the explicit guard.
        """
        src = inspect.getsource(angle_3pt_rad)

        # Pre-fix: ``... + 1e-8`` epsilon hides the degenerate case.
        assert "np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8" not in src, (
            "angle_3pt_rad still has the +1e-8 epsilon that masks degenerate vectors; "
            "see issue #1055"
        )

        # Post-fix contract: explicit norm guard or no-epsilon division.
        has_explicit_guard = "norm(ba)" in src and "norm(bc)" in src
        assert has_explicit_guard, (
            "angle_3pt_rad must guard degenerate vectors explicitly (norm check "
            "or removed epsilon) — see issue #1055"
        )
