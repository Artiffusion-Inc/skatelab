"""RED repro: pose_tracker._kalman_update np.linalg.inv(S) on singular S raises LinAlgError.

Bug (HIGH): ml/src/detection/pose_tracker.py:179 uses
    K = P @ H.T @ np.linalg.inv(S)
in _kalman_update. If S (innovation covariance) becomes singular or
near-singular, np.linalg.inv raises LinAlgError. There is no try/except
around this call.

S can become singular when:
- R is all-zeros (no measurement noise)
- All measurements are identical
- P is in a degenerate state (e.g., after a long period with no measurements)

This test verifies the contract: a singular or near-singular S matrix
must NOT crash the tracker; it should fall back to a safe default
(K = zeros or pinv).
"""

import numpy as np
import pytest


def test_kalman_update_singular_S_does_not_crash():
    """A singular S (H @ P @ H.T + R with R ~ zeros) must not raise LinAlgError.

    Constructs a degenerate case where S is exactly singular and the
    naive np.linalg.inv(S) would raise LinAlgError. The fix uses
    np.linalg.pinv (Moore-Penrose pseudoinverse) for graceful degradation.
    """
    from src.detection.pose_tracker import PoseTracker

    tracker = PoseTracker(fps=30.0)

    # Build a state and measurement that produce a singular S.
    # If H is all-zeros and R is all-zeros, S = H @ P @ H.T + R = 0 (singular).
    x = np.zeros((6, 1))  # zero state
    P = np.eye(6) * 0.1  # initial covariance
    H = np.zeros((2, 6))  # degenerate observation matrix (all-zeros)
    R = np.eye(2) * 0.0  # zero measurement noise -> S = 0 + 0 = 0 (singular)
    z = np.array([[0.0], [0.0]])

    # Pre-fix: LinAlgError. Post-fix: handles singular S via pinv.
    # Either returns a valid (x_upd, P_upd) tuple.
    try:
        x_upd, P_upd = tracker._kalman_update(x, P, z, H, R)
        # State and covariance must have correct shapes
        assert x_upd.shape == (6, 1), f"x_upd should be (6, 1), got {x_upd.shape}"
        assert P_upd.shape == (6, 6), f"P_upd should be (6, 6), got {P_upd.shape}"
        # Results should be finite (pinv graceful degradation)
        assert np.all(np.isfinite(x_upd)), f"x_upd must be finite, got {x_upd}"
        assert np.all(np.isfinite(P_upd)), f"P_upd must be finite, got {P_upd}"
    except np.linalg.LinAlgError as e:
        pytest.fail(
            f"_kalman_update raised LinAlgError on singular S: {e}. "
            f"Fix: use np.linalg.pinv(S) instead of np.linalg.inv(S)."
        )
