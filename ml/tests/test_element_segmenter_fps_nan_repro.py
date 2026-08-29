"""RED repro — `ElementSegmenter._extract_segment_features`
(ml/src/analysis/element_segmenter.py:458) silently coerces NaN/negative
fps to `duration_sec=0.0`, INDISTINGUISHABLE from a legitimate `fps=0`
(broken-header video). Root cause:

    features["duration_sec"] = round(num_frames / fps, 3) if fps > 0 else 0.0
    # ↑ NaN fps → NaN > 0 is False → duration_sec = 0.0 (silent NaN→0)

Comment on lines 453-457 documents the fix for `fps=0` but the NaN/negative
case was missed. `math.isfinite` guard required at function entry
(mirrors PR 1043/1044 fps guard pattern: raise typed ValueError at trust
boundary, not silent coerce).

Empirical evidence (verified):
    fps=30.0: duration_sec=1.0, duration_frames=30
    fps=NaN:  duration_sec=0.0, duration_frames=30  (silent)
    fps=0.0:  duration_sec=0.0, duration_frames=30  (same)
    fps=-1.0: duration_sec=0.0, duration_frames=30  (same)

Bug class: NaN-bypass family (FO/FP/FQ/FR/FS/FT/FU tranches).
Element classification may produce wrong type (jump vs quick step) because
duration=0 misleads downstream logic.

These tests MUST fail (RED) against the current code. They assert the
CORRECT contract: NaN/negative fps → `ValueError`; valid finite fps → real
duration; `math.isfinite(fps)` guard present in source.
"""

import inspect
import math

import numpy as np
import pytest

from src.analysis.element_segmenter import ElementSegmenter


def _seg_poses(n: int = 30) -> np.ndarray:
    """A (n, 17, 2) normalized pose sequence — finite, varied."""
    rng = np.random.default_rng(0)
    return rng.standard_normal((n, 17, 2)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Observable 1: NaN fps must NOT silently coerce to 0.0; must raise.
# --------------------------------------------------------------------------- #


def test_nan_fps_raises_value_error_not_silent_zero():
    """RED: calling `_extract_segment_features(poses, fps=float('nan'))`
    must raise `ValueError`. GREEN contract: a NaN fps is corrupt input
    and must not silently produce `duration_sec=0.0` (indistinguishable
    from a legitimate fps=0 broken-header video).

    On master: `if fps > 0 else 0.0` evaluates NaN>0 as False → silently
    returns duration_sec=0.0. Test FAILS (no exception raised, duration=0).
    After fix: `math.isfinite(fps) and fps > 0` guard → raises ValueError.
    """
    seg = ElementSegmenter()
    with pytest.raises(ValueError, match=r"fps"):
        seg._extract_segment_features(_seg_poses(30), fps=float("nan"))


# --------------------------------------------------------------------------- #
# Observable 2: negative fps must raise, not coerce to 0.0.
# --------------------------------------------------------------------------- #


def test_negative_fps_raises_value_error_not_silent_zero():
    """RED: calling `_extract_segment_features(poses, fps=-1.0)` must
    raise `ValueError`. A negative fps is physically impossible
    (corrupt metadata / sign error). Must not silently produce
    `duration_sec=0.0` (indistinguishable from a legitimate fps=0
    broken-header video).

    On master: `if fps > 0 else 0.0` evaluates -1.0>0 as False → silently
    returns duration_sec=0.0. After fix: ValueError.
    """
    seg = ElementSegmenter()
    with pytest.raises(ValueError, match=r"fps"):
        seg._extract_segment_features(_seg_poses(30), fps=-1.0)


# --------------------------------------------------------------------------- #
# Observable 3: positive infinity fps must raise (math.isfinite covers it).
# --------------------------------------------------------------------------- #


def test_posinf_fps_raises_value_error():
    """RED: calling `_extract_segment_features(poses, fps=float('inf'))`
    must raise `ValueError`. `math.isfinite` rejects +inf.

    On master: `inf > 0` is True → `round(num_frames / inf, 3) = 0.0` →
    silently produces `duration_sec=0.0` again (a third silent path).
    After fix: math.isfinite guard → raises ValueError.
    """
    seg = ElementSegmenter()
    with pytest.raises(ValueError, match=r"fps"):
        seg._extract_segment_features(_seg_poses(30), fps=float("inf"))


# --------------------------------------------------------------------------- #
# Regression: valid finite fps=30 must still produce a real duration.
# --------------------------------------------------------------------------- #


def test_valid_fps_produces_real_duration_not_coerced():
    """Regression guard: fps=30 must report `duration_sec=1.0` (30/30).
    The fix must not change the valid-fps case.
    """
    seg = ElementSegmenter()
    feats = seg._extract_segment_features(_seg_poses(30), fps=30.0)
    assert math.isfinite(feats["duration_sec"]), (
        f"BUG (regression): fps=30 duration must be finite, got {feats['duration_sec']!r}."
    )
    assert feats["duration_sec"] == 1.0, (
        f"BUG (regression): fps=30, num_frames=30 → expected duration_sec=1.0, "
        f"got {feats['duration_sec']!r}. The fps guard must not change valid fps."
    )
    assert feats["duration_frames"] == 30, (
        f"BUG (regression): duration_frames must remain num_frames=30, "
        f"got {feats['duration_frames']!r}."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `math.isfinite(fps)` guard present.
# --------------------------------------------------------------------------- #


def test_source_math_isfinite_fps_guard_present():
    """GREEN contract source check: the NaN-bypass fix must add a
    `math.isfinite(fps)` guard at the function entry (not just
    `if fps > 0`, which is NaN-blind). Locks the root cause so a
    refactor cannot silently regress.
    """
    src = inspect.getsource(ElementSegmenter._extract_segment_features)
    assert "math.isfinite" in src, (
        "BUG: _extract_segment_features must reference `math.isfinite(fps)` "
        "to guard NaN/inf fps. The `if fps > 0 else 0.0` pattern is "
        "NaN-blind (NaN > 0 is False) and silently coerces NaN fps to "
        "duration_sec=0.0. Mirror PR 1043/1044 fps guard pattern."
    )
    assert "fps > 0" in src, (
        "BUG: _extract_segment_features must also reject non-positive fps "
        "(negative fps is physically impossible). Need both "
        "math.isfinite(fps) AND fps > 0."
    )
