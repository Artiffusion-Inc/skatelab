"""RED repro — `VerticalAxisLayer._draw_head_alignment` CRASHES with
`ValueError: cannot convert float NaN to integer` when the HEAD keypoint is
NaN and the pose is in PIXEL coordinates (`normalized=False`), and SILENTLY
DRAWS A GARBAGE head-alignment indicator from the origin (0,0) when the pose
is NORMALIZED (`normalized=True`) — a NaN keypoint is not graceful-skipped.

Root cause (ml/src/visualization/layers/vertical_axis_layer.py):

  `render` (line 102) guards only the hip/shoulder joints, NOT the head:
      required_keys = (H36Key.LHIP, H36Key.RHIP, H36Key.LSHOULDER, H36Key.RSHOULDER)
      if any(np.isnan(pose[k]).any() for k in required_keys):
          return frame                                              # line 110

  HEAD is NOT in `required_keys`, so a NaN HEAD slips through. Then:
      head = np.asarray(normalized_to_pixel(pose[H36Key.HEAD], w, h), ...)   # 124
    (normalized path: `normalized_to_pixel` array-branch masks NaN → (0,0),
     silent garbage; pixel path: no masking → head_pt stays NaN)
      ...
      if self.show_head_alignment:
          self._draw_head_alignment(frame, mid_hip, mid_shoulder, head, spine_vector)  # 175

  `_draw_head_alignment` (277-310):
      hip = mid_hip[:2]
      head_pt = head[:2]                                            # NaN (pixel) or (0,0) (normalized)
      spine_len_sq = float(np.dot(spine_vector, spine_vector))     # 294 — finite (spine valid)
      if spine_len_sq < 1.0: return                                 # 295 — guard checks LENGTH only,
                                                                    # NOT NaN in head_pt
      t = float(np.dot(head_pt - hip, spine_vector) / spine_len_sq) # 299 — NaN head_pt → t=nan
      t = max(0.0, min(1.0, t))                                     # 300 — `min(1.0, nan) = 1.0`
                                                                    # (#454 arg-order trap), `max(0.0, 1.0) = 1.0`
      projection = hip + t * spine_vector                           # 301 — finite (hip/spine valid)
      offset = float(np.linalg.norm(head_pt - projection))         # 303 — NaN (pixel) or finite (normalized 0,0)
      if offset < 3.0: return                                       # 304 — `nan < 3.0` is False → no skip
                                                                    # (pixel path); normalized (0,0) offset
                                                                    # may exceed 3.0 → draws garbage
      hx, hy = int(head_pt[0]), int(head_pt[1])                     # 308 — `int(nan)` → ValueError
                                                                    # CRASH (pixel path)

Two failure modes (same root cause — HEAD not guarded):
  1. PIXEL path (`normalized=False`): head_pt is genuinely NaN → `int(nan)`
     raises `ValueError: cannot convert float NaN to integer` → the whole
     `render` call crashes → the visualization pipeline aborts the frame.
  2. NORMALIZED path (`normalized=True`): `normalized_to_pixel` array-branch
     masks NaN to (0,0), so head_pt = (0,0) (top-left corner) — no crash, but
     a GARBAGE head-alignment line is drawn from the frame origin to the spine
     projection, polluting the user-facing HUD with a misleading indicator on
     a frame where the head was NOT detected.

Consequences (prod impact — `VerticalAxisLayer` is a user-facing HUD layer,
rendered for every analyzed frame in `VisualizationPipeline` / `comparison.py`):
  1. PIXEL path: a single NaN HEAD (head off-frame / undetected — common in
     figure skating, head frequently leaves frame during rotations) crashes
     the whole frame render → the visualization pipeline aborts → the user
     gets a broken/missing annotated video. The crash message
     ("cannot convert float NaN to integer") gives NO hint the cause is an
     occluded HEAD keypoint.
  2. NORMALIZED path: no crash, but a garbage indicator line from (0,0) is
     drawn into the user-facing video — a misleading visual artifact on
     frames with an undetected head, polluting the coach/athlete review.
  3. The render guard checks LHIP/RHIP/LSHOULDER/RSHOULDER but NOT HEAD —
     asymmetric, the head is the only required joint for the head-alignment
     indicator yet the only one not guarded. A fix that adds HEAD to
     `required_keys` (or guards head_pt in `_draw_head_alignment`) fixes both.
  4. Existing tests miss it: `test_vertical_axis*` / layer tests feed
     all-valid keypoints. No test feeds a NaN HEAD through `render` and
     asserts it does not crash / does not draw a garbage indicator.
  5. The #454 arg-order trap (`min(1.0, nan) = 1.0`) on line 300 is the same
     class of bug as BX/BZ — the clamp silently passes NaN through to the
     `int()` crash.

The fix (NOT applied — repro only):
  - add `H36Key.HEAD` to `required_keys` in `render` (line 108) — a NaN HEAD
    skips the whole layer (graceful, no indicator); and/or
  - guard `head_pt` in `_draw_head_alignment`: `if not np.isfinite(head_pt).all():
    return` before the `int()` conversion (line 308); and/or
  - guard the `int()` calls: `if not np.isfinite(head_pt[0]) or not
    np.isfinite(head_pt[1]): return`; and/or
  - replace `int(head_pt[0])` with `int(np.nan_to_num(head_pt[0]))` — but this
    silently draws from (0,0) (the normalized-path garbage), so the skip is
    more honest than the draw-from-origin.
  The cleanest fix: add HEAD to `required_keys` — one line, fixes both paths,
    matches the existing guard pattern.

The correct contract: a NaN HEAD keypoint must NOT crash `render` and must
NOT draw a garbage head-alignment indicator from the origin. The layer must
graceful-skip the head-alignment indicator (or the whole layer) when the head
is NaN — NOT crash, NOT draw garbage.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN HEAD must NOT raise (pixel path) and must NOT draw a head-alignment
indicator (both paths). They FAIL because HEAD is not in `required_keys` and
`_draw_head_alignment` does `int(nan)` (crash) / draws from (0,0) (garbage).
After the fix: HEAD is guarded and the indicator is skipped. The source-check
test confirms `required_keys` does NOT include `H36Key.HEAD` and the
unguarded `int(head_pt[0])` line is present (root cause locked).

Pure-Python (no GPU, no DB): `VerticalAxisLayer.render` and
`_draw_head_alignment` are pure-data functions over a pose array + a frame
buffer (cv2 line drawing on a numpy array).
"""

