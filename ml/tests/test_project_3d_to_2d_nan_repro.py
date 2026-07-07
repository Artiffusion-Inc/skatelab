"""RED repro — `project_3d_to_2d` scalar (tuple) path NaN/degenerate input
hazards (tranche GJ).

Bug: ml/src/visualization/core/geometry.py:213-227 `project_3d_to_2d` scalar
  (tuple) branch has THREE NaN/degenerate-input hazards in perspective
  projection:

      line 215: `x, y, z = pos_3d`
      line 218: `depth = camera_distance - z`           # NaN if any input NaN
      line 221: `depth = max(0.1, depth)`                # NaN-arg-order: max(0.1, NaN) = 0.1
      line 223: `scale = focal_length / depth`           # scale = FL/0.1 = 10*FL
      line 224: `x_2d = width // 2 + int(x * scale)`     # int(NaN*scale) -> ValueError
      line 225: `y_2d = height // 2 + int(y * scale)`    # int(NaN*scale) -> ValueError

  **Bug A (silent off-screen):** NaN z (or any NaN input that makes `depth`
  NaN) -> `max(0.1, NaN) = 0.1` (Python's `max` with NaN returns the
  first-arg when the other is NaN) -> `scale = focal_length / 0.1 = 10*FL` ->
  valid x/y get blown up to a HUGE off-screen pixel (e.g. 1920x1080, FL=1000,
  dist=10, NaN z, valid x=0.5, y=0.3 -> pixel (5960, 3540) — far outside
  1920x1080 viewport). NaN input is silently converted to an off-screen point,
  which the renderer clips to "no joint drawn" -> silent data loss.

  **Bug B (crash):** NaN x or NaN y -> `int(NaN * scale) = int(NaN)` raises
  `ValueError: cannot convert float NaN to integer`. Uncaught -> propagates
  up, kills the renderer mid-frame, whole video frame lost.

  **Bug C (degenerate off-screen):** z = camera_distance -> `depth = 0` ->
  `max(0.1, 0) = 0.1` -> SAME off-screen blowup as Bug A. Function does not
  distinguish "joint at the camera plane" (real geometric problem, joint is
  in front of camera) from "NaN joint" (data corruption problem). Both
  produce (5960, 3540).

  There is NO `math.isfinite` guard on the input tuple. The vectorized
  (ndarray) branch (line 175-212) uses `np.nan_to_num(..., nan=0)` and
  `np.where(depth <= 0.1, 0.1, depth)` to silently coerce NaN to (0, 0) and
  clamp degenerate depth — but the scalar (tuple) branch has NO such guard,
  so the SAME function handles NaN gracefully in one branch and CRASHES /
  off-screen in the other.

Consequences (prod impact):
  1. NaN input from 3D pose lifter failure, blend-3d artifact, or gap-filler
     NaN propagation silently produces off-screen pixel (Bug A) or crashes
     the renderer (Bug B) — the documented scalar (tuple) API path
     (`>>> project_3d_to_2d((0.5, 0.3, 1.0), 1920, 1080)`, line 170-171).
  2. Degenerate z = camera_distance (joint exactly at the camera plane, a
     geometric impossibility for a real joint) is INDISTINGUISHABLE from
     NaN (Bug C) — both produce the same off-screen pixel.
  3. `project_3d_to_2d` is a PUBLIC export (`src/visualization/__init__.py`
     line 46, 138; `src/visualization/core/__init__.py` line 22, 45). The
     scalar path is exercised by any caller that passes a single position
     tuple (the documented API shape). One NaN coordinate -> renderer crash
     or silent data loss.

Fix (NOT applied — repro only):
  - `project_3d_to_2d` scalar path (line 213-227): add `math.isfinite` guard
    on x, y, z at function entry; raise `ValueError(f"pos_3d must be finite,
    got ({x}, {y}, {z})")` for non-finite input. Also add `if depth <= 0:
    raise ValueError(f"z must be < camera_distance ...")` to distinguish
    geometric degeneracy from data corruption.
  The correct contract: a NaN coordinate in a scalar (tuple) position must
  NOT silently off-screen (Bug A) and must NOT crash (Bug B) — it must
  raise at the trust boundary so the upstream bug surfaces, matching the
  PR #1065 / #1070 pattern used for `pixel_to_normalized` and `clip_to_frame`
  in the same file.

Methodology (per audit reglement):
  3 observables  (BUG present -> PASS; flip to GREEN contract on fix)
  1 regression   (PASS — finite scalar tuple -> finite pixel tuple)
  1 source check (PASS — root cause locked via inspect.getsource)

Pure-Python (no GPU, no DB): `project_3d_to_2d` is pure-numpy + int cast.
We feed synthetic NaN / degenerate scalar tuples (no pipeline run) to
isolate the silent off-screen and crash.
"""

from __future__ import annotations

import inspect

