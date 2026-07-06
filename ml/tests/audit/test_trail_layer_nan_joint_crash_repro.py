"""RED repro — `TrailLayer._draw_trail_2d` CRASHES with `ValueError: cannot
convert float NaN to integer` when the TRACKED joint is NaN (partial
occlusion — rest of body valid) and poses are in PIXEL coordinates
(`normalized=False`), and SILENTLY DRAWS A GARBAGE trail segment to the frame
origin (0,0) when poses are NORMALIZED (`normalized=True`) — a NaN tracked
joint is not graceful-skipped.

Root cause (ml/src/visualization/layers/trail_layer.py):

  `render` (line 84) guards only ALL-NaN poses, NOT a NaN tracked joint:
      elif context.pose_2d is not None and not np.all(np.isnan(context.pose_2d)):
          pos = context.pose_2d[self.joint]            # 113 — NaN if joint occluded
          self._trail_2d.append(tuple(pos))             # 114 — NaN tuple appended
          ...
          self._draw_trail_2d(frame, context)           # 119

  `np.all(np.isnan(pose_2d))` is True only when EVERY joint is NaN. A partial
  occlusion (tracked joint NaN, rest valid) passes the guard — the NaN
  `pos` is appended to `_trail_2d`. Then `_draw_trail_2d`:

  `_draw_trail_2d` (123-168):
      if context.normalized:
          trail_px = [normalized_to_pixel(np.array(pos), w, h)   # 134-141
                       for pos in self._trail_2d]
          # normalized_to_pixel array-branch masks NaN → (0,0) → garbage vertex
      else:
          trail_px = [(int(pos[0]), int(pos[1])) for pos in self._trail_2d]  # 143
          # pixel path: int(nan) → ValueError CRASH

Two failure modes (same root cause — tracked joint NaN not guarded at render):
  1. PIXEL path (`normalized=False`): `int(pos[0])` where `pos[0]=nan` →
     `ValueError: cannot convert float NaN to integer` → the whole `render`
     call crashes → the visualization pipeline aborts the frame.
  2. NORMALIZED path (`normalized=True`): `normalized_to_pixel` array-branch
     masks NaN → (0,0), so no crash, but a GARBAGE trail segment is drawn from
     the last valid vertex to the frame origin (0,0) — a spurious trail vertex
     polluting the user-facing HUD on a frame where the tracked joint was
     occluded.

Consequences (prod impact — `TrailLayer` is a user-facing HUD layer, rendered
for every analyzed frame, tracking the foot/ankle trajectory over time):
  1. PIXEL path: a NaN tracked joint (foot occluded / off-frame — common in
     figure skating, the free foot frequently leaves frame during spins) →
     `int(nan)` raises → the whole frame render crashes → the visualization
     pipeline aborts → the user gets a broken/missing annotated video. The
     crash message ("cannot convert float NaN to integer") gives NO hint the
     cause is an occluded joint.
  2. NORMALIZED path: no crash, but a garbage trail segment to (0,0) is drawn
     into the user-facing video — a misleading motion-trail artifact on frames
     with an occluded joint, polluting the coach/athlete review.
  3. The render guard `not np.all(np.isnan(context.pose_2d))` (line 112) is
     too weak — it passes partial occlusion (one joint NaN, rest valid). The
     tracked joint `self.joint` is the only point that matters for the trail,
     yet it is not checked for NaN. A per-joint guard
     (`if not np.isfinite(pos).all(): skip append` or `np.isnan(pos).any()`)
     fixes both paths.
  4. The bug composes with tracking: a track switch / gap-fill failure can
     produce a NaN keypoint for one joint on an otherwise-valid frame; the
     trail then crashes (pixel) or draws garbage (normalized) instead of
     graceful-skipping that vertex.
  5. Existing tests miss it: `test_trail*` feed all-valid keypoints. No test
     feeds a NaN tracked joint (rest valid) through `render` and asserts it
     does not crash / does not draw a garbage origin segment.
  6. Same class as CA (VerticalAxisLayer NaN HEAD) — the `int(nan)` crash +
     `normalized_to_pixel` masks NaN to (0,0) garbage pattern repeats across
     visualization layers.

The fix (NOT applied — repro only):
  - guard the tracked joint at render (line 113):
    `pos = context.pose_2d[self.joint];`
    `if np.isnan(pos).any(): pass  # skip append — occluded joint` (do not
    append NaN to the trail, do not draw this frame); and/or
  - guard `_draw_trail_2d` (line 143):
    `trail_px = [(int(pos[0]), int(pos[1])) for pos in self._trail_2d
                 if not np.isnan(pos).any()]` (skip NaN vertices); and/or
  - mask NaN in `normalized_to_pixel` to a sentinel that `_draw_trail_2d`
    skips (not (0,0), which draws garbage) — but the per-joint guard is
    cleaner.
  The cleanest fix: do not append a NaN `pos` to `_trail_2d` at render (the
  trail simply does not grow this frame — graceful skip).

The correct contract: a NaN tracked joint (partial occlusion, rest of body
valid) must NOT crash `render` and must NOT draw a garbage trail segment to
the origin. The layer must graceful-skip the trail vertex (do not append NaN,
do not draw this frame's segment) — NOT crash, NOT draw garbage.

RED now: the observable assertions below describe the CORRECT behavior — a
NaN tracked joint (rest valid) must NOT raise (pixel path) and must NOT draw
a trail segment to (0,0) (normalized path). They FAIL because the render
guard is `not np.all(np.isnan(...))` (passes partial occlusion) and
`_draw_trail_2d` does `int(nan)` (crash) / `normalized_to_pixel` masks to
(0,0) (garbage). After the fix: the tracked joint is guarded and the NaN
vertex is skipped. The source-check test confirms the
`not np.all(np.isnan(context.pose_2d))` (all-NaN, not per-joint) guard and the
unguarded `int(pos[0])` line are present (root cause locked).

Pure-Python (no GPU, no DB): `TrailLayer.render` and `_draw_trail_2d` are
pure-data functions over a pose array + a frame buffer.
"""

