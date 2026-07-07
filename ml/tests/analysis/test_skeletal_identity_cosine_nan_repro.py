"""RED repro for issue #1225: skeletal identity cosine NaN norm silently
propagates to dot/div.

Source: `ml/src/tracking/skeletal_identity.py:identity_similarity` — the
unfixed cosine similarity is:

    norm_a = np.linalg.norm(profile_a)
    norm_b = np.linalg.norm(profile_b)
    if norm_a < 1e-8 or norm_b < 1e-8:        # NaN < x == False
        return 0.0
    return float(np.dot(profile_a, profile_b) / (norm_a * norm_b))

When either profile contains a NaN, the norm is NaN, `NaN < 1e-8` is False
(the guard silently fails to fire), and the dot/(norm*norm) returns NaN.
NaN similarity then propagates to Re-ID callers (tracklet merger) and
silently corrupts the merged track — `max(0.0, NaN) == 0.0` is an
arg-order accident, not a guarantee.

Fix: explicit `np.isfinite(norm_a) and np.isfinite(norm_b)` check before
the `norm < 1e-8` guard. NaN/inf norm -> 0.0 (fail closed).

3 observables (NaN norm, inf norm, NaN in both profiles) — must NOT
return NaN.
1 regression (valid cosine of identical profile == 1.0) — locks the
no-regression case.
1 source check — `identity_similarity` must guard NaN/inf norm explicitly.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.tracking.skeletal_identity import identity_similarity

# 12-bone profile matching NUM_BONES = 12 in skeletal_identity.py.
_VALID = np.array(
    [0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.15, 0.05, 0.16, 0.10],
    dtype=np.float32,
)


# ---------------------------------------------------------------------------
# Observable 1: NaN in profile_a -> norm_a is NaN -> similarity must be 0.0,
# not NaN. Root cause lock for the unfixed code path.
# ---------------------------------------------------------------------------


def test_cosine_nan_norm_in_profile_a_returns_finite_zero() -> None:
    """NaN in profile_a -> norm_a is NaN -> similarity must NOT be NaN.

    Unfixed: `NaN < 1e-8 == False` -> guard skipped -> `dot/NaN` returns
    NaN -> similarity is NaN -> Re-ID silently corrupts merged track.
    Fixed: explicit isfinite guard -> similarity == 0.0 (fail closed).
    """
    profile_a = _VALID.copy()
    profile_a[4] = np.nan  # poison one bone
    sim = identity_similarity(profile_a, _VALID)
    assert isinstance(sim, float)
    assert np.isfinite(sim), (
        f"#1225: similarity={sim!r} is not finite (NaN norm leaked into "
        f"dot/div). Unfixed: `NaN < 1e-8` is False so the guard skips and "
        f"dot/NaN returns NaN. Re-ID then propagates the NaN to the "
        f"tracklet merger."
    )
    assert sim == 0.0, f"#1225: NaN norm must map to 0.0, got {sim}"


# ---------------------------------------------------------------------------
# Observable 2: NaN in profile_b -> same root cause, symmetric path.
# ---------------------------------------------------------------------------


def test_cosine_nan_norm_in_profile_b_returns_finite_zero() -> None:
    """NaN in profile_b -> norm_b is NaN -> similarity must NOT be NaN.

    Symmetric to observable 1. Locks both sides of the comparison.
    """
    profile_b = _VALID.copy()
    profile_b[7] = np.nan
    sim = identity_similarity(_VALID, profile_b)
    assert isinstance(sim, float)
    assert np.isfinite(sim), f"#1225: similarity={sim!r} is not finite (NaN in profile_b leaked)."
    assert sim == 0.0, f"#1225: NaN norm must map to 0.0, got {sim}"


# ---------------------------------------------------------------------------
# Observable 3: NaN in BOTH profiles -> norm_a * norm_b = NaN -> both branches
# of the comparison must still return a finite 0.0.
# ---------------------------------------------------------------------------


def test_cosine_nan_norm_in_both_profiles_returns_finite_zero() -> None:
    """NaN in both profiles -> both norms NaN -> similarity must be 0.0.

    Even if only one side were guarded, the unguarded side would still
    leak NaN. The fix must cover both.
    """
    profile_a = _VALID.copy()
    profile_a[2] = np.nan
    profile_b = _VALID.copy()
    profile_b[9] = np.nan
    sim = identity_similarity(profile_a, profile_b)
    assert isinstance(sim, float)
    assert np.isfinite(sim), f"#1225: similarity={sim!r} not finite with NaN in both profiles."
    assert sim == 0.0, f"#1225: NaN norm in both must map to 0.0, got {sim}"


# ---------------------------------------------------------------------------
# Observable 4: +inf norm (overflow in profile magnitudes) -> similarity
# must NOT be NaN/Inf. Unfixed: norm*norm = Inf, dot/Inf could be 0 or NaN.
# ---------------------------------------------------------------------------


def test_cosine_inf_norm_returns_finite_zero() -> None:
    """Inf in profile -> norm is Inf -> similarity must NOT be NaN/Inf.

    Unfixed: norm*norm = Inf, dot/Inf could be NaN (if dot is also Inf
    or finite with opposite sign) or finite 0.0. Either way the unfixed
    `Inf < 1e-8` is False, so the zero-vector guard silently fails and
    the result is undefined. Fixed: explicit isfinite -> 0.0.
    """
    profile_a = _VALID.copy()
    profile_a[0] = np.inf
    sim = identity_similarity(profile_a, _VALID)
    assert isinstance(sim, float)
    assert np.isfinite(sim), f"#1225: similarity={sim!r} not finite with Inf norm."
    assert sim == 0.0, f"#1225: Inf norm must map to 0.0, got {sim}"


# ---------------------------------------------------------------------------
# Regression: identical valid profiles -> cosine == 1.0. The fix must not
# break the all-finite happy path.
# ---------------------------------------------------------------------------


def test_cosine_identical_valid_profiles_returns_one_regression() -> None:
    """Identical valid profiles -> similarity must be 1.0 (regression)."""
    sim = identity_similarity(_VALID, _VALID)
    assert isinstance(sim, float)
    assert np.isfinite(sim)
    assert abs(sim - 1.0) < 1e-5, (
        f"#1225 (regression): identical profiles must give similarity=1.0, "
        f"got {sim}. Fix must not break the all-finite happy path."
    )


# ---------------------------------------------------------------------------
# Source check: identity_similarity must guard NaN/inf norm explicitly
# (np.isfinite, np.isnan, or nan_to_num). The unfixed code only had
# `norm < 1e-8` which is NaN-unsafe (NaN < x is False).
# ---------------------------------------------------------------------------


def test_source_identity_similarity_has_isfinite_norm_guard() -> None:
    """Post-fix source contract: `identity_similarity` must guard NaN/inf
    norms explicitly. Locks the root cause so a future revert doesn't
    silently regress to NaN-leaking behavior.
    """
    src = inspect.getsource(identity_similarity)
    assert "isfinite" in src or "isnan" in src or "nan_to_num" in src, (
        "#1225 unfixed: `identity_similarity` does not guard NaN/inf "
        "norms explicitly. The unfixed `norm_a < 1e-8` idiom is NaN-unsafe "
        "(NaN < x is False) so the zero-vector guard silently fails and "
        "the dot/(norm*norm) returns NaN -> Re-ID propagates NaN to the "
        "tracklet merger. Add `if not np.isfinite(norm_a) or not "
        "np.isfinite(norm_b): return 0.0` before the `norm < 1e-8` check."
    )
