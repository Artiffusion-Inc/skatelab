"""Repro / contract test for issue #1089 — `TrailLayer` partial-NaN entry crash.

`TrailLayer.render` appends `context.pose_2d[self.joint]` to `_trail_2d`
unconditionally when the pose is non-all-NaN. The render guard
`not np.all(np.isnan(context.pose_2d))` catches only the all-joints-NaN case
(it is True for partial occlusion). A single-joint NaN (free foot off-frame
during spins — common in figure skating) is then appended to the trail, and
`_draw_trail_2d` does `int(pos[0])` (pixel mode) → `ValueError: cannot
convert float NaN to integer` → the whole frame render crashes → the
visualization pipeline aborts → the user gets a broken annotated video.

In normalized mode the same partial-NaN case does not crash
(`normalized_to_pixel` masks NaN → (0,0)) but a garbage trail segment is
drawn from the last valid vertex to the frame origin — a spurious trail
vertex polluting the user-facing HUD on a frame where the tracked joint was
occluded.

Correct contract: a NaN tracked joint (partial occlusion, rest of body
valid) must NOT crash `render` and must NOT draw a garbage origin segment.
The layer must graceful-skip the trail vertex (do not append NaN, do not
draw this frame's segment).

The current source (ml/src/visualization/layers/trail_layer.py) implements
this contract via a per-joint NaN guard in `render`:

    if context.pose_2d is not None and not np.all(np.isnan(context.pose_2d)):
        pos = context.pose_2d[self.joint]
        if np.isnan(pos).any():
            return frame                        # skip the occluded vertex
        self._trail_2d.append(tuple(pos))
        ...

These tests pin the contract — they were RED against the pre-#892 source
and are GREEN against the current source.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import numpy as np

from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.trail_layer import TrailLayer

if TYPE_CHECKING:
    from numpy.typing import NDArray

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _valid_pose(x: float, y: float) -> np.ndarray:
    """A pose with a valid LFOOT (the tracked joint) at (x, y), pixel coords."""
    pose = np.zeros((17, 2), dtype=np.float32)
    pose[H36Key.LFOOT] = [x, y]
    pose[H36Key.LHIP] = [250.0, 300.0]
    return pose


def _valid_pose_norm(x: float, y: float) -> np.ndarray:
    """A pose with a valid LFOOT (the tracked joint) at (x, y), normalized."""
    pose = np.zeros((17, 2), dtype=np.float32)
    pose[H36Key.LFOOT] = [x, y]
    pose[H36Key.LHIP] = [0.45, 0.50]
    return pose


def _nan_joint_pose_pixel() -> np.ndarray:
    """A pose where ONLY the tracked joint (LFOOT) is NaN — partial occlusion."""
    pose = np.zeros((17, 2), dtype=np.float32)
    pose[H36Key.LFOOT] = [np.nan, np.nan]
    pose[H36Key.LHIP] = [250.0, 300.0]
    pose[H36Key.RHIP] = [260.0, 300.0]
    return pose


def _nan_joint_pose_norm() -> np.ndarray:
    """A pose where ONLY the tracked joint (LFOOT) is NaN — normalized."""
    pose = np.zeros((17, 2), dtype=np.float32)
    pose[H36Key.LFOOT] = [np.nan, np.nan]
    pose[H36Key.LHIP] = [0.45, 0.50]
    pose[H36Key.RHIP] = [0.50, 0.50]
    return pose


def _all_nan_pose() -> np.ndarray:
    """A pose where every joint is NaN — full occlusion / detection gap."""
    return np.full((17, 2), np.nan, dtype=np.float32)


def _spy_line(
    drawn: list[tuple[tuple[int, int], tuple[int, int]]],
    orig_line: Any,
    img: NDArray[np.uint8],
    p1: tuple[float, float],
    p2: tuple[float, float],
    color: tuple[int, int, int],
    thickness: int | None = None,
    *a: Any,
    **k: Any,
) -> NDArray[np.uint8]:
    """cv2.line wrapper that records (p1, p2) before delegating to `orig_line`."""
    p1_int: tuple[int, int] = (int(p1[0]), int(p1[1]))
    p2_int: tuple[int, int] = (int(p2[0]), int(p2[1]))
    drawn.append((p1_int, p2_int))
    th = thickness if thickness is not None else 1
    return orig_line(img, p1, p2, color, th, *a, **k)


# --------------------------------------------------------------------------- #
# 1. Partial-NaN trail entry: pixel mode must not crash on int(NaN).
# --------------------------------------------------------------------------- #


def test_partial_nan_tracked_joint_pixel_mode_does_not_crash():
    """A NaN tracked joint (LFOOT, rest valid) in pixel coords must not
    raise. The render guard `not np.all(np.isnan(pose_2d))` passes partial
    occlusion, so the pre-fix code appended a NaN vertex; the fix
    guards the tracked joint and skips the vertex — render returns the
    frame unchanged, no `ValueError: cannot convert float NaN to integer`.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT, smoothing=False)
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    # Build a valid trail first so the layer has >= 2 points to draw.
    for i in range(5):
        ctx = LayerContext(
            frame_width=w,
            frame_height=h,
            normalized=False,
            pose_2d=_valid_pose(100.0 + i * 10.0, 400.0),
        )
        layer.render(frame, ctx)

    # Now feed a partial-NaN pose: tracked joint NaN, rest valid.
    ctx_nan = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_nan_joint_pose_pixel(),
    )
    try:
        out = layer.render(frame, ctx_nan)
    except ValueError as e:
        raise AssertionError(
            "TrailLayer.render raised ValueError for a NaN tracked joint "
            "(LFOOT, rest valid, pixel coords). The render guard "
            "`not np.all(np.isnan(pose_2d))` passed partial occlusion, the "
            "NaN `pos = pose_2d[self.joint]` was appended, and "
            "`_draw_trail_2d` did `int(pos[0])` -> ValueError. The fix "
            "guards the tracked joint (per-joint NaN check) and skips the "
            "vertex — render must return the frame unchanged."
        ) from e

    assert out is not None, "render returned None for a NaN tracked joint (pixel)"
    # The NaN vertex must not be appended to the trail.
    assert len(layer._trail_2d) == 5, (
        f"Trail was appended to after a NaN tracked joint: len={len(layer._trail_2d)} "
        f"(expected 5, the prior valid entries)."
    )
    for pt in layer._trail_2d:
        assert all(np.isfinite(v) for v in pt), (
            f"Trail contains a non-finite entry: {pt} — the per-joint guard "
            f"must skip NaN vertices, not append them."
        )