import inspect

import cv2
import numpy as np

import src.visualization.layers.trail_layer as mod
from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.trail_layer import TrailLayer


def _valid_pose(i: int, normalized: bool) -> np.ndarray:
    """A pose with a valid LFOOT (the tracked joint) at step `i`."""
    pose = np.zeros((17, 2), dtype=np.float32)
    if normalized:
        pose[H36Key.LFOOT] = [0.20 + i * 0.01, 0.80]
        pose[H36Key.LHIP] = [0.45, 0.50]
    else:
        pose[H36Key.LFOOT] = [100.0 + i * 10.0, 400.0]
        pose[H36Key.LHIP] = [250.0, 300.0]
    return pose


def _nan_joint_pose(normalized: bool) -> np.ndarray:
    """A pose where ONLY the tracked joint (LFOOT) is NaN, rest valid —
    partial occlusion. The render guard `not np.all(np.isnan(pose_2d))` passes
    (not ALL joints NaN), so the NaN `pos` is appended to the trail."""
    pose = np.zeros((17, 2), dtype=np.float32)
    if normalized:
        pose[H36Key.LFOOT] = [np.nan, np.nan]
        pose[H36Key.LHIP] = [0.45, 0.50]
        pose[H36Key.RHIP] = [0.50, 0.50]
    else:
        pose[H36Key.LFOOT] = [np.nan, np.nan]
        pose[H36Key.LHIP] = [250.0, 300.0]
        pose[H36Key.RHIP] = [260.0, 300.0]
    return pose


def _render_and_collect_lines(layer, frame, ctx) -> list[tuple]:
    """Render and collect cv2.line call (p1, p2) tuples."""
    calls = []
    orig_line = mod.cv2.line

    def spy(img, p1, p2, color, thickness=None, *a, **k):
        calls.append((tuple(p1), tuple(p2)))
        th = thickness if thickness is not None else 1
        return orig_line(img, p1, p2, color, th, *a, **k)

    mod.cv2.line = spy
    try:
        layer.render(frame, ctx)
    finally:
        mod.cv2.line = orig_line
    return calls


