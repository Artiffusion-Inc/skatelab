"""RED repro for issue #968: all-NaN bone column → NaN profile + skipped
spine normalization + NaN similarity.

When a bone-length column is all-NaN in every surviving frame of the tracklet
(fully occluded limb across the whole tracklet), `np.nanmedian` emits
RuntimeWarning + returns NaN (NOT a sentinel), the spine `> 1e-6` guard
silently skips normalization (`NaN > x` is False), and `identity_similarity`
returns NaN → `max(0.0, NaN)` accidentally masks as 0.0. This file must FAIL
on master and PASS after the guard is added.
"""

from __future__ import annotations

import inspect
import warnings

import numpy as np

from src.tracking.skeletal_identity import (
    NUM_BONES,
    compute_identity_profile,
    identity_similarity,
)
from src.types import H36Key


def _finite_bones(n_frames: int = 20, bone_scale: float = 1.0) -> np.ndarray:
    """(N, NUM_BONES) all-finite bone lengths matching _make_3d_pose geometry."""
    bones = np.full((n_frames, NUM_BONES), 0.2 * bone_scale, dtype=np.float32)
    # Spine bones (idx 8, 9) — keep distinct so normalization is observable.
    bones[:, 8] = 0.15 * bone_scale  # HIP_CENTER -> THORAX
    bones[:, 9] = 0.05 * bone_scale  # THORAX -> NECK
    bones[:, 10] = 0.16 * bone_scale  # shoulder width
    bones[:, 11] = 0.10 * bone_scale  # pelvis width
    return bones


def test_compute_identity_profile_source_has_all_nan_column_guard() -> None:
    """Source-check: compute_identity_profile + identity_similarity guard
    all-NaN columns and NaN norms (root-cause lock). Fails on master."""
    src = inspect.getsource(compute_identity_profile)
    sim_src = inspect.getsource(identity_similarity)
    # Master has bare `np.nanmedian(bones, axis=0)` with no all-NaN column guard.
    assert "np.nanmedian" in src, "nanmedian still used (regression check)"
    # Must guard all-NaN columns: isfinite / nan_to_num / all(isnan) fill.
    assert (
        "np.isfinite" in src
        or "nan_to_num" in src
        or "np.all(np.isnan" in src
        or "np.isnan(bones).all" in src
    ), "compute_identity_profile must guard all-NaN bone columns"
    # Spine guard must check isfinite, not bare `spine > 1e-6` (NaN-unsafe).
    assert "isfinite" in src, "spine normalization must guard NaN via isfinite"
    # identity_similarity must fail-closed on NaN norm explicitly.
    assert "isfinite" in sim_src or "np.isnan" in sim_src, (
        "identity_similarity must NaN-guard norms explicitly (fail closed)"
    )


def test_all_nan_bone_column_profile_is_finite_not_nan() -> None:
    """All-NaN bone column → finite profile entry (sentinel 0.0), no NaN leak."""
    bones = _finite_bones()
    bones[:, 4] = np.nan  # humerus R fully occluded across all frames
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)  # All-NaN slice → error
        profile = compute_identity_profile(bones)
    assert profile.shape == (NUM_BONES,)
    # Finite sentinel (0.0) for the occluded bone, NOT NaN.
    assert np.isfinite(profile).all(), f"NaN leaked into profile: {profile}"
    assert profile[4] == 0.0, f"expected sentinel 0.0 for all-NaN bone, got {profile[4]}"


def test_all_nan_spine_bone_column_normalization_not_skipped() -> None:
    """Spine bone all-NaN → normalization must NOT silently skip and return
    un-normalized (raw) non-spine bones. Profile entries finite and normalized
    (not raw 2.0 magnitudes)."""
    bones = _finite_bones()
    bones[:, 8] = np.nan  # spine lower fully occluded
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        profile = compute_identity_profile(bones)
    assert np.isfinite(profile).all(), f"NaN in profile: {profile}"
    # If normalization were skipped, femur (0.2) / surviving-spine (0.05) would
    # stay raw. Normalized profile divides by the surviving spine sum, so the
    # femur ratio is ~0.2 / 0.05 = 4.0, not 0.2. Either way it must be finite
    # and NOT the raw 0.2 magnitude (which signals skipped normalization).
    assert profile[0] != 0.2, f"normalization skipped — femur stays raw 0.2: {profile}"


def test_identity_similarity_nan_profile_finite_not_nan() -> None:
    """identity_similarity with a NaN-poisoned profile must return a finite
    float (fail closed 0.0), NOT NaN. Locks the `max(0.0, NaN)=0.0` arg-order
    accident vs `max(NaN, 0.0)=NaN` — explicit guard, not comparison semantics."""
    bones_a = _finite_bones()
    bones_b = _finite_bones()
    bones_b[:, 4] = np.nan  # all-NaN column in candidate
    profile_a = compute_identity_profile(bones_a)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        profile_b = compute_identity_profile(bones_b)
    sim = identity_similarity(profile_a, profile_b)
    assert isinstance(sim, float)
    assert np.isfinite(sim), f"similarity is NaN (not fail-closed): {sim}"
    assert sim == 0.0 or 0.0 <= sim <= 1.0, f"similarity out of [0,1]: {sim}"


def test_all_nan_all_bones_defined_behavior_no_crash() -> None:
    """Every bone column all-NaN (whole tracklet occluded) — defined behavior:
    finite profile, similarity 0.0 vs a finite reference, no crash, no NaN."""
    bones = np.full((20, NUM_BONES), np.nan, dtype=np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        profile = compute_identity_profile(bones)
    assert profile.shape == (NUM_BONES,)
    assert np.isfinite(profile).all(), f"NaN in all-occluded profile: {profile}"
    ref = compute_identity_profile(_finite_bones())
    sim = identity_similarity(profile, ref)
    assert np.isfinite(sim), f"similarity NaN vs finite ref: {sim}"


def test_partial_nan_bone_column_profile_finite_regression() -> None:
    """Regression: partial-NaN column (some frames NaN, not all) → nanmedian
    skips NaN frames → finite profile. Fix must not break partial-occlusion."""
    bones = _finite_bones()
    bones[:5, 4] = np.nan  # 5/20 frames NaN — NOT all-NaN column
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        profile = compute_identity_profile(bones)
    assert np.isfinite(profile).all(), f"partial NaN broke: {profile}"
    # Humerus 0.2 normalized by spine sum 0.2 → 1.0; partial NaN frames skipped
    # by nanmedian, so the median stays 0.2 → normalized 1.0 (regression lock).
    assert abs(profile[4] - 1.0) < 1e-4, f"partial-NaN median wrong: {profile[4]}"


def test_all_finite_bones_unchanged_regression() -> None:
    """All-finite bones → profile unchanged (regression)."""
    bones = _finite_bones()
    profile = compute_identity_profile(bones)
    # Spine sum = 0.15 + 0.05 = 0.2 → femur 0.2 / 0.2 = 1.0
    assert np.isfinite(profile).all()
    assert abs(profile[0] - 1.0) < 1e-5, f"all-finite normalization changed: {profile[0]}"
