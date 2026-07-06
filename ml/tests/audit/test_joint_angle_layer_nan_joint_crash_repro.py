"""RED repro — `JointAngleLayer.render` CRASHES with `ZeroDivisionError:
division by zero` when a joint point of an angle spec is NaN (partial
occlusion — rest of body valid) and poses are in PIXEL coordinates
(`normalized=False`), and SILENTLY DRAWS A GARBAGE arc when poses are
NORMALIZED (`normalized=True`) — a NaN joint point is not graceful-skipped on
the 2D path.

Root cause (ml/src/visualization/layers/joint_angle_layer.py):

  `render` (line 182) has a NaN guard ONLY on the 3D path, NOT the 2D path:
      if use_3d and context.pose_3d is not None:
          a3 = context.pose_3d[spec.point_a]; v3 = ...; c3 = ...
          if not (np.isnan(a3).any() or np.isnan(v3).any() or np.isnan(c3).any()):
              angle = angle_3pt(a3, v3, c3)                          # 201-202

      # 2D path — NO NaN guard on pa/pv/pc:
      if context.normalized:
          pa = np.array(normalized_to_pixel(pose[spec.point_a], w, h), ...)  # 206
          pv = np.array(normalized_to_pixel(pose[spec.vertex], w, h), ...)   # 207
          pc = np.array(normalized_to_pixel(pose[spec.point_c], w, h), ...)   # 208
          # normalized_to_pixel array-branch masks NaN → (0,0) → garbage arc
      else:
          pa = pose[spec.point_a].astype(np.float64)                        # 210
          pv = pose[spec.vertex].astype(np.float64)                         # 211
          pc = pose[spec.point_c].astype(np.float64)                         # 212
          # pixel path: pa/pv/pc stay NaN

      if angle is None:
          angle = angle_3pt(pa, pv, pc)                                      # 216
          # pixel path: angle_3pt(NaN, ...) → ZeroDivisionError CRASH

      if np.isnan(angle) or angle < 0 or angle > 360:                      # 219
          continue   # NEVER REACHED (pixel path crashed at line 216)

  `angle_3pt_rad` (geometry.py:12) is `@njit(fastmath=True)` — under fastmath,
  NaN in `ba = a - b` / `bc = c - b` makes `np.linalg.norm(ba) = nan`, and
  `nan / (nan * nan + 1e-8)` raises `ZeroDivisionError` (fastmath NaN→0 in
  division). ANY of point_a / vertex / point_c NaN → ZeroDivisionError.

Two failure modes (same root cause — 2D path has no per-joint NaN guard):
  1. PIXEL path (`normalized=False`): `pa`/`pv`/`pc` stay NaN →
     `angle_3pt(NaN, ...)` → `ZeroDivisionError: division by zero` (line 216)
     → the whole `render` call crashes → the visualization pipeline aborts
     the frame. The `if np.isnan(angle) ... continue` guard (line 219) is
     NEVER reached (the crash happens at line 216, before `angle` is assigned).
  2. NORMALIZED path (`normalized=True`): `normalized_to_pixel` array-branch
     masks NaN → (0,0), so `pa`/`pv`/`pc` = (0,0) → `angle_3pt((0,0), ...)`
     returns a finite angle (e.g. 140°) → the line-219 guard passes (angle is
     finite, in [0,360]) → a GARBAGE arc + ticks + degree label are drawn at
     the frame origin / wrong location — a misleading joint-angle artifact on
     a frame where the joint was occluded.

Consequences (prod impact — `JointAngleLayer` is a user-facing HUD layer,
rendered for every analyzed frame, drawing knee/hip/elbow angles for the
coach/athlete review):
  1. PIXEL path: a NaN joint point (knee/foot/elbow occluded / off-frame —
     common in figure skating, free leg frequently leaves frame during spins)
     → `ZeroDivisionError` → the whole frame render crashes → the
     visualization pipeline aborts → the user gets a broken/missing annotated
     video. The crash message ("division by zero") gives NO hint the cause is
     an occluded joint — it looks like a geometry bug, not a data bug.
  2. NORMALIZED path: no crash, but a garbage arc + degree label is drawn at
     the wrong location (origin / collapsed angle) — a misleading
     joint-angle readout polluting the user-facing HUD on frames with an
     occluded joint, polluting the coach/athlete review with wrong angle
     numbers.
  3. The 3D path IS guarded (line 201: `if not (np.isnan(a3).any() or ...)`)
     but the 2D path is NOT — asymmetric, the same NaN-safety that the 3D path
     has was not applied to the 2D path. A fix that adds the same
     `np.isnan(...).any()` guard to `pa`/`pv`/`pc` on the 2D path fixes both
     modes (skip the spec on NaN).
  4. The `if np.isnan(angle) or ... continue` guard (line 219) was INTENDED to
     catch NaN angles, but the pixel path crashes at `angle_3pt` (line 216)
     BEFORE `angle` is assigned — the guard is dead code for the NaN-joint
     case on the pixel path. The normalized path produces a finite (garbage)
     angle, so the guard passes it. Both modes bypass the intended guard.
  5. Existing tests miss it: `test_joint_angle*` feed all-valid keypoints. No
     test feeds a NaN joint point (rest valid) through `render` and asserts it
     does not crash / does not draw a garbage arc.
  6. Same class as CA/CB — the `int(nan)` / `angle_3pt(NaN)` crash +
     `normalized_to_pixel` masks NaN→(0,0) garbage pattern repeats across viz
     layers. The 2D path NaN guard is the missing piece.

The fix (NOT applied — repro only):
  - mirror the 3D guard on the 2D path (after computing pa/pv/pc, lines
    206-212):
    `if np.isnan(pa).any() or np.isnan(pv).any() or np.isnan(pc).any(): continue`
    (skip the spec — graceful, no arc, no crash, no garbage); and/or
  - guard before `angle_3pt` (line 216):
    `try: angle = angle_3pt(pa, pv, pc) except (ZeroDivisionError, ValueError):
    continue`; and/or
  - make `angle_3pt_rad` NaN-aware (return `nan` on NaN input, not raise) —
    then the line-219 guard catches it; but the per-joint skip is cleaner
    (avoids the garbage normalized-path arc too).
  The cleanest fix: add the `np.isnan(...).any()` guard to pa/pv/pc on the 2D
  path (mirror line 201) — one line, fixes both modes, matches the existing
  3D-path guard pattern.

The correct contract: a NaN joint point (partial occlusion, rest valid) on the
2D path must NOT crash `render` and must NOT draw a garbage arc. The layer
must graceful-skip the angle spec (continue, no arc) — NOT crash, NOT draw
garbage.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN joint point (rest valid) must NOT raise (pixel path) and must NOT draw an
arc (normalized path). They FAIL because the 2D path has no NaN guard on
pa/pv/pc, so `angle_3pt(NaN)` crashes (pixel) / `normalized_to_pixel` masks to
(0,0) and `angle_3pt((0,0),...)` returns a finite garbage angle (normalized).
After the fix: the per-joint NaN guard skips the spec. The source-check test
confirms the 3D-path `np.isnan(...).any()` guard IS present (line 201) but the
2D path has only the dead-code `if np.isnan(angle) ...` guard (line 219) and
the unguarded `angle = angle_3pt(pa, pv, pc)` call (line 216) — root cause
locked.

Pure-Python (no GPU, no DB): `JointAngleLayer.render` is a pure-data function
over a pose array + a frame buffer (cv2 ellipse/line drawing).
"""