# --------------------------------------------------------------------------- #
# Observable 1: a NaN tracked joint in PIXEL coords must NOT crash render —
# graceful skip, NOT ValueError.
# --------------------------------------------------------------------------- #


def test_nan_joint_pixel_render_does_not_crash_repro():
    """CORRECT behavior: `TrailLayer.render` with a NaN TRACKED joint (LFOOT,
    rest valid) in pixel coords (`normalized=False`) must NOT raise. It must
    graceful-skip the trail vertex (do not append NaN, do not draw this
    frame's segment) and return the frame, NOT crash with `ValueError:
    cannot convert float NaN to integer`.

    RED now: NaN LFOOT (rest valid, pixel) → render guard
    `not np.all(np.isnan(pose_2d))` is True (not ALL NaN) → guard passes →
    `pos = pose_2d[LFOOT]` = NaN → `self._trail_2d.append((nan, nan))` →
    `_draw_trail_2d` → `trail_px = [(int(pos[0]), int(pos[1])) ...]` (line 143)
    → `int(nan)` → ValueError crash. After the fix: the tracked joint is
    guarded (per-joint NaN check) and the NaN vertex is skipped (not
    appended), so render returns the frame unchanged.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT)
    # Build a valid trail first (5 frames) so the trail has >= 2 points.
    for i in range(5):
        ctx = LayerContext(
            frame_width=w, frame_height=h, normalized=False,
            pose_2d=_valid_pose(i, normalized=False),
        )
        layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)

    # NaN tracked joint (rest valid) — partial occlusion.
    ctx_nan = LayerContext(
        frame_width=w, frame_height=h, normalized=False,
        pose_2d=_nan_joint_pose(normalized=False),
    )
    try:
        out = layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx_nan)
    except Exception as e:
        raise AssertionError(
            f"BUG: TrailLayer.render raised {type(e).__name__}: {e} for a NaN "
            f"TRACKED joint (LFOOT, rest valid) in pixel coords "
            f"(normalized=False). The render guard `not np.all(np.isnan("
            f"pose_2d))` (line 112) passes partial occlusion (not ALL joints "
            f"NaN), so the NaN `pos = pose_2d[self.joint]` is appended to "
            f"`_trail_2d` (line 114); `_draw_trail_2d` then does "
            f"`trail_px = [(int(pos[0]), int(pos[1])) ...]` (line 143) and "
            f"`int(nan)` raises ValueError. A NaN tracked joint (free foot "
            f"off-frame during spins — common in figure skating) crashes the "
            f"whole frame render → the visualization pipeline aborts → the "
            f"user gets a broken annotated video. The layer must graceful-skip "
            f"the NaN vertex (per-joint NaN guard at render), NOT crash."
        ) from e

    assert out is not None, (
        "BUG: TrailLayer.render returned None for a NaN tracked joint (pixel); "
        "expected the frame."
    )


# --------------------------------------------------------------------------- #
# Observable 2: a NaN tracked joint in NORMALIZED coords must NOT draw a
# garbage trail segment to the frame origin (0,0) — graceful skip.
# --------------------------------------------------------------------------- #


def test_nan_joint_normalized_render_no_garbage_origin_segment_repro():
    """CORRECT behavior: `TrailLayer.render` with a NaN TRACKED joint (LFOOT,
    rest valid) in normalized coords (`normalized=True`) must NOT draw a
    trail segment to the frame origin (0,0). `normalized_to_pixel` array-branch
    masks NaN to (0,0), so no crash, but a GARBAGE segment is drawn from the
    last valid vertex to (0,0) — a spurious trail vertex polluting the
    user-facing HUD. The layer must graceful-skip the NaN vertex (do not
    append NaN, do not draw a segment to origin), NOT draw garbage.

    RED now: NaN LFOOT (normalized) → guard passes → NaN appended →
    `normalized_to_pixel(np.array([nan,nan]), w, h)` → array-branch masks NaN
    → (0,0) → `_draw_trail_2d` draws segment from last valid vertex to (0,0).
    After the fix: the tracked joint is guarded and no segment to (0,0) is
    drawn.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT, smoothing=False)
    # Build a valid trail (5 frames).
    for i in range(5):
        ctx = LayerContext(
            frame_width=w, frame_height=h, normalized=True,
            pose_2d=_valid_pose(i, normalized=True),
        )
        layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)

    # NaN tracked joint — partial occlusion. Collect the lines drawn this frame.
    ctx_nan = LayerContext(
        frame_width=w, frame_height=h, normalized=True,
        pose_2d=_nan_joint_pose(normalized=True),
    )
    calls = _render_and_collect_lines(
        layer, np.zeros((h, w, 3), dtype=np.uint8), ctx_nan
    )

    # CORRECT contract: NO line segment may end at or start at the frame origin
    # (0,0) — a NaN tracked joint must not produce a garbage origin vertex.
    origin_segments = [
        (p1, p2) for p1, p2 in calls
        if tuple(int(v) for v in p1) == (0, 0) or tuple(int(v) for v in p2) == (0, 0)
    ]
    assert not origin_segments, (
        f"BUG: TrailLayer.render drew {len(origin_segments)} trail segment(s) "
        f"to the frame origin (0,0) for a NaN TRACKED joint (LFOOT, rest valid) "
        f"in normalized coords: {origin_segments}. `normalized_to_pixel` "
        f"array-branch masks NaN to (0,0) (geometry.py:74), so no crash, but a "
        f"GARBAGE segment is drawn from the last valid vertex to the frame "
        f"origin — a spurious trail vertex polluting the user-facing HUD on a "
        f"frame where the tracked joint was occluded. The render guard `not "
        f"np.all(np.isnan(pose_2d))` (line 112) passes partial occlusion, so the "
        f"NaN `pos` is appended. The layer must graceful-skip the NaN vertex "
        f"(per-joint NaN guard at render), NOT draw garbage to (0,0)."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the bug triggers regardless of which joint is tracked — a
# NaN in ANY tracked joint (foot, ankle, hand) crashes / draws garbage.
# --------------------------------------------------------------------------- #


def test_nan_tracked_joint_any_joint_does_not_crash_repro():
    """CORRECT behavior: the crash triggers for ANY tracked joint, not just
    LFOOT. `TrailLayer(joint=K)` with joint K NaN (rest valid) must NOT crash
    (pixel) — the bug has a wide blast radius across joints.

    RED now: NaN RKNEE / RWRIST / LANKLE (rest valid, pixel) each →
    `int(nan)` crash. After the fix: graceful skip on any occluded tracked
    joint.
    """
    w, h = 640, 480
    for joint in (H36Key.RKNEE, H36Key.RWRIST, H36Key.LFOOT):
        layer = TrailLayer(joint=joint)
        for i in range(5):
            pose = np.zeros((17, 2), dtype=np.float32)
            pose[joint] = [100.0 + i * 10.0, 400.0]
            ctx = LayerContext(
                frame_width=w, frame_height=h, normalized=False, pose_2d=pose,
            )
            layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx)

        pose_nan = np.zeros((17, 2), dtype=np.float32)
        pose_nan[H36Key.LHIP] = [250.0, 300.0]  # rest valid
        pose_nan[joint] = [np.nan, np.nan]       # tracked joint NaN
        ctx_nan = LayerContext(
            frame_width=w, frame_height=h, normalized=False, pose_2d=pose_nan,
        )
        try:
            layer.render(np.zeros((h, w, 3), dtype=np.uint8), ctx_nan)
        except Exception as e:
            raise AssertionError(
                f"BUG: TrailLayer.render raised {type(e).__name__}: {e} for "
                f"a NaN tracked joint {joint.name} (rest valid, pixel). The "
                f"crash triggers for ANY tracked joint, not just LFOOT — the "
                f"render guard `not np.all(np.isnan(pose_2d))` passes partial "
                f"occlusion regardless of which joint is tracked. A fix that "
                f"only guards LFOOT would leave the other tracked-joint configs "
                f"broken."
            ) from e


