"""RED repro tests for two confirmed bugs in skeleton drawer.

Bug A: draw_skeleton silently discards caller's `confidences` param.
    drawer.py:78 unconditionally sets `confidences = None` before the
    `if pose.shape[1] == 3` branch. For a (17, 2) pose, any `confidences`
    array the caller passed is thrown away, so the per-joint confidence
    guards (drawer.py:95-99 / 116-117) never fire and low-confidence
    joints are always drawn. The public API documents `confidences` as a
    parameter; callers relying on it get silently wrong output (no
    skeleton thinning on low-confidence detections).

Bug B: draw_skeleton_batch swaps width/height and passes `normalized`
    (bool) as `confidence_threshold` (float).
    drawer.py:173-181 calls draw_skeleton positionally:
        draw_skeleton(frame.copy(), poses[i], width, height, normalized, **kwargs)
    but draw_skeleton's signature is
        (frame, pose, height, width, confidence_threshold, line_width,
         joint_radius, normalized, confidences)
    so `width` lands in the `height` slot, `height` lands in the `width`
    slot (dimensions swapped), and `normalized=True` lands in
    `confidence_threshold` (coerced to 1.0). A normalized pose (0.5, 0.5)
    on a 640x480 frame renders at the wrong pixel.

These tests MUST fail (RED) against the current buggy code. They are
repros, not fixes; production code is intentionally untouched.
"""

import numpy as np

from src.visualization.skeleton.drawer import draw_skeleton, draw_skeleton_batch

# ---------------------------------------------------------------------------
# Bug A: caller's `confidences` discarded (drawer.py:78)
# ---------------------------------------------------------------------------


def test_draw_skeleton_confidences_param_is_not_discarded():
    """Passing confidences below threshold must skip the joints.

    Setup: (17, 2) pose all at normalized center (0.5, 0.5), explicit
    `confidences` all 0.1 (below default threshold 0.5). Expected: every
    joint is below threshold and skipped, so the frame is unchanged.

    RED now: drawer.py:78 overwrites `confidences = None` unconditionally,
    discarding the caller's array. The confidence guards never fire, all
    joints are drawn, and the frame changes.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pose = np.full((17, 2), 0.5, dtype=np.float32)
    confs = np.full((17,), 0.1, dtype=np.float32)
    before = frame.copy()

    draw_skeleton(
        frame,
        pose,
        480,  # height
        640,  # width
        confidence_threshold=0.5,
        confidences=confs,
    )

    # Joints below threshold must be skipped -> frame unchanged.
    assert np.array_equal(before, frame), (
        "Expected frame unchanged (low-confidence joints skipped), "
        "but joints were drawn: caller's `confidences` discarded by "
        "drawer.py:78 unconditional `confidences = None`."
    )


# ---------------------------------------------------------------------------
# Bug B: draw_skeleton_batch swaps width/height + normalized->threshold
# ---------------------------------------------------------------------------


def test_draw_skeleton_batch_does_not_swap_width_height():
    """Batch wrapper must pass width/height to the correct slots.

    Setup: two 480x640 frames (H=480, W=640), poses (2, 17, 2) all at
    normalized center (0.5, 0.5). For a 640x480 frame the correct center
    pixel is (x=320, y=240) -> row=240, col=320 -> frame[240, 320].

    RED now: draw_skeleton_batch (drawer.py:173-181) passes args
    positionally as (frame, pose, width, height, normalized, **kwargs),
    so width=640 lands in the `height` slot and height=480 lands in the
    `width` slot. normalized_to_pixel then computes
    x = 0.5 * 480 = 240, y = 0.5 * 640 = 320 -> ink at frame[320, 240]
    (row=320, col=240) -- swapped.
    """
    frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(2)]
    poses = np.full((2, 17, 2), 0.5, dtype=np.float32)

    out = draw_skeleton_batch(
        frames,
        poses,
        width=640,
        height=480,
        normalized=True,
    )

    # Correct center for 640x480: row 240, col 320.
    assert out[0][240, 320].any(), (
        "Expected ink at correct center (row=240, col=320) for 640x480 "
        "frame, but that pixel is empty: draw_skeleton_batch swapped "
        "width/height (drawer.py:173-181)."
    )
    # The swapped center (row=320, col=240) must be empty.
    assert not out[0][320, 240].any(), (
        "Found ink at swapped center (row=320, col=240): "
        "draw_skeleton_batch passed width/height to the wrong slots."
    )
