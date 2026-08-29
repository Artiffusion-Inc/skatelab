"""RED repro: OneEuroFilter.filter_sample NaN/inf timestamp guard bypass (#1033).

Root cause: monotonic guard `if t <= self._t_prev` does NOT catch NaN
(`NaN <= x == False` in Python) → `te = NaN - t_prev = NaN` →
`_smoothing_factor_numba` under Numba `fastmath=True` → ZeroDivisionError
(fastmath NaN-as-0). inf also bypasses monotonic check in non-init case only
when inf <= t_prev is False (inf is greater), so inf reaches `te = inf - t_prev`
and downstream stays inf (no crash but contract violation).

Fix contract: NaN/inf timestamps must be rejected by `ValueError` BEFORE the
monotonic comparison and BEFORE `te = t - self._t_prev`.
"""

from __future__ import annotations

import inspect
import math

import pytest

from src.utils.smoothing import OneEuroFilter

# --- RED: NaN timestamp ------------------------------------------------------


def test_nan_timestamp_raises_value_error_not_zero_division() -> None:
    """NaN timestamp must raise ValueError (guard contract), NOT ZeroDivisionError."""
    f = OneEuroFilter(freq=30.0)
    f.filter_sample(0.0, 1.0)  # init
    with pytest.raises(ValueError, match=r"[Ff]inite|NaN|timestamp"):
        f.filter_sample(float("nan"), 0.5)


def test_inf_timestamp_raises_value_error() -> None:
    """inf timestamp is not a finite monotonic timestamp → ValueError."""
    f = OneEuroFilter(freq=30.0)
    f.filter_sample(0.0, 1.0)  # init
    with pytest.raises(ValueError, match=r"[Ff]inite|inf|timestamp"):
        f.filter_sample(float("inf"), 0.5)


def test_neg_inf_timestamp_raises_value_error() -> None:
    """-inf timestamp is not a finite timestamp → ValueError."""
    f = OneEuroFilter(freq=30.0)
    f.filter_sample(0.0, 1.0)  # init
    with pytest.raises(ValueError, match=r"[Ff]inite|inf|timestamp"):
        f.filter_sample(float("-inf"), 0.5)


# --- Regression: normal finite increasing timestamps ------------------------


def test_finite_increasing_timestamp_returns_finite() -> None:
    """Regression: normal finite increasing timestamps still filter to finite values."""
    f = OneEuroFilter(freq=30.0)
    out0 = f.filter_sample(0.0, 1.0)
    out1 = f.filter_sample(1.0 / 30.0, 1.2)
    out2 = f.filter_sample(2.0 / 30.0, 1.4)
    assert math.isfinite(out0)
    assert math.isfinite(out1)
    assert math.isfinite(out2)


def test_init_nan_timestamp_raises_value_error() -> None:
    """First-sample (init path) NaN timestamp must also raise ValueError.

    The init branch sets `_t_prev = t` without any guard; a NaN seed poisons all
    subsequent samples. Reject at init too.
    """
    f = OneEuroFilter(freq=30.0)
    with pytest.raises(ValueError, match=r"[Ff]inite|NaN|timestamp"):
        f.filter_sample(float("nan"), 1.0)


# --- Root-cause lock: source check ------------------------------------------


def test_filter_source_has_finite_guard_before_monotonic() -> None:
    """Source-check: isfinite guard present BEFORE `te = t - self._t_prev`.

    Locks the root-cause fix in place against regressions that move or remove
    the guard.
    """
    src = inspect.getsource(OneEuroFilter.filter_sample)
    # Must reference a finite-check helper.
    guard_idx = src.find("isfinite")
    assert guard_idx >= 0, "filter_sample missing isfinite guard:\n" + src
    # Guard must appear before the monotonic comparison `if t <= self._t_prev`
    # (the existing guard that NaN bypasses) and before the time-interval
    # computation `te = t - self._t_prev`.
    monotonic_idx = src.find("if t <= self._t_prev")
    assert monotonic_idx >= 0, "could not locate monotonic guard in source"
    assert guard_idx < monotonic_idx, "isfinite guard not placed before monotonic guard:\n" + src