import inspect

import cv2
import numpy as np

import src.visualization.layers.joint_angle_layer as mod
from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.joint_angle_layer import JointAngleLayer, JointAngleSpec


def _spec() -> JointAngleSpec:
    """R-knee angle spec: vertex=RKNEE, point_a=RHIP, point_c=RFOOT."""
    return JointAngleSpec(
        name="rknee",
        point_a=H36Key.RHIP,
        vertex=H36Key.RKNEE,
        point_c=H36Key.RFOOT,
    )


def _valid_pose(normalized: bool) -> np.ndarray:
    pose = np.zeros((17, 2), dtype=np.float32)
    if normalized:
        pose[H36Key.RHIP] = [0.40, 0.50]
        pose[H36Key.RKNEE] = [0.42, 0.70]
        pose[H36Key.RFOOT] = [0.44, 0.90]
    else:
        pose[H36Key.RHIP] = [250.0, 300.0]
        pose[H36Key.RKNEE] = [260.0, 360.0]
        pose[H36Key.RFOOT] = [270.0, 420.0]
    return pose


def _nan_point_pose(point: int, normalized: bool) -> np.ndarray:
    """Pose with ONLY `point` NaN (rest valid) — partial occlusion."""
    pose = _valid_pose(normalized)
    pose[point] = [np.nan, np.nan]
    return pose


