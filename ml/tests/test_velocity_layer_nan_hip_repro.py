"""RED repro — `VelocityLayer._draw_velocity_2d` NaN hip poison + person-switch miss.

Two NaN-leak paths when a partial-NaN pose (one NaN hip keypoint) reaches the
layer (issue #973, tranche TC):

PATH 1 — person-switch miss (line 145-149):
    hip_now = context.pose_2d[H36Key.RHIP, :2]
    hip_prev = self._prev_pose_2d[H36Key.RHIP, :2]
    if np.linalg.norm(hip_now - hip_prev) > self.max_jump:   # NaN > 0.15 == False
        self._vel_history.clear()
        return
NaN RHIP → `hip_now = [NaN, NaN]` → `norm(NaN) = NaN` → `NaN > 0.15` False →
guard does NOT fire → history NOT cleared → a real person switch hidden behind
a NaN hip is silently missed → velocity history mixes two skaters.

PATH 2 — history poison (line 152-158):
    raw_vel = (context.pose_2d - self._prev_pose_2d) * self.scale   # NaN if pose NaN
    self._vel_history.append(raw_vel)                              # NO NaN-check
    velocities = np.mean(self._vel_history, axis=0)               # NaN poisons ALL joints
NaN raw_vel appended without guard → `np.mean(history)` returns NaN for ALL
joints for ~`smooth_window` (5) frames until the NaN frame is evicted. Line 173
`np.isnan(vel_px[joint_idx])` then skips every arrow for ~5 frames AFTER the
NaN frame. One occluded joint → 5 frames of missing arrows.

The line-141 guard `np.all(np.isnan(context.pose_2d))` only skips ALL-NaN
poses — a partial-NaN pose (one NaN hip, rest finite) passes through both
paths.

Contract: a NaN hip on a frame must NOT silently miss a person switch (fail
closed — clear history) and must NOT poison the smoothing history for the
whole window (NaN masked/skipped, not appended and propagated via np.mean).
"""

import inspect

import numpy as np
import pytest

from src.types import H36Key
from src.visualization.layers.base import LayerContext
from src.visualization.layers.velocity_layer import VelocityLayer


def _make_ctx(pose_2d: np.ndarray, *, normalized: bool = True) -> LayerContext:
    return LayerContext(
        frame_width=1920,
        frame_height=1080,
        frame_idx=0,
        pose_2d=pose_2d.astype(np.float32),
        pose_3d=None,
        normalized=normalized,
    )


def _finite_pose() -> np.ndarray:
    pose = np.zeros((17, 2), dtype=np.float32)
    # Spread joints so they aren't all at the origin.
    for i in range(17):
        pose[i] = (0.1 + 0.01 * i, 0.5 + 0.01 * i)
    return pose


def _nan_hip_pose() -> np.ndarray:
    pose = _finite_pose()
    pose[H36Key.RHIP] = np.nan
    return pose


# -- PATH 2: history poison ---------------------------------------------------


def test_nan_hip_pose_does_not_poison_velocity_history():
    """A NaN hip frame must not append NaN to `_vel_history`.

    After a finite frame then a NaN-hip frame, every entry in
    `_vel_history` must be finite (NaN frame skipped/held). The smoothed
    velocity (`np.mean(history, axis=0)`) must be finite for all joints.
    """
    layer = VelocityLayer(scale=5.0, smooth_window=5)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # Frame 0: finite pose — seeds _prev_pose_2d.
    layer.render(frame, _make_ctx(_finite_pose()))

    # Frame 1: finite pose — appends one finite velocity to history.
    p1 = _finite_pose()
    p1[:, 0] += 0.01  # small motion
    layer.render(frame, _make_ctx(p1))

    # Frame 2: NaN hip pose — must NOT append NaN to history.
    layer.render(frame, _make_ctx(_nan_hip_pose()))

    for entry in layer._vel_history:
        assert np.all(np.isfinite(entry)), f"NaN leaked into velocity history: {entry}"


def test_nan_hip_frame_velocity_stays_finite_for_other_joints():
    """Smoothing output (np.mean over history) must be finite for finite joints
    immediately after a NaN-hip frame."""
    layer = VelocityLayer(scale=5.0, smooth_window=3)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    layer.render(frame, _make_ctx(_finite_pose()))
    p1 = _finite_pose()
    p1[:, 0] += 0.02
    layer.render(frame, _make_ctx(p1))

    # NaN hip frame
    layer.render(frame, _make_ctx(_nan_hip_pose()))

    if layer._vel_history:
        velocities = np.mean(layer._vel_history, axis=0)
        # Every joint except the NaN hip must have finite smoothed velocity.
        for j in range(17):
            if j == H36Key.RHIP:
                continue
            assert np.all(np.isfinite(velocities[j])), (
                f"joint {j} velocity NaN-poisoned: {velocities[j]}"
            )


# -- PATH 1: person-switch miss -----------------------------------------------


def test_nan_hip_does_not_silently_miss_person_switch():
    """A NaN hip on a real person-switch frame must fail closed — clear history.

    The previous pose has hip at (0.5, 0.5). The current pose has a NaN hip but
    every OTHER joint is at a clearly different location (a true switch). The
    guard must treat a NaN hip comparison as a switch (fail closed), clearing
    `_vel_history`, NOT silently passing through.
    """
    layer = VelocityLayer(scale=5.0, smooth_window=5, max_jump=0.15)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # Seed prev pose with hip near (0.5, 0.5) and finite velocity history.
    prev = _finite_pose()
    prev[H36Key.RHIP] = (0.5, 0.5)
    layer.render(frame, _make_ctx(prev))
    p1 = prev.copy()
    p1[:, 0] += 0.01
    layer.render(frame, _make_ctx(p1))
    assert len(layer._vel_history) > 0

    # Current pose: NaN hip + all other joints far away (real switch).
    switched = _finite_pose()
    switched[H36Key.RHIP] = np.nan
    switched[:, 0] += 0.9  # huge displacement — a real switch
    layer.render(frame, _make_ctx(switched))

    assert len(layer._vel_history) == 0, (
        "NaN hip silently passed through person-switch guard; history not cleared"
    )


# -- regression ---------------------------------------------------------------


def test_all_finite_poses_regression():
    """All-finite frames: history grows, velocity finite, no spurious clear."""
    layer = VelocityLayer(scale=5.0, smooth_window=5)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    prev = _finite_pose()
    layer.render(frame, _make_ctx(prev))

    for k in range(1, 6):
        cur = _finite_pose()
        cur[:, 0] += 0.01 * k
        layer.render(frame, _make_ctx(cur))
        assert len(layer._vel_history) == min(k, 5)
        for entry in layer._vel_history:
            assert np.all(np.isfinite(entry))


# -- root-cause source lock ---------------------------------------------------


def test_velocity_layer_source_has_nan_hip_guard():
    """Root-cause lock: VelocityLayer._draw_velocity_2d source must contain an
    isfinite/NaN guard on the hip comparison or on raw_vel before history
    append. Fails on master (no guard)."""
    src = inspect.getsource(VelocityLayer._draw_velocity_2d)
    assert "np.isfinite" in src or "np.isnan" in src or "nan_to_num" in src, (
        "VelocityLayer._draw_velocity_2d has no NaN/isfinite guard on hip/velocity"
    )