# --------------------------------------------------------------------------- #
# Regression guard: an all-valid pose still draws the trail (the fix must not
# suppress the valid case).
# --------------------------------------------------------------------------- #


def test_all_valid_trail_drawn_repro():
    """Regression guard: an all-valid pose (tracked joint finite) must still
    draw the trail. The fix (per-joint NaN guard) must not suppress the valid
    case.

    This PASSES today; it locks the contract so a NaN-aware fix cannot
    regress the all-valid case.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT, smoothing=False)
    for i in range(5):
        ctx = LayerContext(
            frame_width=w, frame_height=h, normalized=False,
            pose_2d=_valid_pose(i, normalized=False),
        )
        calls = _render_and_collect_lines(
            layer, np.zeros((h, w, 3), dtype=np.uint8), ctx
        )
    assert len(calls) >= 1, (
        f"BUG (regression): all-valid pose drew {len(calls)} trail segments; "
        f"expected >= 1. The valid case must be unchanged by the NaN-aware fix "
        f"— the trail must still draw when the tracked joint is finite."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — render guard is `np.all(np.isnan(...))`
# (all-NaN, not per-joint) + unguarded `int(pos[0])` in _draw_trail_2d.
# --------------------------------------------------------------------------- #


def test_trail_layer_nan_joint_crash_source_repro():
    """Source check: `render` guards `not np.all(np.isnan(context.pose_2d))`
    (line 112 — all-NaN, NOT per-joint — passes partial occlusion), then
    appends `pos = context.pose_2d[self.joint]` (line 113) with no NaN check,
    and `_draw_trail_2d` does `trail_px = [(int(pos[0]), int(pos[1])) for pos
    in self._trail_2d]` (line 143) — unguarded `int()` conversion. Root cause
    locked.

    RED now: the all-NaN guard + unguarded `int(pos[0])` are present (PASS —
    root cause locked). After the fix: a per-joint NaN guard
    (`np.isnan(pos).any()` / `np.isfinite(pos).all()` / skip append) appears
    in render or `_draw_trail_2d` — this test FAILS, signaling the observable
    tests above should flip to GREEN.
    """
    render_src = inspect.getsource(TrailLayer.render)
    # The all-NaN guard (passes partial occlusion) is present.
    assert "not np.all(np.isnan(context.pose_2d))" in render_src, (
        "BUG: render must guard `not np.all(np.isnan(context.pose_2d))` "
        "(all-NaN, passes partial occlusion) for this repro to be valid. If a "
        "per-joint NaN guard was added (e.g. `if np.isnan(pos).any(): skip`), "
        "the crash bug is fixed — update the observable tests to the GREEN "
        "contract."
    )
    # The tracked joint is read with no NaN check, then appended.
    assert "pos = context.pose_2d[self.joint]" in render_src, (
        "BUG: render must read `pos = context.pose_2d[self.joint]` (no NaN "
        "check) for this repro to be valid. If a NaN guard was added on `pos`, "
        "the crash bug is fixed — update the observable tests to the GREEN "
        "contract."
    )
    # No per-joint NaN guard in render.
    assert "np.isnan(pos)" not in render_src and "np.isfinite(pos)" not in render_src, (
        "BUG: a per-joint NaN guard (`np.isnan(pos)` / `np.isfinite(pos)`) "
        "appeared in render — the NaN tracked-joint crash bug is fixed; update "
        "the observable tests to the GREEN contract."
    )

    draw_src = inspect.getsource(TrailLayer._draw_trail_2d)
    # The unguarded int() conversion is present — the crash point.
    assert "trail_px = [(int(pos[0]), int(pos[1])) for pos in self._trail_2d]" in draw_src, (
        "BUG: _draw_trail_2d must do `trail_px = [(int(pos[0]), int(pos[1])) "
        "for pos in self._trail_2d]` (unguarded int() — `int(nan)` raises "
        "ValueError) for this repro to be valid. If a NaN guard / skip was "
        "added (e.g. `if not np.isnan(pos).any()`), the crash bug is fixed — "
        "update the observable tests to the GREEN contract."
    )
    assert "np.isnan" not in draw_src and "np.isfinite" not in draw_src and \
        "nan_to_num" not in draw_src, (
        "BUG: a NaN guard (`np.isnan` / `np.isfinite` / `nan_to_num`) appeared "
        "in _draw_trail_2d — the NaN tracked-joint crash bug is fixed; update "
        "the observable tests to the GREEN contract."
    )