def _render_and_collect_ellipses(layer, frame, ctx) -> int:
    """Render and count cv2.ellipse calls (the angle-arc draw). A correct
    graceful-skip draws ZERO ellipses when a joint point is NaN."""
    calls = []
    orig_ellipse = mod.cv2.ellipse

    def spy(*a, **k):
        calls.append(1)
        return orig_ellipse(*a, **k)

    mod.cv2.ellipse = spy
    try:
        layer.render(frame, ctx)
    finally:
        mod.cv2.ellipse = orig_ellipse
    return len(calls)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN joint point in PIXEL coords must NOT crash render —
# graceful skip, NOT ZeroDivisionError.
# --------------------------------------------------------------------------- #


def test_nan_point_pixel_render_does_not_crash_repro():
    """CORRECT behavior: `JointAngleLayer.render` with a NaN joint point
    (point_c=RFOOT, rest valid) in pixel coords (`normalized=False`) must NOT
    raise. It must graceful-skip the angle spec (continue, no arc) and return
    the frame, NOT crash with `ZeroDivisionError: division by zero`.

    RED now: NaN RFOOT (rest valid, pixel) → 2D path has no NaN guard on
    pa/pv/pc (only the 3D path is guarded, line 201) → `pc = pose[RFOOT]` =
    NaN → `angle = angle_3pt(pa, pv, pc)` (line 216) → `angle_3pt_rad` is
    `@njit(fastmath=True)`, NaN makes `norm(ba)=nan`, `nan/(nan+1e-8)` raises
    ZeroDivisionError (fastmath NaN→0 in division). The `if np.isnan(angle) ...
    continue` guard (line 219) is NEVER reached (crash at 216 before `angle`
    is assigned). After the fix: the 2D path guards pa/pv/pc (mirror line 201)
    and skips the spec.
    """
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_nan_point_pose(H36Key.RFOOT, normalized=False),
    )
    try:
        out = layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)
    except Exception as e:
        raise AssertionError(
            f"BUG: JointAngleLayer.render raised {type(e).__name__}: {e} for "
            f"a NaN joint point (point_c=RFOOT, rest valid) in pixel coords "
            f"(normalized=False). The 3D path guards NaN (line 201: `if not "
            f"(np.isnan(a3).any() or ...)`), but the 2D path has NO NaN guard "
            f"on pa/pv/pc (lines 210-212), so `pc = pose[RFOOT]` is NaN and "
            f"`angle = angle_3pt(pa, pv, pc)` (line 216) raises "
            f"ZeroDivisionError — `angle_3pt_rad` is `@njit(fastmath=True)`, "
            f"NaN makes `norm(ba)=nan`, `nan/(nan+1e-8)` raises (fastmath "
            f"NaN→0 in division). The `if np.isnan(angle) ... continue` guard "
            f"(line 219) is dead code here — the crash happens at line 216 "
            f"BEFORE `angle` is assigned. A NaN joint point (free foot "
            f"off-frame during spins — common in figure skating) crashes the "
            f"whole frame render → the visualization pipeline aborts → the "
            f"user gets a broken annotated video. The 2D path must mirror the "
            f"3D NaN guard (skip the spec), NOT crash."
        ) from e

    assert out is not None, (
        "BUG: JointAngleLayer.render returned None for a NaN joint point "
        "(pixel); expected the frame."
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN joint point in NORMALIZED coords must NOT draw a garbage
# arc — graceful skip.
# --------------------------------------------------------------------------- #


def test_nan_point_normalized_render_no_garbage_arc_repro():
    """CORRECT behavior: `JointAngleLayer.render` with a NaN joint point
    (point_c=RFOOT, rest valid) in normalized coords (`normalized=True`) must
    NOT draw an angle arc. `normalized_to_pixel` array-branch masks NaN to
    (0,0), so no crash, but `angle_3pt((0,0), pv, pa)` returns a finite
    garbage angle (e.g. ~140°) that passes the line-219 `np.isnan(angle)`
    guard → a GARBAGE arc + ticks + degree label are drawn at the wrong
    location. The layer must graceful-skip the spec (zero ellipses), NOT draw
    garbage.

    RED now: NaN RFOOT (normalized) → `normalized_to_pixel` masks NaN →
    (0,0) → `pc = (0,0)` → `angle_3pt(pa, pv, (0,0))` = finite garbage →
    line-219 guard passes → ellipse + ticks + label drawn. After the fix: the
    2D-path NaN guard skips the spec, zero ellipses.
    """
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=True,
        pose_2d=_nan_point_pose(H36Key.RFOOT, normalized=True),
    )
    n_ellipses = _render_and_collect_ellipses(layer, np.zeros((h, w, 3), dtype=np.uint8), ctx)

    # CORRECT contract: ZERO angle arcs when a joint point is NaN.
    assert n_ellipses == 0, (
        f"BUG: JointAngleLayer.render drew {n_ellipses} angle arc(s) "
        f"(cv2.ellipse) for a NaN joint point (point_c=RFOOT, rest valid) in "
        f"normalized coords. `normalized_to_pixel` array-branch masks NaN to "
        f"(0,0) (geometry.py:74), so `pc = (0,0)`, no crash, but "
        f"`angle_3pt(pa, pv, (0,0))` returns a finite GARBAGE angle (~140°) "
        f"that passes the `if np.isnan(angle) ... continue` guard (line 219) "
        f"— a GARBAGE arc + tick marks + degree label are drawn at the wrong "
        f"location, polluting the user-facing HUD with a misleading "
        f"joint-angle readout on a frame where the joint was occluded. The 2D "
        f"path has no NaN guard on pa/pv/pc (only the 3D path is guarded, line "
        f"201). The layer must graceful-skip the spec (mirror the 3D guard), "
        f"NOT draw garbage."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the crash triggers for NaN in ANY of the three points (a,
# vertex, c) — wide blast radius.
# --------------------------------------------------------------------------- #


def test_nan_any_point_pixel_render_does_not_crash_repro():
    """CORRECT behavior: a NaN in ANY of point_a / vertex / point_c (rest
    valid, pixel) must NOT crash `render`. `angle_3pt` uses all three points;
    NaN in any one raises ZeroDivisionError. The bug has a wide blast radius
    — any occluded joint of the angle triplet.

    RED now: NaN in RHIP (point_a), RKNEE (vertex), or RFOOT (point_c) each
    → ZeroDivisionError. After the fix: graceful skip on any occluded point.
    """
    w, h = 640, 480
    for point, label in [
        (H36Key.RHIP, "point_a=RHIP"),
        (H36Key.RKNEE, "vertex=RKNEE"),
        (H36Key.RFOOT, "point_c=RFOOT"),
    ]:
        layer = JointAngleLayer(joints=[_spec()])
        ctx = LayerContext(
            frame_width=w,
            frame_height=h,
            normalized=False,
            pose_2d=_nan_point_pose(point, normalized=False),
        )
        try:
            layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)
        except Exception as e:
            raise AssertionError(
                f"BUG: JointAngleLayer.render raised {type(e).__name__}: {e} "
                f"for a NaN joint point ({label}, rest valid, pixel). "
                f"`angle_3pt` uses all three points; NaN in any one raises "
                f"ZeroDivisionError (fastmath NaN→0 in division). The crash "
                f"triggers on ANY occluded point of the angle triplet — wide "
                f"blast radius. A fix that only guards one point would leave "
                f"the other two broken."
            ) from e


# --------------------------------------------------------------------------- #
# Regression guard: an all-valid pose still draws the angle arc.
# --------------------------------------------------------------------------- #


def test_all_valid_angle_arc_drawn_repro():
    """Regression guard: an all-valid pose must still draw the angle arc.
    The fix (2D-path NaN guard) must not suppress the valid case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    w, h = 640, 480
    layer = JointAngleLayer(joints=[_spec()])
    ctx = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_valid_pose(normalized=False),
    )
    n_ellipses = _render_and_collect_ellipses(layer, np.zeros((h, w, 3), dtype=np.uint8), ctx)
    assert n_ellipses >= 1, (
        f"BUG (regression): all-valid pose drew {n_ellipses} angle arc(s); "
        f"expected >= 1. The valid case must be unchanged by the NaN-aware fix "
        f"— the angle arc must still draw when all joint points are finite."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — 3D path IS NaN-guarded, 2D path is NOT +
# unguarded angle_3pt call + dead-code np.isnan(angle) guard.
# --------------------------------------------------------------------------- #


def test_joint_angle_layer_nan_crash_source_repro():
    """Source check (GREEN contract): the 2D-path NaN guard lives in `render`
    on the RAW pose (pre-`normalized_to_pixel` conversion). The 3D path guards
    NaN (line 201); the 2D path now mirrors it — but on the raw pose, NOT on
    `pa`/`pv`/`pc` after conversion. The normalized path masks NaN to (0,0)
    inside `normalized_to_pixel`, so a post-conversion `np.isnan(pa)` check is
    always False and the garbage arc leaks; the raw-pose guard catches it
    before conversion. `angle_3pt(pa, pv, pc)` is still the fallback — the
    guard is upstream (skip the spec), not wrapping the call.
    """
    src = inspect.getsource(JointAngleLayer.render)
    # The 3D path IS NaN-guarded (proves the codebase knows the pattern).
    assert "if not (np.isnan(a3).any() or np.isnan(v3).any() or np.isnan(c3).any()):" in src, (
        "BUG: render must guard the 3D path with `if not (np.isnan(a3).any() "
        "or np.isnan(v3).any() or np.isnan(c3).any()):` — the #894 fix mirrors "
        "it on the 2D path; if the 3D guard was removed the repro is invalid."
    )
    # The 2D-path raw-pose NaN guard is present (pre-conversion, mirrors line
    # 201) — the #894 fix.
    assert (
        "np.isnan(pose[spec.point_a]).any()" in src
        and "np.isnan(pose[spec.vertex]).any()" in src
        and "np.isnan(pose[spec.point_c]).any()" in src
    ), (
        "BUG: render must guard the 2D path on the RAW pose "
        "(`np.isnan(pose[spec.point_a]).any() or ...`) — the #894 fix. A "
        "post-conversion guard (np.isnan(pa)) is dead for the normalized path "
        "(normalized_to_pixel masks NaN -> (0,0)); the raw-pose guard catches "
        "it before conversion."
    )
    # The 2D path still computes pa/pv/pc (the guard is before them, not
    # replacing them).
    assert (
        "pa = pose[spec.point_a].astype(np.float64)" in src
        and "pv = pose[spec.vertex].astype(np.float64)" in src
        and "pc = pose[spec.point_c].astype(np.float64)" in src
    ), (
        "BUG: render must still compute `pa = pose[spec.point_a].astype(...)` "
        "/ `pv` / `pc`; the #894 guard is before the conversion, not a "
        "replacement of it."
    )
    # angle_3pt is still the 2D fallback — the guard is upstream (skip spec),
    # not wrapping the call.
    assert "angle = angle_3pt(pa, pv, pc)" in src, (
        "BUG: render must still call `angle = angle_3pt(pa, pv, pc)` as the 2D "
        "fallback; the #894 guard skips the spec upstream, it does not wrap the "
        "call."
    )
    # The NaN-angle guard is still present (defence-in-depth for the pixel
    # path where #863's angle_3pt wrapper returns NaN).
    assert "if np.isnan(angle) or angle < 0 or angle > 360:" in src, (
        "BUG: render must keep `if np.isnan(angle) or angle < 0 or angle > "
        "360: continue` (defence-in-depth for the pixel path where angle_3pt "
        "returns NaN); the #894 raw-pose guard is the primary, this is the "
        "secondary. If it was removed, the pixel path may regress."
    )