# --------------------------------------------------------------------------- #
# 2. All-NaN trail: full occlusion must not crash or corrupt.
# --------------------------------------------------------------------------- #


def test_all_nan_pose_does_not_crash_pixel_mode():
    """A pose where every joint is NaN must not crash render and must not
    append to the trail. The all-NaN guard at the render level catches this
    — the per-joint guard is an additional defence for partial occlusion.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT, smoothing=False)
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    for i in range(5):
        ctx = LayerContext(
            frame_width=w,
            frame_height=h,
            normalized=False,
            pose_2d=_valid_pose(100.0 + i * 10.0, 400.0),
        )
        layer.render(frame, ctx)
    before = len(layer._trail_2d)

    ctx_nan = LayerContext(
        frame_width=w,
        frame_height=h,
        normalized=False,
        pose_2d=_all_nan_pose(),
    )
    try:
        layer.render(frame, ctx_nan)
    except ValueError as e:
        raise AssertionError(
            "TrailLayer.render raised ValueError for an all-NaN pose "
            "(pixel mode). The all-NaN pose guard must skip the frame."
        ) from e

    assert len(layer._trail_2d) == before, (
        f"All-NaN pose appended to the trail: before={before}, after="
        f"{len(layer._trail_2d)}. The all-NaN pose guard must skip appends."
    )


# --------------------------------------------------------------------------- #
# 3. Valid finite regression: an all-valid pose still draws the trail.
# --------------------------------------------------------------------------- #


def test_valid_finite_pose_still_draws_trail_pixel_mode():
    """Regression guard: an all-valid pose (tracked joint finite) must still
    append to the trail and produce at least one drawn segment. The fix
    must not suppress the valid case.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT, smoothing=False)
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    drawn: list[tuple[tuple[int, int], tuple[int, int]]] = []
    import src.visualization.layers.trail_layer as mod

    orig_line = mod.cv2.line
    mod.cv2.line = lambda img, p1, p2, color, thickness=None, *a, **k: _spy_line(  # type: ignore[assignment]
        drawn, orig_line, img, p1, p2, color, thickness, *a, **k
    )
    try:
        for i in range(5):
            ctx = LayerContext(
                frame_width=w,
                frame_height=h,
                normalized=False,
                pose_2d=_valid_pose(100.0 + i * 10.0, 400.0),
            )
            layer.render(frame, ctx)
    finally:
        mod.cv2.line = orig_line

    assert len(layer._trail_2d) == 5, (
        f"Trail not populated for valid pose: len={len(layer._trail_2d)}"
    )
    for pt in layer._trail_2d:
        assert all(np.isfinite(v) for v in pt), (
            f"Trail contains a non-finite entry on the valid path: {pt}"
        )
    assert len(drawn) >= 1, (
        f"No trail segments drawn for valid pose: {len(drawn)} line calls. "
        f"The per-joint guard must not suppress the all-finite case."
    )


