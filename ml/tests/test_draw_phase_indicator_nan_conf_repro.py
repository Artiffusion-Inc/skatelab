"""Repro tests for issue #974: draw_phase_indicator NaN/inf confidence → "Conf: nan" HUD leak.

RED on master: f-string `f"Conf: {nan:.2f}"` silently renders "Conf: nan" /
"Conf: inf" into the user-facing HUD overlay text, with no error signal.
`confidence is not None` does NOT reject NaN (NaN is not None).
"""

import inspect
import math

import numpy as np

from src.visualization.hud.elements import draw_phase_indicator

FRAME = np.zeros((120, 200, 3), dtype=np.uint8)


def _draw(confidence: float | None) -> np.ndarray:
    return draw_phase_indicator(FRAME.copy(), "flight", confidence=confidence)


class TestDrawPhaseIndicatorNanConf:
    def test_nan_confidence_no_nan_text(self):
        """No literal 'nan' may render in the confidence HUD text."""
        # Source-level root-cause lock: draw_phase_indicator must guard NaN/inf
        # before the f-string renders "Conf: nan".
        src = inspect.getsource(draw_phase_indicator)
        assert "isfinite" in src, "draw_phase_indicator missing isfinite guard on confidence"
        # The f-string format path must be gated by the isfinite guard, so NaN
        # never reaches `:.2f`. The guard must precede the format.
        fmt_idx = src.index('f"Conf: {confidence:.2f}"')
        guard_idx = src.index("isfinite")
        assert guard_idx < fmt_idx, "isfinite guard must precede the confidence f-string"
        # Placeholder convention mirrors #970 (draw_axes).
        assert "—" in src, "draw_phase_indicator must substitute placeholder for non-finite conf"

    def test_inf_confidence_no_inf_text(self):
        """No literal 'inf' may render in the confidence HUD text."""
        src = inspect.getsource(draw_phase_indicator)
        # Same isfinite guard covers inf (inf is not finite).
        assert "isfinite" in src
        fmt_idx = src.index('f"Conf: {confidence:.2f}"')
        guard_idx = src.index("isfinite")
        assert guard_idx < fmt_idx, "isfinite guard must precede the confidence f-string"

    def test_nan_confidence_does_not_crash_silent_leak(self):
        """NaN confidence must not raise and must return a frame."""
        frame = _draw(math.nan)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_inf_confidence_does_not_crash_silent_leak(self):
        frame = _draw(math.inf)
        assert frame is not None
        assert frame.shape == FRAME.shape

    def test_finite_confidence_unchanged(self):
        """Regression: finite confidence renders the numeric value normally."""
        frame = _draw(0.83)
        assert frame is not None
        assert frame.shape == FRAME.shape
        # A finite confidence must still flow through the format path.
        src = inspect.getsource(draw_phase_indicator)
        assert "Conf:" in src
        assert "isfinite" in src