import inspect

import cv2
import numpy as np

from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.vertical_axis_layer import VerticalAxisLayer


HEAD_COLOR = (180, 130, 255)  # the head-alignment indicator color (line 310)


def _pose(nan_head: bool, normalized: bool) -> np.ndarray:
    """A single-frame 2D pose with a valid spine (hip/shoulder) and a NaN or
    valid HEAD. In normalized coords ([0,1]) or pixel coords.

    When `nan_head`, the HEAD keypoint is NaN — the occlusion case. The render
    guard checks only LHIP/RHIP/LSHOULDER/RSHOULDER (NOT HEAD), so a NaN HEAD
    slips through to `_draw_head_alignment`, where:
      - pixel path: `int(nan)` → ValueError crash;
      - normalized path: `normalized_to_pixel` masks NaN → (0,0) → garbage
        indicator drawn from the frame origin.
    """
    if normalized:
        pose = np.zeros((17, 2), dtype=np.float32)
        pose[H36Key.LHIP] = [0.40, 0.70]
        pose[H36Key.RHIP] = [0.50, 0.70]
        pose[H36Key.LSHOULDER] = [0.42, 0.40]
        pose[H36Key.RSHOULDER] = [0.48, 0.40]
        pose[H36Key.HEAD] = [np.nan, np.nan] if nan_head else [0.45, 0.20]
    else:
        pose = np.zeros((17, 2), dtype=np.float32)
        pose[H36Key.LHIP] = [200.0, 350.0]
        pose[H36Key.RHIP] = [250.0, 350.0]
        pose[H36Key.LSHOULDER] = [210.0, 200.0]
        pose[H36Key.RSHOULDER] = [240.0, 200.0]
        pose[H36Key.HEAD] = [np.nan, np.nan] if nan_head else [225.0, 100.0]
    return pose


def _count_head_alignment_lines(layer, frame, ctx) -> int:
    """Render and count cv2.line calls using the head-alignment color
    (HEAD_COLOR = (180, 130, 255), line 310). A correct graceful-skip draws
    ZERO such lines when the head is NaN.
    """
    import src.visualization.layers.vertical_axis_layer as mod

    calls = []
    orig_line = mod.cv2.line

    def spy(img, p1, p2, color, thickness=None, *a, **k):
        calls.append(tuple(color) if color is not None else None)
        th = thickness if thickness is not None else 1
        return orig_line(img, p1, p2, color, th, *a, **k)

    mod.cv2.line = spy
    try:
        layer.render(frame, ctx)
    finally:
        mod.cv2.line = orig_line
    return sum(1 for c in calls if c == HEAD_COLOR)