# --------------------------------------------------------------------------- #
# 4. Partial-NaN in normalized mode must not draw a garbage origin segment.
# --------------------------------------------------------------------------- #


def test_partial_nan_tracked_joint_normalized_mode_no_origin_segment():
    """A NaN tracked joint (LFOOT, rest valid) in normalized coords must not
    draw a trail segment to the frame origin (0,0). `normalized_to_pixel`
    masks NaN → (0,0) — without the per-joint guard, a garbage segment
    from the last valid vertex to (0,0) is drawn into the user-facing HUD.
    """
    w, h = 640, 480
    layer = TrailLayer(joint=H36Key.LFOOT, smoothing=False)
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    for i in range(5):
        ctx = LayerContext(
            frame_width=w,
            frame_height=h,
            normalized=True,
            pose_2d=_valid_pose_norm(0.20 + i * 0.01, 0.80),
        )
        layer.render(frame, ctx)

    import src.visualization.layers.trail_layer as mod

    drawn: list[tuple[tuple[int, int], tuple[int, int]]] = []
    orig_line = mod.cv2.line
    mod.cv2.line = lambda img, p1, p2, color, thickness=None, *a, **k: _spy_line(  # type: ignore[assignment]
        drawn, orig_line, img, p1, p2, color, thickness, *a, **k
    )
    try:
        ctx_nan = LayerContext(
            frame_width=w,
            frame_height=h,
            normalized=True,
            pose_2d=_nan_joint_pose_norm(),
        )
        layer.render(frame, ctx_nan)
    finally:
        mod.cv2.line = orig_line

    origin_segments = [
        (p1, p2)
        for p1, p2 in drawn
        if (int(p1[0]), int(p1[1])) == (0, 0) or (int(p2[0]), int(p2[1])) == (0, 0)
    ]
    assert not origin_segments, (
        f"Trail drew {len(origin_segments)} segment(s) to the frame origin "
        f"(0,0) for a NaN tracked joint (normalized): {origin_segments}. "
        f"The per-joint guard must skip the NaN vertex — no append, no draw."
    )


# --------------------------------------------------------------------------- #
# 5. Source check: per-joint NaN guard is present in render.
# --------------------------------------------------------------------------- #


def test_trail_layer_render_has_per_joint_nan_guard_source():
    """Source check: `render` must guard the tracked joint with a per-joint
    NaN check (`np.isnan(pos).any()` or equivalent `isfinite` / `not
    isnan` test) AFTER reading `pos = context.pose_2d[self.joint]`. Without
    it, partial occlusion appends a NaN vertex and crashes int(nan) in
    pixel mode / draws a garbage origin segment in normalized mode.

    The per-joint guard is the contract — if it is removed, partial
    occlusion will regress.
    """
    render_src = inspect.getsource(TrailLayer.render)

    # The all-NaN pose guard (defence-in-depth) is kept.
    assert "not np.all(np.isnan(context.pose_2d))" in render_src, (
        "render must keep `not np.all(np.isnan(context.pose_2d))` "
        "(all-NaN pose guard, defence-in-depth)."
    )
    # The tracked joint is read.
    assert "pos = context.pose_2d[self.joint]" in render_src, (
        "render must read `pos = context.pose_2d[self.joint]` before the per-joint guard."
    )
    # The per-joint NaN guard is present. The source uses `np.isnan`,
    # which is the canonical NumPy check and equivalent to
    # `not np.isfinite(pos).all()` for 2D coords. Accept either form.
    has_nan_guard = "np.isnan(pos).any()" in render_src or "np.isnan(pos)" in render_src
    has_isfinite_guard = (
        "np.isfinite(pos).all()" in render_src or "not np.isfinite(pos)" in render_src
    )
    assert has_nan_guard or has_isfinite_guard, (
        "render must guard the tracked joint with a per-joint NaN check "
        "after the read: `np.isnan(pos).any()` or `np.isfinite(pos).all()` "
        "or equivalent. Without it, partial occlusion appends a NaN "
        "vertex and crashes int(nan) (pixel) / draws a garbage origin "
        "segment (normalized)."
    )
    # The guard must skip the frame (return frame), not a silent append.
    assert "return frame" in render_src, (
        "render must `return frame` after the per-joint NaN guard — skip "
        "the occluded vertex this frame."
    )
