"""RED repro: TrailLayer NaN-then-valid pose crash (pixel mode) / corruption (normalized mode).

Root cause: trail_layer.py render() (lines 98-115) appends context.pose_2d[self.joint] /
pose_3d[self.joint] to _trail_2d / _trail_3d unconditionally when pose_2d / pose_3d is not
None — INCLUDING all-NaN poses. There is NO np.isnan guard, unlike VelocityLayer which
guards with `not np.all(np.isnan(context.pose_2d))` at velocity_layer.py:117.

Pixel-coord branch (normalized=False), _draw_trail_2d line 139:
    trail_px = [(int(pos[0]), int(pos[1])) for pos in self._trail_2d]
→ int(nan) raises ValueError: cannot convert float NaN to integer. Hard crash.

Normalized branch (normalized=True): normalized_to_pixel silently maps NaN → (0,0)
→ spurious trail vertex at frame origin → visual corruption.

Production layer: ml/src/visualization/pipeline.py:40 key "trail".
Detection gap (occlusion) → NaN frame → next valid frame crashes / corrupts.
"""

import numpy as np

from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.trail_layer import TrailLayer


def _ctx(pose_2d, *, normalized, frame_idx):
    return LayerContext(
        frame_width=640,
        frame_height=480,
        pose_2d=pose_2d,
        normalized=normalized,
        frame_idx=frame_idx,
    )


def _valid_pose(x, y):
    p = np.zeros((17, 2), dtype=np.float32)
    p[H36Key.LFOOT] = [x, y]
    return p


def _nan_pose():
    return np.full((17, 2), np.nan, dtype=np.float32)


# =============================================================================
# BUG #1a — pixel mode: ValueError on int(nan)
# =============================================================================


def test_trail_nan_then_valid_pixel_mode_raises_valueerror():
    """RED: TrailLayer crashes on NaN-then-valid pose in pixel mode.

    Sequence: valid frame → all-NaN frame (detection gap/occlusion) → valid frame.
    The NaN pose is appended to _trail_2d unconditionally (no np.isnan guard, unlike
    VelocityLayer:117). On the next valid frame _draw_trail_2d runs int(nan) → ValueError.
    """
    layer = TrailLayer(length=20, smoothing=False)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Frame 0 — valid pose, builds trail
    layer.render(frame, _ctx(_valid_pose(100, 100), normalized=False, frame_idx=0))

    # Frame 1 — all-NaN pose (detection gap / occlusion). Bug: appended unconditionally.
    layer.render(frame, _ctx(_nan_pose(), normalized=False, frame_idx=1))

    # Frame 2 — valid pose again. RED: _draw_trail_2d converts trail → int(nan) →
    # ValueError. Asserting NO raise → fails (RED) against current buggy code.
    raised = False
    exc: BaseException | None = None
    try:
        layer.render(frame, _ctx(_valid_pose(200, 200), normalized=False, frame_idx=2))
    except (ValueError, TypeError) as e:
        raised = True
        exc = e
    assert not raised, (
        f"BUG #1a: TrailLayer crashes on NaN-then-valid pose (pixel mode): "
        f"{type(exc).__name__ if exc else '?'}: {exc}. "
        f"render() appends NaN pose unconditionally (no np.isnan guard, unlike "
        f"VelocityLayer:117) → int(nan) ValueError at _draw_trail_2d:139. "
        f"Detection gap (occlusion) → crash on next valid frame."
    )


# =============================================================================
# BUG #1b — normalized mode: spurious (0,0) trail vertex (visual corruption)
# =============================================================================


def test_trail_nan_then_valid_normalized_mode_inserts_spurious_origin_vertex():
    """RED: TrailLayer corrupts trail in normalized mode on NaN-then-valid pose.

    Normalized branch calls normalized_to_pixel(np.array([nan, nan]), ...) which maps
    NaN coords to (0,0) → a spurious trail vertex at the frame origin. The trail now
    draws a segment from origin to the real joint position: visual corruption.
    """
    layer = TrailLayer(length=20, smoothing=False)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Frame 0 — valid normalized pose at rink centre (~0.5, 0.5)
    p0 = np.zeros((17, 2), dtype=np.float32)
    p0[H36Key.LFOOT] = [0.5, 0.5]
    layer.render(frame, _ctx(p0, normalized=True, frame_idx=0))

    # Frame 1 — all-NaN pose. Bug: appended; normalized_to_pixel maps NaN → (0,0).
    layer.render(frame, _ctx(_nan_pose(), normalized=True, frame_idx=1))

    # Frame 2 — valid normalized pose elsewhere
    p2 = np.zeros((17, 2), dtype=np.float32)
    p2[H36Key.LFOOT] = [0.7, 0.7]
    layer.render(frame, _ctx(p2, normalized=True, frame_idx=2))

    # The NaN pose produced a spurious vertex at pixel (0,0). Inspect _trail_2d:
    # the stored tuple for the NaN frame is (nan, nan) which normalized_to_pixel
    # turns into ~(0,0). Assert no near-origin vertex was inserted.
    trail_px = []
    for pos in layer._trail_2d:
        from src.visualization.core.geometry import normalized_to_pixel

        pt = normalized_to_pixel(np.array(pos), 640, 480)
        trail_px.append((int(pt[0]), int(pt[1])))

    origin_vertex = next(
        ((px, py) for (px, py) in trail_px if px <= 5 and py <= 5),
        None,
    )
    assert origin_vertex is None, (
        f"BUG #1b: TrailLayer inserted spurious trail vertex at frame origin "
        f"{origin_vertex} after NaN-then-valid pose (normalized mode). "
        f"trail_px={trail_px}. normalized_to_pixel maps NaN→(0,0) → visual corruption."
    )
