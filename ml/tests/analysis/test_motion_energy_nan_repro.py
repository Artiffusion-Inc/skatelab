"""RED repro -> GREEN after fix: `element_segmenter._extract_segment_features`
motion_energy_* features (ml/src/analysis/element_segmenter.py:524-526) sit at
the trust boundary between analysis and ML classification (BiGRU coarse + RF
fine in ml/src/tas/). The three reductions are unguarded:

    features["motion_energy_mean"] = float(np.mean(motion_energy))   # 524
    features["motion_energy_std"] = float(np.std(motion_energy))     # 525
    features["motion_energy_max"] = float(np.max(motion_energy))     # 526

With one NaN in motion_energy, all three reductions return NaN, written to
the features dict that the element classifier consumes. Boundary effect:
- crashes the classifier (most ML libs raise on NaN), OR
- silently returns NaN confidence, OR
- silently misclassifies the element.

The upstream #922 nan_to_num at line 507 currently masks the bug by coercing
NaN keypoints to 0.0 before _compute_motion_energy. That's a fragile
defense-in-depth leak: if #922 is ever reverted, motion_energy_mean/std/max
silently become NaN at the classifier boundary. Fix: explicit
`motion_energy = motion_energy[np.isfinite(motion_energy)]` filter (or
`np.nanmean/nanstd/nanmax`) at the reduction site, mirroring the #1276
hip_y_range pattern in the same function.

3 observables (one NaN, all NaN, NaN via chain) — GREEN on master (due to
#922 upstream nan_to_num), serve as regression guards so a future revert
of #922 doesn't silently break the classifier chain.
1 regression  (valid input -> correct motion_energy_mean/std/max).
2 source checks (root cause locked via file read) — RED on master.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from src.analysis.element_segmenter import ElementSegmenter
from src.types import H36Key

# ---------------------------------------------------------------------------
# Observable 1: one frame NaN keypoint -> motion_energy_* must be finite.
# GREEN on master (upstream nan_to_num at #922 masks the bug). Locks the
# contract so a future revert of #922 doesn't silently break the classifier.
# ---------------------------------------------------------------------------


def test_motion_energy_one_nan_keypoint_is_finite() -> None:
    """One frame NaN keypoint -> motion_energy_mean/std/max must NOT be NaN.

    Without the explicit isfinite guard at lines 524-526 (relying solely on
    the #922 upstream nan_to_num), the result is fragile. With the fix
    (filter motion_energy to finite values before the reductions), the
    result is finite and reflects only valid frames.
    """
    seg = ElementSegmenter()
    poses = np.full((30, 17, 2), 0.4, dtype=np.float32)
    # Frame 5: full NaN keypoint at the hip. With #922 nan_to_num this
    # gets zeroed before _compute_motion_energy, so motion_energy stays
    # finite. Without #922 (or if the upstream guard is ever weakened),
    # motion_energy at frame 5 would be NaN.
    poses[5, H36Key.LHIP, :] = np.nan
    poses[5, H36Key.RHIP, :] = np.nan

    features = seg._extract_segment_features(poses, fps=30.0)
    for key in ("motion_energy_mean", "motion_energy_std", "motion_energy_max"):
        v = features.get(key)
        assert math.isfinite(v), (
            f"#1308: {key}={v!r} is not finite (NaN leak). NaN keypoint "
            f"propagates through _compute_motion_energy -> np.mean/std/max "
            f"absorb NaN -> float(NaN) -> NaN feature consumed by the "
            f"element classifier (BiGRU/RF in ml/src/tas/)."
        )


# ---------------------------------------------------------------------------
# Observable 2: ALL frames NaN hip -> motion_energy_* must be finite
# (sentinel 0.0, not NaN, since no valid motion exists).
# ---------------------------------------------------------------------------


def test_motion_energy_all_nan_hip_is_finite_sentinel() -> None:
    """All-NaN hip -> motion_energy_mean/std/max must be 0.0 sentinel."""
    seg = ElementSegmenter()
    poses = np.full((30, 17, 2), 0.4, dtype=np.float32)
    poses[:, H36Key.LHIP, :] = np.nan
    poses[:, H36Key.RHIP, :] = np.nan

    features = seg._extract_segment_features(poses, fps=30.0)
    for key in ("motion_energy_mean", "motion_energy_std", "motion_energy_max"):
        v = features.get(key)
        assert math.isfinite(v), (
            f"#1308: {key}={v!r} is not finite for all-NaN hip segment "
            f"(RF/BiGRU classifier breaks)."
        )


# ---------------------------------------------------------------------------
# Observable 3: NaN via chain (alternating valid/NaN frames).
# GREEN on master (upstream nan_to_num at #922 masks the bug).
# ---------------------------------------------------------------------------


def test_motion_energy_nan_via_chain_is_finite() -> None:
    """Half-NaN hip (alternating valid/NaN) -> motion_energy_* must be finite."""
    seg = ElementSegmenter()
    poses = np.full((30, 17, 2), 0.4, dtype=np.float32)
    poses[1::2, H36Key.LHIP, :] = np.nan
    poses[1::2, H36Key.RHIP, :] = np.nan

    features = seg._extract_segment_features(poses, fps=30.0)
    for key in ("motion_energy_mean", "motion_energy_std", "motion_energy_max"):
        v = features.get(key)
        assert math.isfinite(v), f"#1308: {key}={v!r} is not finite (chain NaN leak)."


# ---------------------------------------------------------------------------
# Regression: valid input -> motion_energy_mean/std/max must match direct
# reductions. PASSES on master; this is the no-regression guard for the fix.
# ---------------------------------------------------------------------------


def test_motion_energy_valid_input_byte_identical_repro() -> None:
    """Valid input: motion_energy_mean/std/max must match direct reductions.

    Locks in that the fix doesn't change behaviour for all-finite input
    (the isfinite filter / nanmean must be a no-op on finite arrays).
    """
    seg = ElementSegmenter()
    # 30 frames, smooth sinusoidal motion. With nan_to_num at #922 already
    # running, poses stay finite; _compute_motion_energy yields a finite
    # signal; mean/std/max must match direct numpy reductions.
    poses = np.full((30, 17, 2), 0.5, dtype=np.float32)
    for i in range(30):
        # Animate the right shoulder (sine wave) so diff is non-zero.
        poses[i, H36Key.RSHOULDER, 0] = 0.5 + 0.1 * np.sin(2 * np.pi * i / 30.0)

    features = seg._extract_segment_features(poses, fps=30.0)
    me = seg._compute_motion_energy(poses)
    expected_mean = float(np.mean(me))
    expected_std = float(np.std(me))
    expected_max = float(np.max(me))
    assert math.isclose(features["motion_energy_mean"], expected_mean, abs_tol=1e-5), (
        f"#1308 (regression): motion_energy_mean={features['motion_energy_mean']!r} "
        f"differs from direct np.mean={expected_mean!r}."
    )
    assert math.isclose(features["motion_energy_std"], expected_std, abs_tol=1e-5), (
        f"#1308 (regression): motion_energy_std={features['motion_energy_std']!r} "
        f"differs from direct np.std={expected_std!r}."
    )
    assert math.isclose(features["motion_energy_max"], expected_max, abs_tol=1e-5), (
        f"#1308 (regression): motion_energy_max={features['motion_energy_max']!r} "
        f"differs from direct np.max={expected_max!r}."
    )


# ---------------------------------------------------------------------------
# Source check 1: motion_energy reductions must have an explicit isfinite /
# nanmean / nanstd / nanmax guard. RED on master.
# ---------------------------------------------------------------------------


def test_source_motion_energy_has_isfinite_guard() -> None:
    """Post-fix source contract: motion_energy reductions must guard
    against NaN with `math.isfinite` filter or `np.nanmean/nanstd/nanmax`.

    FAILS on master (lines 524-526 use bare `np.mean/std/max`).
    PASSES after fix adds the guard.
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "element_segmenter.py"
    text = src_path.read_text(encoding="utf-8")
    # Locate the motion_energy reduction block.
    m = re.search(
        r"# Motion energy.*?# Hip Y trajectory",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate motion_energy reduction block in element_segmenter.py"
    body = m.group(0)
    # The fix idiom must be present on the motion_energy reductions
    # (nanmean/nanstd/nanmax OR an isfinite filter on motion_energy).
    has_guard = bool(
        re.search(
            r"np\.nanmean\(motion_energy\)|np\.nanstd\(motion_energy\)|np\.nanmax\(motion_energy\)|isfinite\(motion_energy\)",
            body,
        )
    )
    assert has_guard, (
        "#1308 unfixed: `motion_energy_mean/std/max` reductions in "
        "element_segmenter.py (lines 524-526) lack explicit isfinite / "
        "nanmean / nanstd / nanmax guard. With one NaN in motion_energy "
        "(CoM NaN, occluded keypoint, missing frame), np.mean/std/max "
        "absorb NaN -> NaN written to features dict -> consumed by the "
        "element classifier (BiGRU coarse + RF fine in ml/src/tas/). "
        "Add `motion_energy = motion_energy[np.isfinite(motion_energy)]` "
        "filter before the reductions, or use np.nanmean/nanstd/nanmax."
    )


# ---------------------------------------------------------------------------
# Source check 2: lines 524-526 must NOT be the bare `np.mean(motion_energy)`
# / `np.std(motion_energy)` / `np.max(motion_energy)` unguarded pattern.
# RED on master.
# ---------------------------------------------------------------------------


def test_source_motion_energy_not_bare_mean_std_max() -> None:
    """The bare `np.mean(motion_energy)` / `np.std(motion_energy)` /
    `np.max(motion_energy)` unguarded idioms at the motion_energy
    reduction site (lines 524-526) are the root cause. RED on master.
    PASSES after the fix replaces them with isfinite-filtered variants.

    Scope-limited to the motion_energy reduction block (between the
    "# Motion energy" and "# Hip Y trajectory" markers) so the
    `_detect_stillness` use at line 325 is not flagged (it operates
    on a different signal with its own adaptive-threshold logic).
    """
    src_path = Path(__file__).resolve().parents[2] / "src" / "analysis" / "element_segmenter.py"
    text = src_path.read_text(encoding="utf-8")
    # Locate only the motion_energy reduction block in _extract_segment_features.
    m = re.search(
        r"# Motion energy.*?# Hip Y trajectory",
        text,
        re.DOTALL,
    )
    assert m, "Could not locate motion_energy reduction block in element_segmenter.py"
    body = m.group(0)
    bare_idioms = [
        "float(np.mean(motion_energy))",
        "float(np.std(motion_energy))",
        "float(np.max(motion_energy))",
    ]
    leaks = [idiom for idiom in bare_idioms if idiom in body]
    assert not leaks, (
        f"#1308 unfixed: element_segmenter.py motion_energy reduction block "
        f"still contains the bare unguarded idioms: {leaks}. Any NaN in "
        f"motion_energy (CoM NaN, occluded keypoint, missing frame) "
        f"propagates through np.mean/std/max to the features dict "
        f"consumed by the element classifier (BiGRU/RF in ml/src/tas/). "
        f"Replace with `motion_energy = motion_energy[np.isfinite(motion_energy)]` "
        f"filter before the reductions, or use np.nanmean/nanstd/nanmax."
    )