# --------------------------------------------------------------------------- #
# Observable 1: a NaN HEAD in PIXEL coords must NOT crash render — graceful
# skip, NOT ValueError.
# --------------------------------------------------------------------------- #


def test_nan_head_pixel_render_does_not_crash_repro():
    """CORRECT behavior: `VerticalAxisLayer.render` with a NaN HEAD keypoint
    in pixel coords (`normalized=False`) must NOT raise. It must graceful-skip
    the head-alignment indicator (or the whole layer) and return the frame,
    NOT crash with `ValueError: cannot convert float NaN to integer`.

    RED now: NaN HEAD (pixel) → render guard checks only hip/shoulder (NOT
    HEAD) → slips through to `_draw_head_alignment` → `head_pt = head[:2]` is
    NaN → `spine_len_sq < 1.0` guard (line 295) checks LENGTH not NaN →
    `t = ... = nan` → `min(1.0, nan) = 1.0` (#454) → `offset = nan` →
    `nan < 3.0` is False (no skip) → `int(head_pt[0]) = int(nan)` → ValueError
    crash. After the fix: HEAD is guarded (added to `required_keys`, or
    `np.isfinite(head_pt)` check in `_draw_head_alignment`) and the render
    returns the frame unchanged.
    """
    w, h = 640, 480
    ctx = LayerContext(
        frame_width=w, frame_height=h, normalized=False,
        pose_2d=_pose(nan_head=True, normalized=False),
    )
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    layer = VerticalAxisLayer()

    try:
        out = layer.render(frame, ctx)
    except Exception as e:
        raise AssertionError(
            f"BUG: VerticalAxisLayer.render raised {type(e).__name__}: {e} "
            f"for a NaN HEAD keypoint in pixel coords (normalized=False). The "
            f"render guard checks only LHIP/RHIP/LSHOULDER/RSHOULDER (NOT HEAD, "
            f"line 108), so a NaN HEAD slips through to "
            f"`_draw_head_alignment`, where `head_pt = head[:2]` is NaN, the "
            f"`spine_len_sq < 1.0` guard (line 295) checks LENGTH not NaN, "
            f"`t = nan`, `min(1.0, nan) = 1.0` (#454 arg-order trap), "
            f"`offset = nan`, `nan < 3.0` is False (no skip, line 304), and "
            f"`int(head_pt[0]) = int(nan)` raises ValueError (line 308). A NaN "
            f"HEAD (common — head off-frame during rotations) crashes the whole "
            f"frame render → the visualization pipeline aborts → the user gets a "
            f"broken annotated video. The layer must graceful-skip the "
            f"head-alignment indicator (add HEAD to `required_keys`, or guard "
            f"`head_pt` in `_draw_head_alignment`), NOT crash."
        ) from e

    # If it did not crash, the frame must be returned unchanged (no indicator).
    assert out is not None, (
        "BUG: VerticalAxisLayer.render returned None for a NaN HEAD (pixel); "
        "expected the frame."
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN HEAD in NORMALIZED coords must NOT draw a garbage
# head-alignment indicator from the frame origin (0,0) — graceful skip, NOT
# silent wrong output.
# --------------------------------------------------------------------------- #


def test_nan_head_normalized_render_no_garbage_indicator_repro():
    """CORRECT behavior: `VerticalAxisLayer.render` with a NaN HEAD keypoint
    in normalized coords (`normalized=True`) must NOT draw a head-alignment
    indicator. The `normalized_to_pixel` array-branch masks NaN to (0,0), so
    no crash, but a GARBAGE indicator line is drawn from the frame origin
    (0,0) to the spine projection — a misleading visual artifact on a frame
    where the head was NOT detected. The layer must graceful-skip the
    indicator (zero HEAD_COLOR lines), NOT draw garbage from (0,0).

    RED now: NaN HEAD (normalized) → `normalized_to_pixel` masks NaN → (0,0)
    → render guard checks only hip/shoulder (NOT HEAD) → slips through →
    `head_pt = (0,0)` → `offset = norm((0,0) - projection)` is large (> 3.0)
    → `int(0)` no crash → `cv2.line((0,0), projection, HEAD_COLOR)` draws a
    garbage indicator from the top-left corner. After the fix: HEAD is guarded
    and zero HEAD_COLOR lines are drawn.
    """
    w, h = 640, 480
    ctx = LayerContext(
        frame_width=w, frame_height=h, normalized=True,
        pose_2d=_pose(nan_head=True, normalized=True),
    )
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    layer = VerticalAxisLayer()

    n_head_lines = _count_head_alignment_lines(layer, frame, ctx)

    # CORRECT contract: ZERO head-alignment indicator lines when HEAD is NaN.
    assert n_head_lines == 0, (
        f"BUG: VerticalAxisLayer.render drew {n_head_lines} head-alignment "
        f"indicator line(s) (color {HEAD_COLOR}) for a NaN HEAD keypoint in "
        f"normalized coords. `normalized_to_pixel` masks NaN to (0,0) "
        f"(array-branch, geometry.py:74), so no crash, but a GARBAGE indicator "
        f"is drawn from the frame origin (0,0) to the spine projection — a "
        f"misleading visual artifact on a frame where the head was NOT "
        f"detected, polluting the user-facing HUD. The render guard checks "
        f"only LHIP/RHIP/LSHOULDER/RSHOULDER (NOT HEAD, line 108), so the NaN "
        f"HEAD slips through. The layer must graceful-skip the head-alignment "
        f"indicator (add HEAD to `required_keys`), NOT draw garbage from (0,0)."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the bug triggers on NaN HEAD regardless of which other joints
# are valid — the head is the only unguarded required joint.
# --------------------------------------------------------------------------- #


def test_nan_head_only_render_does_not_crash_repro():
    """CORRECT behavior: `render` with a NaN HEAD and ALL OTHER joints valid
    must NOT crash (pixel) and must NOT draw a garbage indicator (normalized).
    The head is the ONLY required joint for the head-alignment indicator that
    is NOT in `required_keys` — the bug triggers whenever the head alone is
    occluded, even when the rest of the body is fully detected.

    RED now: only HEAD NaN, hips/shoulders valid → render guard passes (HEAD
    not checked) → `_draw_head_alignment` runs on NaN head → crash (pixel) /
    garbage (normalized). After the fix: HEAD is guarded and both paths skip.
    """
    w, h = 640, 480
    # Pixel path — must not crash.
    ctx_px = LayerContext(
        frame_width=w, frame_height=h, normalized=False,
        pose_2d=_pose(nan_head=True, normalized=False),
    )
    layer = VerticalAxisLayer()
    try:
        layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx_px)
    except Exception as e:
        raise AssertionError(
            f"BUG: VerticalAxisLayer.render raised {type(e).__name__}: {e} "
            f"for a NaN HEAD with all other joints valid (pixel). The head is "
            f"the ONLY required joint for the head-alignment indicator that is "
            f"NOT in `required_keys` (line 108) — the bug triggers whenever "
            f"the head alone is occluded, even when the rest of the body is "
            f"fully detected. A fix that only guards the head in some paths "
            f"but not the render entry leaves the other path broken."
        ) from e


# --------------------------------------------------------------------------- #
# Regression guard: an all-valid pose still renders the head-alignment
# indicator (the fix must not suppress the valid case).
# --------------------------------------------------------------------------- #


def test_all_valid_head_alignment_drawn_repro():
    """Regression guard: an all-valid pose (HEAD finite, offset > 3.0 from
    spine) must still draw the head-alignment indicator. The fix (add HEAD to
    `required_keys` / guard `head_pt`) must not suppress the valid case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot regress
    the all-valid case.
    """
    w, h = 640, 480
    ctx = LayerContext(
        frame_width=w, frame_height=h, normalized=False,
        pose_2d=_pose(nan_head=False, normalized=False),
    )
    layer = VerticalAxisLayer()
    n_head_lines = _count_head_alignment_lines(
        layer, np.zeros((h, w, 3), dtype=np.uint8), ctx
    )
    assert n_head_lines >= 1, (
        f"BUG (regression): all-valid pose (HEAD finite, offset > 3.0) drew "
        f"{n_head_lines} head-alignment indicator line(s); expected >= 1. The "
        f"valid case must be unchanged by the NaN-aware fix — the indicator "
        f"must still draw when the head is finite and off the spine line."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `required_keys` does NOT include HEAD +
# unguarded `int(head_pt[0])` conversion + `min(1.0, t)` #454 clamp.
# --------------------------------------------------------------------------- #


def test_vertical_axis_head_nan_crash_source_repro():
    """Source check: `render`'s `required_keys` guard checks only
    (LHIP, RHIP, LSHOULDER, RSHOULDER) — NOT HEAD (line 108), and
    `_draw_head_alignment` does `hx, hy = int(head_pt[0]), int(head_pt[1])`
    (line 308) with NO NaN guard, and clamps `t = max(0.0, min(1.0, t))`
    (line 300) — the #454 arg-order trap (`min(1.0, nan) = 1.0`). Root cause
    locked.

    RED now: the no-HEAD guard + unguarded `int()` + `min(1.0, t)` clamp are
    present (PASS — root cause locked). After the fix: HEAD is added to
    `required_keys` (or a `np.isfinite(head_pt)` guard appears in
    `_draw_head_alignment`) — this test FAILS, signaling the observable tests
    above should flip to GREEN.
    """
    render_src = inspect.getsource(VerticalAxisLayer.render)
    # The render guard checks only hip/shoulder, NOT HEAD.
    assert "required_keys = (H36Key.LHIP, H36Key.RHIP, H36Key.LSHOULDER, H36Key.RSHOULDER)" in render_src, (
        "BUG: render must guard `required_keys = (H36Key.LHIP, H36Key.RHIP, "
        "H36Key.LSHOULDER, H36Key.RSHOULDER)` (NOT HEAD) for this repro to be "
        "valid. If H36Key.HEAD was added to `required_keys`, the NaN-HEAD "
        "crash/garbage bug is fixed — update the observable tests to the "
        "GREEN contract."
    )
    # The guard's required_keys tuple must NOT include HEAD. (H36Key.HEAD
    # legitimately appears elsewhere in render — `pose[H36Key.HEAD]` is read
    # at line 124 to build the head point — so we check the guard tuple
    # specifically, not the whole render body.)
    guard_line = next(
        (ln for ln in render_src.splitlines()
         if "required_keys" in ln and "(" in ln),
        None,
    )
    assert guard_line is not None and "H36Key.HEAD" not in guard_line, (
        f"BUG: H36Key.HEAD was added to render's `required_keys` guard tuple "
        f"({guard_line!r}) — the NaN-HEAD crash/garbage bug is fixed at the "
        f"render entry; update the observable tests to the GREEN contract."
    )

    head_src = inspect.getsource(VerticalAxisLayer._draw_head_alignment)
    # The unguarded int() conversion is present — the crash point.
    assert "hx, hy = int(head_pt[0]), int(head_pt[1])" in head_src, (
        "BUG: _draw_head_alignment must do `hx, hy = int(head_pt[0]), "
        "int(head_pt[1])` (unguarded int() conversion — `int(nan)` raises "
        "ValueError) for this repro to be valid. If a NaN guard was added "
        "(e.g. `if not np.isfinite(head_pt).all(): return`), the crash bug is "
        "fixed — update the observable tests to the GREEN contract."
    )
    # The #454 arg-order trap: `min(1.0, nan) = 1.0`. The clamp uses bare
    # `min(1.0, t)` without a NaN guard.
    assert "t = max(0.0, min(1.0, t))" in head_src, (
        "BUG: _draw_head_alignment must clamp `t = max(0.0, min(1.0, t))` "
        "(the #454 arg-order trap: `min(1.0, nan) = 1.0`) for this repro to be "
        "valid. If a NaN guard was added on `t` or `head_pt`, the crash bug is "
        "fixed — update the observable tests to the GREEN contract."
    )
    # The spine_len guard checks LENGTH only, NOT NaN in head_pt.
    assert "if spine_len_sq < 1.0:" in head_src, (
        "BUG: _draw_head_alignment must guard `if spine_len_sq < 1.0: return` "
        "(LENGTH-only guard, misses NaN in head_pt) for this repro to be "
        "valid. If a NaN guard was added, the crash bug is fixed — update the "
        "observable tests to the GREEN contract."
    )
    assert "np.isfinite" not in head_src and "np.isnan" not in head_src and \
        "nan_to_num" not in head_src, (
        "BUG: a NaN guard (`np.isfinite` / `np.isnan` / `nan_to_num`) appeared "
        "in _draw_head_alignment — the NaN-HEAD crash/garbage bug is fixed; "
        "update the observable tests to the GREEN contract."
    )