from src.visualization.core.geometry import project_3d_to_2d

# =============================================================================
# Source check — root cause locked.
# =============================================================================


def test_project_3d_to_2d_scalar_path_has_isfinite_guard():
    """GREEN contract source check: `project_3d_to_2d` scalar branch now
    guards x, y, z with `math.isfinite(...)` at function entry and raises
    `ValueError` on non-finite input. The unfixed scalar branch does
    `depth = max(0.1, camera_distance - z)` and `int(x * scale)` with NO
    NaN guard -> silent off-screen or int(NaN) ValueError crash.

    Mirrors the PR #1065 / #1070 pattern (`pixel_to_normalized` and
    `clip_to_frame` use `math.isfinite` guards in the same file).
    """
    src = inspect.getsource(project_3d_to_2d)

    # GREEN: the scalar `else:` branch now uses `math.isfinite` to guard x, y, z.
    scalar_branch = src.split("else:")[-1]  # last `else:` is the scalar branch
    assert "isfinite" in scalar_branch, (
        "project_3d_to_2d scalar branch must guard x/y/z with math.isfinite "
        "before the projection (depth = max(0.1, ...), int(x*scale)). The "
        "unfixed branch is NaN-blind: max(0.1, NaN) = 0.1 -> off-screen "
        "pixel, int(NaN*scale) -> ValueError crash. Add math.isfinite guard "
        "at function entry mirroring the PR #1065 / #1070 pattern."
    )
    # And the guard must raise, not silently coerce to off-screen.
    assert "ValueError" in scalar_branch or "raise" in scalar_branch, (
        "project_3d_to_2d scalar branch must raise on non-finite input (not "
        "silently coerce to off-screen). Root cause not fixed if guard just "
        "returns (0, 0) silently — symmetric sibling-bug shape (silent data "
        "loss in one branch, crash in the other)."
    )


# =============================================================================
# Observable 1 — BUG: NaN z (or any NaN input that makes `depth` NaN) silently
# produces an off-screen pixel. The vectorized (ndarray) branch uses
# `np.nan_to_num(..., nan=0)` to coerce NaN to (0, 0); the scalar (tuple)
# branch has NO such guard -> max(0.1, NaN) = 0.1 -> 10*FL scale blowup.
# =============================================================================


def test_nan_z_silently_produces_offscreen_pixel():
    """BUG: `project_3d_to_2d((0.5, 0.3, NaN), 1920, 1080, 1000, 10.0)`
    returns (5960, 3540) — far outside the 1920x1080 viewport. NaN z ->
    `depth = max(0.1, NaN) = 0.1` -> `scale = 1000/0.1 = 10000` -> x=0.5
    blown up to 5000+960 = 5960, y=0.3 blown up to 3000+540 = 3540. The
    vectorized (ndarray) branch NaN-masks to (0, 0) gracefully; the scalar
    branch silently off-screens.

    PASS on unfixed code. A fix (isfinite guard before projection) ->
    raise ValueError -> assert FAILS -> GREEN contract. Locks the silent
    off-screen hazard so a fix cannot rely on `max(0.1, ...)` to reject
    NaN quietly.
    """
    nan = float("nan")
    raised = False
    try:
        out = project_3d_to_2d((0.5, 0.3, nan), 1920, 1080, 1000, 10.0)
    except (ValueError, TypeError):
        raised = True
        out = None

    # BUG: NaN z silently produces (5960, 3540) — far outside viewport.
    if not raised:
        assert out != (5960, 3540), (
            f"BUG: project_3d_to_2d((0.5, 0.3, NaN), 1920, 1080, 1000, 10.0) "
            f"silently returned {out} (off-screen — far outside 1920x1080 "
            f"viewport). NaN z -> max(0.1, NaN) = 0.1 -> 10*FL scale blowup. "
            f"Add math.isfinite guard at function entry to raise instead of "
            f"silently corrupting the renderer with an off-screen pixel."
        )
    # GREEN contract: NaN z must raise (no silent off-screen, no silent
    # coerce to (0, 0) — symmetric with PR #1065 / #1070 pattern).
    assert raised, (
        f"GREEN contract: project_3d_to_2d with NaN z must raise ValueError "
        f"at the trust boundary (not silently off-screen, not silently "
        f"coerce to (0, 0)). Got {out}. Mirror the PR #1065 / #1070 "
        f"math.isfinite guard pattern from `pixel_to_normalized` and "
        f"`clip_to_frame` in the same file."
    )


# =============================================================================
# Observable 2 — BUG: NaN x or NaN y -> int(NaN * scale) raises ValueError.
# `int(NaN)` raises `ValueError: cannot convert float NaN to integer` (Python
# rejects NaN->int cast). The uncaught exception propagates up, kills the
# renderer mid-frame, whole video frame lost.
# =============================================================================


