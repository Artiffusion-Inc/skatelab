"""RED repro — `pixel_to_normalized` NaN/zero/negative width/height silently
coerced to 0.5 (tranche FX).

Bug: ml/src/visualization/core/geometry.py:94-125 `pixel_to_normalized` has
  FOUR NaN-blind `width > 0` and `height > 0` guards:

      line 117:  `result[..., 0] = result[..., 0] / width if width > 0 else 0.5`
      line 118:  `result[..., 1] = result[..., 1] / height if height > 0 else 0.5`
      line 123:  `x_norm = x / width if width > 0 else 0.5`
      line 124:  `y_norm = y / height if height > 0 else 0.5`

  NaN is NOT > 0 (NaN > 0 evaluates to False), so a NaN width/height
  bypasses the guard and falls into the `else 0.5` branch — silently
  coercing to frame center. The same happens for negative width/height
  (e.g. -1 > 0 is False → 0.5). This is INDISTINGUISHABLE from a legitimate
  width=0 (also returns 0.5).

  Concretely:
      pixel_to_normalized([100, 200], 1920, 1080) → (0.052, 0.185)  (correct)
      pixel_to_normalized([100, 200], NaN, 1080)   → (0.5,   0.185)  (silent)
      pixel_to_normalized([100, 200], 0,   1080)   → (0.5,   0.185)  (same)
      pixel_to_normalized([100, 200], -1,  1080)   → (0.5,   0.185)  (negative)

  Prod impact: NaN/negative width/height is a common bug class
  (corrupt video metadata, uninitialized frame size, negative crop
  artifact). The silent coerce to 0.5 collapses the entire UI
  (skeleton, HUD, comparison, 3D export, axis endpoints, bounding box)
  to frame center with NO error.

  There is NO `math.isfinite(width) and width > 0` (or equivalent) guard.
  The four `width > 0` / `height > 0` comparisons are NaN-blind: NaN > 0
  is False (IEEE 754), so NaN takes the `else 0.5` branch.

Fix (NOT applied — repro only):
  At function entry, guard width/height with `math.isfinite(width) and
  width > 0` (and same for height) → raise `ValueError(f"width must be
  finite and > 0, got {width}")` (or `height`). The function must reject
  NaN, negative, and zero width/height at the trust boundary; the silent
  0.5 coerce masks the real bug upstream and corrupts rendering.

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — finite width/height → finite normalized output)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `pixel_to_normalized` is pure-numpy + int
cast. We feed synthetic NaN/zero/negative width/height scalars to
isolate the silent coerce.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from src.visualization.core.geometry import pixel_to_normalized

# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_pixel_to_normalized_has_isfinite_guard_on_width_height():
    """GREEN contract source check: `pixel_to_normalized` guards width/height
    with `math.isfinite(width) and width > 0` (and same for height) at function
    entry. The unfixed function only checks `width > 0` (and `height > 0`),
    which is NaN-blind (NaN > 0 is False → falls into the `else 0.5` branch).
    """
    src = inspect.getsource(pixel_to_normalized)

    # The NaN-blind `if width > 0 else 0.5` and `if height > 0 else 0.5`
    # patterns must be GONE on fix.
    assert "if width > 0 else 0.5" not in src, (
        "pixel_to_normalized still has the NaN-blind `if width > 0 else 0.5` "
        "guard — root cause not fixed. Replace with `math.isfinite(width) and "
        "width > 0` so NaN/negative width raises instead of silently coercing "
        "to 0.5."
    )
    assert "if height > 0 else 0.5" not in src, (
        "pixel_to_normalized still has the NaN-blind `if height > 0 else 0.5` "
        "guard — root cause not fixed. Replace with `math.isfinite(height) and "
        "height > 0` so NaN/negative height raises instead of silently coercing "
        "to 0.5."
    )
    # GREEN: the function now uses `math.isfinite(...) and ... > 0` to guard
    # both width and height.
    assert "math.isfinite(width) and width > 0" in src, (
        "pixel_to_normalized must guard `width` with "
        "`math.isfinite(width) and width > 0` at function entry. The unfixed "
        "function uses NaN-blind `width > 0` (NaN > 0 is False → silent 0.5)."
    )
    assert "math.isfinite(height) and height > 0" in src, (
        "pixel_to_normalized must guard `height` with "
        "`math.isfinite(height) and height > 0` at function entry. The unfixed "
        "function uses NaN-blind `height > 0` (NaN > 0 is False → silent 0.5)."
    )


# =============================================================================
# Observable 1 — BUG: NaN width silently coerces to 0.5 (frame center) —
# INDISTINGUISHABLE from a legitimate width=0. Both produce x=0.5, so a
# caller cannot tell a real NaN bug from an intentional zero. The fix
# must raise ValueError on NaN width (NOT silently coerce).
# =============================================================================


def test_nan_width_raises_not_silent_half():
    """BUG: `pixel_to_normalized` scalar path with NaN width silently
    returns `(0.5, ...)` — visually collapses the entire UI to frame
    center with no error. The fix must raise ValueError on NaN width.

    PASS on unfixed code (returns (0.5, ...), no exception). A fix →
    ValueError raised → assert FAILS → GREEN contract. Locks the silent
    NaN→0.5 coerce.
    """
    nan = float("nan")
    raised = False
    try:
        _ = pixel_to_normalized((100, 200), nan, 1080)  # type: ignore[arg-type]
    except ValueError:
        raised = True

    # BUG: NaN width silently returns (0.5, ...), no exception.
    assert raised, (
        "BUG: pixel_to_normalized with NaN width silently returned (0.5, "
        "...) — no ValueError raised. NaN width corrupts rendering "
        "(skeleton / HUD / 3D endpoints collapse to frame center) and is "
        "INDISTINGUISHABLE from a legitimate width=0. The fix must raise "
        "ValueError on NaN width so the upstream bug surfaces."
    )


# =============================================================================
# Observable 2 — BUG: NaN height = 0 height = (..., 0.5). Same silent
# coerce, same fix: raise ValueError on NaN height at function entry.
# =============================================================================


def test_nan_height_raises_value_error():
    """BUG: `pixel_to_normalized` scalar path with NaN height silently returns
    `(..., 0.5)`. A fix must raise ValueError on NaN height.

    PASS on unfixed code (returns (..., 0.5), no exception). A fix →
    ValueError raised → assert FAILS → GREEN contract.
    """
    nan = float("nan")
    raised = False
    try:
        _ = pixel_to_normalized((100, 200), 1920, nan)  # type: ignore[arg-type]
    except ValueError:
        raised = True

    # BUG: NaN height silently returns (..., 0.5), no exception.
    assert raised, (
        "BUG: pixel_to_normalized with NaN height returned (..., 0.5) "
        "silently — no ValueError raised. NaN height corrupts rendering. "
        "The fix must raise ValueError on NaN height so the upstream bug "
        "surfaces."
    )


# =============================================================================
# Observable 3 — BUG: zero/negative width/height also bypass the guard
# (`0 > 0` is False → 0.5; `-1 > 0` is False → 0.5). The fix must raise
# ValueError for any non-finite-or-positive width/height at the trust
# boundary.
# =============================================================================


def test_zero_and_negative_width_height_raise_value_error():
    """BUG: `pixel_to_normalized` scalar path with width=0 or width=-1
    silently returns `(0.5, ...)`. The NaN-blind `width > 0` guard treats
    0 and negative identically to NaN. A fix must raise ValueError for all
    invalid width/height (NaN, 0, negative).

    PASS on unfixed code (silent coerce). A fix → ValueError → assert
    FAILS → GREEN contract. Locks the zero/negative coerce.
    """
    # Pair each bad width with a valid height, and vice versa. The bad
    # value must trigger the raise (the guard is on width and height
    # independently).
    cases = [
        # (width, height, bad_dim)
        (0, 1080, "width"),
        (-1, 1080, "width"),
        (-1920, 1080, "width"),
        (1920, 0, "height"),
        (1920, -1, "height"),
        (1920, -1080, "height"),
    ]
    for w, h, bad_dim in cases:
        raised = False
        try:
            _ = pixel_to_normalized((100, 200), w, h)
        except ValueError:
            raised = True

        # BUG: zero/negative width or height silently returns 0.5.
        assert raised, (
            f"BUG: pixel_to_normalized with bad {bad_dim} (w={w}, h={h}) "
            f"silently returned 0.5 (no ValueError). The fix must raise "
            f"ValueError on invalid width/height at the trust boundary "
            f"(NaN, 0, negative)."
        )


# =============================================================================
# Regression — PASS: a finite width/height → finite normalized output. The
# fix (isfinite guard raising on invalid) must NOT regress the finite path.
# =============================================================================


def test_finite_width_height_returns_finite_normalized():
    """NOT a bug: a finite width/height (1920, 1080) → finite normalized
    output (0.052, 0.185) for pixel (100, 200). Regression guard so the
    isfinite guard fix does not break the finite path.
    """
    out_scalar = pixel_to_normalized((100, 200), 1920, 1080)
    assert out_scalar == (pytest.approx(100 / 1920), pytest.approx(200 / 1080)), (
        f"BUG (regression): finite width/height (1920, 1080) → {out_scalar} "
        f"(expected ({100 / 1920:.6f}, {200 / 1080:.6f})). The finite path must "
        f"return the correctly-scaled normalized tuple. An isfinite guard fix "
        f"must not regress this."
    )

    # Also regression for the vectorized path.
    arr = np.array([[100, 200], [960, 540], [1920, 1080]], dtype=np.float32)
    out_arr = pixel_to_normalized(arr, 1920, 1080)
    expected = np.array(
        [[100 / 1920, 200 / 1080], [0.5, 0.5], [1.0, 1.0]],
        dtype=np.float32,
    )
    assert np.allclose(np.asarray(out_arr), expected, atol=1e-5), (
        f"BUG (regression): vectorized finite path → {out_arr} (expected "
        f"{expected}). The finite vectorized path must return the correctly-"
        f"scaled normalized array. An isfinite guard fix must not regress this."
    )
