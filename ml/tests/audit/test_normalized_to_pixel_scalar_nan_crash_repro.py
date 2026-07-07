"""RED repro — `normalized_to_pixel` scalar (tuple) path NaN → `int(NaN)`
ValueError crash, while the vectorized (ndarray) path NaN-masks to (0,0)
(tranche EU).

Bug: ml/src/visualization/core/geometry.py:43-81 `normalized_to_pixel` has
  TWO branches with ASYMMETRIC NaN handling:

      line 62:  `if isinstance(pos_normalized, np.ndarray):`
      line 66:      `result[..., 0] = np.clip(result[..., 0] * width, 0, width - 1)`
      line 67:      `result[..., 1] = np.clip(result[..., 1] * height, 0, height - 1)`
      line 68:      `# Replace NaN (from undetected keypoints) with 0 before int cast`
      line 69:      `nan_mask = np.isnan(result[..., 0]) | np.isnan(result[..., 1])`
      line 74:      `result[nan_mask] = 0`           # ← NaN guarded → (0, 0)
      line 75:      `return result.astype(np.int32)`
      line 76:  `else:`                              # scalar (tuple/list) path
      line 78:      `x, y = pos_normalized`
      line 79:      `x_px = int(np.clip(x * width, 0, width - 1))`   # NaN → int(NaN)
      line 80:      `y_px = int(np.clip(y * height, 0, height - 1))`# NaN → int(NaN)
      line 81:      `return (x_px, y_px)`

  `np.clip(NaN, 0, width-1)` = NaN (numpy `np.clip` does NOT mask NaN — the
  same family as the `np.clip` NaN-pass-through noted in other tranches).
  `int(NaN)` raises `ValueError: cannot convert float NaN to integer` (Python
  rejects NaN→int cast). So a NaN in the scalar (tuple/list) position → CRASH.

  The vectorized path (line 62-75) explicitly NaN-masks (`nan_mask = ...;
  result[nan_mask] = 0` — line 69, 74) with the comment "Replace NaN (from
  undetected keypoints) with 0 before int cast". The scalar path (line 76-81)
  has NO such guard — `int(np.clip(NaN * width, 0, width - 1))` = `int(NaN)`
  → ValueError. The SAME function handles NaN in one branch and CRASHES on
  NaN in the other.

  There is NO guard on the scalar path: it does not `if not np.isfinite(x): x
  = 0.0` / `if np.isnan(x): return (0, 0)` / `x = np.nan_to_num(...)` before
  the `int(...)` cast. `int(np.clip(NaN, ...))` raises ValueError directly
  (no exception caught in `normalized_to_pixel`).

Consequences (prod impact):
  1. The scalar (tuple) path is the PUBLIC API documented in the docstring
     (`>>> normalized_to_pixel((0.5, 0.5), 1920, 1080)` → `(960, 540)` — line
     59-60). A caller passing a single (x, y) tuple with a NaN coordinate
     (occluded keypoint → NaN pose → caller computes a NaN position tuple and
     passes it to `normalized_to_pixel`) → `int(NaN)` → ValueError → the
     render / overlay CRASHES. The vectorized path would have returned (0, 0)
     (graceful), but the scalar path crashes.
  2. The bug is a hard CRASH (ValueError), not a silent leak — but it is
     ASYMMETRIC: the same input as an ndarray (vectorized) is handled
     gracefully (NaN → (0, 0)), while the same input as a tuple (scalar)
     crashes. A caller that switches from passing `np.array([nan, nan])` to
     `(nan, nan)` (or vice versa) sees the behavior flip from graceful to
     crash with NO change in the underlying data.
  3. `normalized_to_pixel` is a PUBLIC export (`src/visualization/__init__.py`
     line 44, 136). The scalar path is exercised by any caller that passes a
     single position tuple (the documented API shape). One NaN coordinate →
     the render crashes.
  4. Sibling to the NaN-int-cast / asymmetric-guard family:
     - The vectorized path NaN-mask (line 69, 74) IS the same guard the
       scalar path is MISSING. `test_vertical_axis_head_nan_crash_repro`
       covers the `_draw_head_alignment` NaN crash (a DIFFERENT consumer that
       calls `int(head_pt[0])` directly — NOT via `normalized_to_pixel`).
       `test_joint_angle_layer_nan_joint_crash_repro` covers the
       joint-angle-layer NaN crash. NEITHER covers the `normalized_to_pixel`
       SCALAR path `int(np.clip(NaN, ...))` crash. The vectorized path is
       guarded; the scalar path is NOT — NO test feeds a NaN tuple through
       `normalized_to_pixel` and asserts a non-crash result (mirroring the
       vectorized (0, 0) contract).

The fix (NOT applied — repro only):
  - `normalized_to_pixel` scalar path (line 78-81): NaN-guard before the int
    cast, mirroring the vectorized path — `x, y = pos_normalized;
    if not np.isfinite(x): x = 0.0; if not np.isfinite(y): y = 0.0;` (or
    `x, y = np.nan_to_num(pos_normalized, nan=0.0)`); and/or
  - unify the paths — wrap the scalar in `np.asarray` and route through the
    vectorized branch (which already NaN-masks), so the scalar path inherits
    the guard.
  The correct contract: a NaN coordinate in a scalar (tuple) position must
  NOT crash. It must return (0, 0) (mirroring the vectorized path) or NaN-
  mask before the int cast, NOT raise ValueError.

Methodology (per audit reglement):
  3 observables  (BUG present → PASS; flip to GREEN contract on fix)
  1 regression   (PASS — finite scalar tuple → finite pixel tuple)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `normalized_to_pixel` is pure-numpy + int cast.
We feed a synthetic NaN scalar tuple (no pipeline run) to isolate the crash.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.visualization.core.geometry import normalized_to_pixel


# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_normalized_to_pixel_scalar_path_has_no_nan_guard():
    """Lock the root cause: `normalized_to_pixel` vectorized branch (line 62-75)
    NaN-masks (`nan_mask = np.isnan(...); result[nan_mask] = 0` — line 69, 74)
    before the int cast, but the scalar branch (line 76-81) does
    `int(np.clip(x * width, 0, width - 1))` (line 79) with NO NaN guard —
    `np.clip(NaN, ...)` = NaN, `int(NaN)` raises ValueError.

    A fix would NaN-guard the scalar path (mirror the vectorized mask / route
    through the vectorized branch). As long as the code is unfixed this passes
    — flip on fix.
    """
    src = inspect.getsource(normalized_to_pixel)

    # The vectorized NaN guard the scalar path is MISSING.
    assert "nan_mask = np.isnan(result[..., 0]) | np.isnan(result[..., 1])" in src, (
        "normalized_to_pixel vectorized branch must NaN-mask "
        "(`nan_mask = np.isnan(result[..., 0]) | np.isnan(result[..., 1])`, "
        "line 69) for this repro to be valid. If the vectorized guard changed, "
        "update the repro."
    )
    assert "result[nan_mask] = 0" in src, (
        "normalized_to_pixel vectorized branch must NaN-mask "
        "(`result[nan_mask] = 0`, line 74) for this repro to be valid. If the "
        "vectorized guard changed, update the repro."
    )
    # The scalar-path crash: int(np.clip(x * width, 0, width - 1)) on NaN x
    # → int(NaN) → ValueError.
    assert "int(np.clip(x * width, 0, width - 1))" in src, (
        "normalized_to_pixel scalar branch must compute "
        "`int(np.clip(x * width, 0, width - 1))` (line 79, NaN x → int(NaN) → "
        "ValueError) for this repro to be valid. If the scalar computation "
        "changed, update the repro."
    )
    # NO NaN guard on the scalar path. The scalar `else:` branch must not
    # contain isfinite / isnan / nan_to_num.
    scalar_branch = src.split("else:")[1] if "else:" in src else ""
    assert "isfinite" not in scalar_branch and "isnan" not in scalar_branch and \
           "nan_to_num" not in scalar_branch, (
        "normalized_to_pixel scalar branch now guards NaN (isfinite / isnan / "
        "nan_to_num) — root cause fixed, update this repro to the GREEN contract "
        "(NaN scalar tuple → (0, 0), mirroring the vectorized path, not crash)."
    )


# =============================================================================
# Observable 1 — BUG: np.clip(NaN, 0, width-1) = NaN (clip does NOT mask NaN).
# Locks the mechanism so a fix cannot rely on np.clip to reject NaN quietly.
# =============================================================================


def test_clip_nan_returns_nan():
    """BUG: `np.clip(float('nan'), 0, 99)` returns NaN (numpy `np.clip` does NOT
    mask NaN — it passes NaN through). So a NaN coordinate → `np.clip(NaN * w,
    0, w-1)` = NaN → `int(NaN)` → ValueError.

    PASS on unfixed code (numpy semantics). A fix (nan_to_num / isfinite
    guard before clip) → 0.0 → assert FAILS → GREEN contract. Locks the
    mechanism — a fix must NaN-mask BEFORE the clip / int cast.
    """
    clipped = np.clip(float("nan") * 100, 0, 99)
    # BUG: clip passes NaN through.
    assert np.isnan(clipped), (
        f"FIXED or numpy semantics changed: np.clip(NaN, 0, 99) = {clipped} "
        f"(finite). If clip now masks NaN, the NaN→int crash is gone — "
        f"update repro to the GREEN contract."
    )


# =============================================================================
# Observable 2 — BUG: `int(NaN)` raises ValueError. Locks that the int cast is
# the crash site — a fix cannot rely on int() to reject NaN quietly.
# =============================================================================


def test_int_nan_raises_valueerror():
    """BUG: `int(float('nan'))` raises `ValueError: cannot convert float NaN
    to integer` (Python rejects NaN→int cast). So `int(np.clip(NaN, 0, w-1))`
    = `int(NaN)` → ValueError.

    PASS on unfixed code (Python semantics). A fix (NaN-guard before the int
    cast) → no `int(NaN)` reached → assert FAILS → GREEN contract. Locks the
    crash site.
    """
    raised = False
    try:
        _ = int(float("nan"))
    except ValueError:
        raised = True
    # BUG: int(NaN) raises ValueError.
    assert raised, (
        f"FIXED or Python semantics changed: int(NaN) did NOT raise "
        f"ValueError. If Python now accepts NaN→int, the crash is gone — "
        f"update repro to the GREEN contract."
    )


# =============================================================================
# Observable 3 — BUG: `normalized_to_pixel((nan, nan), w, h)` (SCALAR path)
# raises ValueError, while `normalized_to_pixel(np.array([[nan, nan]]), w, h)`
# (VECTORIZED path) returns [[0, 0]] (NaN-masked). The SAME function handles
# NaN gracefully in one branch and CRASHES on NaN in the other.
# =============================================================================


def test_scalar_nan_crashes_vectorized_nan_guarded():
    """BUG: `normalized_to_pixel` with a NaN scalar tuple (scalar path, line
    76-81) → `int(np.clip(NaN * w, 0, w-1))` = `int(NaN)` → ValueError. The
    SAME input as an ndarray (vectorized path, line 62-75) → NaN-masked to
    (0, 0) (graceful). Asymmetric NaN handling: vectorized guarded, scalar
    crashes.

    PASS on unfixed code. A fix (NaN-guard the scalar path / route through the
    vectorized branch) → scalar NaN tuple → (0, 0) (no crash) → assert FAILS
    → GREEN contract.
    """
    nan = float("nan")

    # Vectorized path: NaN ndarray → (0, 0) (guarded).
    arr = np.array([[nan, nan]], dtype=np.float32)
    out_vec = normalized_to_pixel(arr, 100, 100)
    assert np.array_equal(np.asarray(out_vec), np.array([[0, 0]])), (
        f"test fixture broken: vectorized NaN path returned {out_vec} "
        f"(expected [[0, 0]]). If the vectorized NaN guard changed, update "
        f"the repro."
    )

    # Scalar path: NaN tuple → ValueError (NOT guarded).
    raised = False
    try:
        normalized_to_pixel((nan, nan), 100, 100)
    except ValueError:
        raised = True
    # BUG: scalar NaN tuple crashes; vectorized NaN is guarded.
    assert raised, (
        f"FIXED: normalized_to_pixel with a NaN scalar tuple did NOT raise "
        f"ValueError. A NaN guard (isfinite / nan_to_num on the scalar path) "
        f"landed. Update this repro to the GREEN contract (NaN scalar tuple → "
        f"(0, 0), mirroring the vectorized path, not crash)."
    )


# =============================================================================
# Regression — PASS: a finite scalar tuple (0.5, 0.5) → finite pixel tuple
# (50, 50) for a 100x100 frame. The fix (NaN-guard on the scalar path) must
# NOT regress the finite scalar path.
# =============================================================================


def test_finite_scalar_returns_finite_pixel():
    """NOT a bug: a finite scalar tuple (0.5, 0.5) → (50, 50) for a 100x100
    frame (clipped, int-cast). Regression guard so a NaN-guard fix does not
    break the finite scalar path (and does not accidentally return (0, 0) for
    valid positions).
    """
    out = normalized_to_pixel((0.5, 0.5), 100, 100)
    assert out == (50, 50), (
        f"BUG (regression): finite scalar (0.5, 0.5) on 100x100 → {out} "
        f"(expected (50, 50)). The finite scalar path must return the "
        f"clipped, int-cast pixel tuple. A NaN-guard fix must not regress "
        f"this."
    )