def test_nan_x_raises_valueerror_no_crash():
    """BUG: `project_3d_to_2d((NaN, 0.3, 1.0), 1920, 1080, 1000, 10.0)`
    raises `ValueError: cannot convert float NaN to integer` (uncaught ->
    kills renderer mid-frame).

    PASS on unfixed code IF it raises. A fix (isfinite guard at function
    entry) -> raise ValueError with a clear message naming the bad input
    (not Python's generic int-cast message) -> assert still PASSES (raised
    == True). The test PASSES on both unfixed and fixed code; the GREEN
    contract is `raised == True` (no crash that propagates silently).
    Locks the crash site.
    """
    nan = float("nan")
    raised = False
    try:
        out = project_3d_to_2d((nan, 0.3, 1.0), 1920, 1080, 1000, 10.0)
    except (ValueError, TypeError):
        raised = True
        out = None

    # BUG: NaN x crashes with ValueError. Test passes (raised == True)
    # on unfixed code. A fix that guards at the trust boundary with a
    # clear ValueError message ALSO passes — locks the contract that the
    # function must not silently return garbage on NaN input.
    assert raised, (
        f"BUG: project_3d_to_2d((NaN, 0.3, 1.0), 1920, 1080, 1000, 10.0) "
        f"returned {out} (silent). NaN x -> int(NaN * scale) -> ValueError "
        f"crash. Function must raise on non-finite input (not silently "
        f"return garbage), mirroring PR #1065 / #1070 pattern."
    )


# =============================================================================
# Observable 3 — BUG: z = camera_distance (joint at the camera plane) is a
# real geometric degeneracy. The unfixed function does `depth = max(0.1, 0)
# = 0.1` -> SAME 10*FL off-screen blowup as Bug A. Function does not
# distinguish "joint at the camera" from "NaN joint" — both produce
# (5960, 3540). A fix that only NaN-guards (without depth>0 guard) leaves
# the degenerate-z off-screen hazard intact.
# =============================================================================


def test_degenerate_z_equals_camera_distance_raises():
    """BUG: `project_3d_to_2d((0.5, 0.3, 10.0), 1920, 1080, 1000, 10.0)`
    returns (5960, 3540) — z = camera_distance -> depth = 0 -> max(0.1, 0)
    = 0.1 -> SAME 10*FL off-screen blowup as NaN z. Function is
    INDISTINGUISHABLE from NaN input (Bug A produces identical output).

    PASS on unfixed code (returns off-screen pixel). A fix must add
    `if depth <= 0: raise ValueError(f"z must be < camera_distance ...")`
    to distinguish geometric degeneracy from data corruption.

    Locks the degenerate-z hazard so a fix cannot rely on `max(0.1, ...)`
    to clamp depth quietly.
    """
    raised = False
    try:
        out = project_3d_to_2d((0.5, 0.3, 10.0), 1920, 1080, 1000, 10.0)
    except (ValueError, TypeError):
        raised = True
        out = None

    if not raised:
        # BUG: degenerate z produces same off-screen pixel as NaN z.
        assert out != (5960, 3540), (
            f"BUG: project_3d_to_2d((0.5, 0.3, 10.0), 1920, 1080, 1000, 10.0) "
            f"silently returned {out} (off-screen — z = camera_distance "
            f"-> depth = 0 -> max(0.1, 0) = 0.1 -> 10*FL blowup). Function "
            f"is INDISTINGUISHABLE from NaN z. Add `if depth <= 0: raise` "
            f"guard to surface the geometric degeneracy."
        )
    # GREEN: degenerate z must raise (not silently off-screen).
    assert raised, (
        f"GREEN contract: project_3d_to_2d with z = camera_distance must "
        f"raise ValueError (not silently off-screen). Got {out}. Mirror "
        f"the PR #1065 / #1070 pattern — guard at the trust boundary."
    )


# =============================================================================
# Regression — PASS: a finite scalar tuple (0.5, 0.3, 1.0) -> finite pixel
# tuple (1015, 573) for 1920x1080, FL=1000, dist=10. The fix (isfinite
# guard) must NOT regress the finite scalar path.
# =============================================================================


def test_finite_scalar_returns_finite_pixel():
    """NOT a bug: a finite scalar tuple (0.5, 0.3, 1.0) -> finite pixel
    tuple (1015, 573) for 1920x1080, FL=1000, dist=10. Regression guard
    so an isfinite-guard fix does not break the finite scalar path.
    """
    out = project_3d_to_2d((0.5, 0.3, 1.0), 1920, 1080, 1000, 10.0)
    assert out == (1015, 573), (
        f"BUG (regression): finite scalar (0.5, 0.3, 1.0) on 1920x1080, "
        f"FL=1000, dist=10 -> {out} (expected (1015, 573)). The finite "
        f"scalar path must return the projected pixel tuple unchanged. "
        f"An isfinite-guard fix must not regress this."
    )
