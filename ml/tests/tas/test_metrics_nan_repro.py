"""Regression tests for issue #1158: MultiOverlapF1.compute crashes on NaN threshold.

`int(threshold * 100)` raises `ValueError: cannot convert float NaN to integer`
when `self.thresholds` contains NaN (corrupt config). Guard with `math.isfinite`.
"""

import math

import numpy as np

try:
    from ml.src.tas.metrics import MultiOverlapF1
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from tas.metrics import MultiOverlapF1


def _labels():
    return np.array([0, 0, 1, 1, 1, 0, 2, 2, 0], dtype=np.int64)


def test_nan_threshold_does_not_crash():
    """NaN threshold must not raise ValueError from int(NaN)."""
    m = MultiOverlapF1(thresholds=[0.5, float("nan"), 0.75])
    # Must not raise
    result = m.compute(_labels(), _labels())
    assert isinstance(result, dict)
    # Finite thresholds still produce tagged entries
    assert "f1@50" in result
    assert "f1@75" in result


def test_inf_threshold_does_not_crash():
    """Infinity threshold must not raise (also non-finite)."""
    m = MultiOverlapF1(thresholds=[float("inf"), 0.5])
    result = m.compute(_labels(), _labels())
    assert "f1@50" in result


def test_all_nan_thresholds_returns_empty_or_finite_keys():
    """If every threshold is NaN, result has no int(NaN) crash."""
    m = MultiOverlapF1(thresholds=[float("nan")])
    result = m.compute(_labels(), _labels())
    # No NaN-tagged keys produced
    for k in result:
        assert not k.endswith("@nan"), f"unexpected NaN tag in {k}"


def test_finite_thresholds_unchanged():
    """Sanity: baseline behaviour with all-finite thresholds preserved."""
    m = MultiOverlapF1(thresholds=[0.1, 0.25, 0.5])
    result = m.compute(_labels(), _labels())
    assert "f1@10" in result
    assert "f1@25" in result
    assert "f1@50" in result
    for v in result.values():
        assert math.isfinite(float(v))


def test_tag_format_for_finite_threshold():
    """Finite threshold 0.30 -> tag '30' (regression guard for tag format)."""
    m = MultiOverlapF1(thresholds=[0.30])
    result = m.compute(_labels(), _labels())
    assert "f1@30" in result
    assert "precision@30" in result
    assert "recall@30" in result
