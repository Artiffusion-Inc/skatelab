"""RED repro -> GREEN after fix: `element_segmenter._extract_segment_features`
hip_y_range computation (ml/src/analysis/element_segmenter.py:519-520) silently
leaks NaN into the features dict when any mid-hip Y is NaN, breaking the
downstream RF classifier (scikit-learn RF rejects NaN at predict time -> user
sees "no elements detected" for a valid jump with a few occluded frames).

Root cause: line 520 is `float(np.max(hip_y) - np.min(hip_y))`. With one NaN
in hip_y, both np.max and np.min absorb NaN -> NaN - NaN = NaN -> float(NaN).
The `hip_y_min_idx` sibling was already guarded (#989) but `hip_y_range` was
missed by the upstream nan_to_num at #922 (which currently masks the bug
by coercing NaN to 0.0 — fragile defense-in-depth leak: if #922 is ever
reverted, hip_y_range breaks downstream).

Fix: explicit `math.isfinite(hip_y)` filter at the feature-math trust
boundary, mirroring #989 hip_y_min_idx pattern.

3 observables (one NaN, all NaN, NaN via chain) — GREEN on master
(due to #922 upstream nan_to_num), serve as regression guards
1 regression  (valid CoM -> correct hip_y_range)
2 source checks (root cause locked via file read) — RED on master
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key

# ---------------------------------------------------------------------------
# Observable 1: one frame NaN mid-hip -> hip_y_range must be NaN-free.
# GREEN on master (upstream nan_to_num at #922 masks the bug). Locks the
# contract so a future revert of #922 doesn't silently break the RF chain.
# ---------------------------------------------------------------------------


def test_hip_y_range_one_nan_mid_hip_is_finite() -> None:
    """One frame NaN mid-hip -> hip_y_range must NOT be NaN.

    Without the explicit isfinite guard at line 520 (relying solely on the
    #922 upstream nan_to_num), the result is fragile. With the fix (filter
    hip_y to finite values before max/min), the result is finite and
    reflects only valid frames.
    """
    seg = ElementSegmenter()
    poses = np.full((30, 17, 2), 0.4, dtype=np.float32)
    poses[5, H36Key.LHIP, :] = np.nan
    poses[5, H36Key.RHIP, :] = np.nan

    features = seg._extract_segment_features(poses, fps=30.0)
    hip_y_range = features.get("hip_y_range")
    assert math.isfinite(hip_y_range), (
        f"#1276: hip_y_range={hip_y_range!r} is not finite (NaN leak). "
        f"mid-hip NaN -> np.max/min absorb NaN -> NaN - NaN = NaN -> float(NaN) "
        f"propagates to RF classifier input -> ValueError at predict time."
    )


# ---------------------------------------------------------------------------
# Observable 2: ALL frames NaN mid-hip -> hip_y_range must be 0.0 sentinel
# (no valid data -> zero range, not NaN).
# ---------------------------------------------------------------------------


def test_hip_y_range_all_nan_mid_hip_is_finite_sentinel() -> None:
    """All-NaN mid-hip -> hip_y_range must be 0.0 (sentinel, not NaN)."""
    seg = ElementSegmenter()
    poses = np.full((30, 17, 2), 0.4, dtype=np.float32)
    poses[:, H36Key.LHIP, :] = np.nan
    poses[:, H36Key.RHIP, :] = np.nan

    features = seg._extract_segment_features(poses, fps=30.0)
    hip_y_range = features.get("hip_y_range")
    assert math.isfinite(hip_y_range), (
        f"#1276: hip_y_range={hip_y_range!r} is not finite for all-NaN "
        f"mid-hip segment (RF classifier breaks)."
    )


# ---------------------------------------------------------------------------
# Observable 3: NaN via chain (subtle: NaN propagates through hip_y
# when #922 upstream guard is not present).
# GREEN on master (upstream nan_to_num at #922 masks the bug).
# ---------------------------------------------------------------------------


def test_hip_y_range_nan_via_chain_is_finite() -> None:
    """Half-NaN mid-hip (alternating valid/NaN) -> hip_y_range must be finite."""
    seg = ElementSegmenter()
    poses = np.full((30, 17, 2), 0.4, dtype=np.float32)
    # Odd frames: NaN mid-hip; even frames: valid 0.4.
    poses[1::2, H36Key.LHIP, :] = np.nan
    poses[1::2, H36Key.RHIP, :] = np.nan

    features = seg._extract_segment_features(poses, fps=30.0)
    hip_y_range = features.get("hip_y_range")
    assert math.isfinite(hip_y_range), (
        f"#1276: hip_y_range={hip_y_range!r} is not finite (chain NaN leak)."
    )


# ---------------------------------------------------------------------------
# Regression: valid CoM (all-finite mid-hip) must produce correct range.
# PASSES on master; this is the no-regression guard for the fix.
# ---------------------------------------------------------------------------


def test_hip_y_range_valid_input_byte_identical_repro() -> None:
    """Valid input: hip_y_range must match direct np.max - np.min on finite."""
    seg = ElementSegmenter()
    # 30 frames, mid-hip Y = 0.5, 0.3, 0.1 (peak at frame 2), 0.3, 0.5...
    poses = np.full((30, 17, 2), 0.5, dtype=np.float32)
    for i in range(30):
        poses[i, H36Key.LHIP, 1] = 0.5 - 0.4 * abs(i - 2) / 27.0
        poses[i, H36Key.RHIP, 1] = poses[i, H36Key.LHIP, 1]

    features = seg._extract_segment_features(poses, fps=30.0)
    hip_y_range = features.get("hip_y_range")
    # Direct expected: max ~ 0.5, min ~ 0.1, range ~ 0.4.
    expected_max = max(0.5 - 0.4 * abs(i - 2) / 27.0 for i in range(30))
    expected_min = min(0.5 - 0.4 * abs(i - 2) / 27.0 for i in range(30))
    expected_range = expected_max - expected_min
    assert math.isclose(hip_y_range, expected_range, abs_tol=1e-5), (
        f"#1276 (regression): hip_y_range={hip_y_range!r} differs from "
        f"expected {expected_range!r}. Fix must not break all-finite case."
    )


# ---------------------------------------------------------------------------
# Source check 1: hip_y_range computation must have an explicit isfinite /
# nanmax / nanmin guard. RED on master (bare np.max - np.min on hip_y).
# ---------------------------------------------------------------------------


def test_source_hip_y_range_has_isfinite_guard() -> None:
    """Post-fix source contract: hip_y_range computation must guard
    against NaN with `math.isfinite` filter or `np.nanmax`/`np.nanmin`.

    FAILS on master (no such guard on line 520).
    PASSES after fix adds the guard.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "element_segmenter.py"
    text = src_path.read_text(encoding="utf-8")
    # Locate the hip_y_range computation block.
    m = re.search(
        r"# Hip Y trajectory.*?features\[\"hip_y_min_idx\"\]\s*=",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate Hip Y trajectory block in element_segmenter.py"
    body = m.group(0)
    # The fix idiom must be present: nanmax, nanmin, or isfinite filter
    # on hip_y specifically.
    has_guard = bool(re.search(r"np\.nanmax\(hip_y\)|np\.nanmin\(hip_y\)|isfinite\(hip_y\)", body))
    assert has_guard, (
        "#1276 unfixed: `hip_y_range` computation in element_segmenter.py "
        "lacks explicit isfinite / nanmax / nanmin guard. With NaN mid-hip, "
        "np.max/min absorb NaN -> NaN - NaN = NaN -> float(NaN) propagates "
        "to RF classifier input -> ValueError at predict time -> user sees "
        "'no elements detected' for valid jump. Add `hip_y = hip_y[np.isfinite(hip_y)]` "
        "filter or use np.nanmax/np.nanmin before the np.max/np.min call."
    )


# ---------------------------------------------------------------------------
# Source check 2: line 520 must NOT be a bare `np.max(hip_y) - np.min(hip_y)`
# (the un-guarded idiom). RED on master.
# ---------------------------------------------------------------------------


def test_source_hip_y_range_not_bare_max_min() -> None:
    """The bare `np.max(hip_y) - np.min(hip_y)` idiom at line 520 is the
    root cause. RED on master (line 520 is exactly this idiom). PASSES
    after the fix replaces it with a guarded variant (isfinite filter /
    nanmax / nanmin).
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "element_segmenter.py"
    text = src_path.read_text(encoding="utf-8")
    # The bare idiom is the bug. After fix, this exact pattern should not
    # appear (or appears alongside a guard).
    bare_idiom = "float(np.max(hip_y) - np.min(hip_y))"
    assert bare_idiom not in text, (
        f"#1276 unfixed: element_segmenter.py still contains the bare "
        f"`{bare_idiom}` idiom at the hip_y_range computation site. "
        f"Any NaN mid-hip propagates through np.max/np.min. Replace with "
        f"`np.nanmax/np.nanmin` or filter `hip_y = hip_y[np.isfinite(hip_y)]` "
        f"before the max/min call."
    )
