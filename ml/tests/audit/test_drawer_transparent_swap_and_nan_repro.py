"""RED repro — two confirmed bugs in skeleton drawer (siblings of #448/#449).

Bug C: draw_skeleton_transparent passes args positionally and swaps
    width/height, and coerces `normalized` (bool) into `confidence_threshold`.
    drawer.py:455 calls:
        draw_skeleton(overlay, pose, width, height, normalized, **kwargs)
    but draw_skeleton's signature is
        (frame, pose, height, width, confidence_threshold, line_width,
         joint_radius, normalized, confidences)
    so `width` lands in the `height` slot, `height` lands in the `width`
    slot (dimensions swapped), and `normalized=True` lands in
    `confidence_threshold` (coerced to 1.0 → every joint is below threshold →
    skeleton NOT drawn). This is the EXACT sibling of the #449
    draw_skeleton_batch swap that was already fixed — the transparent wrapper
    was missed.

Bug D: draw_skeleton misclassifies a NaN-containing pose as pixel coordinates.
    drawer.py:87 `if pose.max() <= 1.0:` — `np.array(...).max()` on an array
    containing NaN returns NaN, and `NaN <= 1.0` is False, so the code takes
    the "already in pixel coordinates" branch for a NORMALIZED pose that
    happens to contain a NaN keypoint (common: occluded joint after smoothing
    #462 restores NaN). The normalized coords are then treated as pixel
    coords and drawn at the wrong location.

These tests MUST fail (RED) against the current buggy code. Repros, not fixes.
"""

import numpy as np

from src.visualization.skeleton.drawer import draw_skeleton, draw_skeleton_transparent

# ---------------------------------------------------------------------------
# Bug C: draw_skeleton_transparent swaps width/height + coerces normalized
#        into confidence_threshold (sibling of #449, missed wrapper)
# ---------------------------------------------------------------------------


def test_draw_skeleton_transparent_does_not_swap_width_height():
    """A normalized pose (0.5, 0.5) on a 640x480 frame must render at the
    frame center (320, 240). With the width/height swap it renders at
    (240, 320) — wrong pixel. Assert the skeleton lands near the center.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pose = np.full((17, 2), 0.5, dtype=np.float32)  # normalized center

    out = draw_skeleton_transparent(frame, pose, width=640, height=480, normalized=True)
    # skeleton drawn → overlay non-zero somewhere
    drawn_mask = (out > 0).any(axis=2)
    assert drawn_mask.any(), "no skeleton drawn at all"

    _ys, xs = np.where(drawn_mask)
    # Correct: center at (320, 480//2=240). Swapped: would cluster near (240, 320).
    # Allow a generous band around the TRUE center; a swapped render falls outside.
    assert abs(xs.mean() - 320) < 60, (
        f"BUG: draw_skeleton_transparent swapped width/height — skeleton rendered "
        f"at x≈{xs.mean():.0f} (expected ≈320 for normalized 0.5 on width=640). "
        f"#449 fixed draw_skeleton_batch but missed this transparent wrapper "
        f"(drawer.py:455 passes width,height,normalized positionally into "
        f"height,width,confidence_threshold)."
    )


def test_draw_skeleton_transparent_draws_joints_not_suppressed_by_threshold():
    """`normalized=True` coerced into `confidence_threshold=1.0` would
    suppress ALL joints (no confidence reaches 1.0 for (17,2) pose →
    confidences=None → joints drawn). Actually with confidences=None joints
    ARE drawn (radius default). The real suppression shows for (17,3) poses:
    normalized=True→threshold=1.0 > any real confidence → skeleton suppressed.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # (17, 3) pose: x,y at center, confidence 0.9 (below coerced 1.0 threshold)
    pose = np.full((17, 3), 0.5, dtype=np.float32)
    pose[:, 2] = 0.9

    out = draw_skeleton_transparent(frame, pose, width=640, height=480, normalized=True)
    drawn_mask = (out > 0).any(axis=2)
    assert drawn_mask.any(), (
        "BUG: draw_skeleton_transparent coerces normalized=True into "
        "confidence_threshold=1.0 (drawer.py:455 positional swap), so every "
        "joint with confidence 0.9 < 1.0 is suppressed and NO skeleton is "
        "drawn. #449-sibling: the transparent wrapper was missed."
    )


# ---------------------------------------------------------------------------
# Bug D: NaN keypoint → pose.max()=NaN → normalized pose treated as pixels
# ---------------------------------------------------------------------------


def test_draw_skeleton_nan_keypoint_does_not_treat_normalized_as_pixels():
    """A normalized pose (all coords in [0,1]) with ONE NaN keypoint must
    still be treated as normalized and converted to pixels. drawer.py:87
    `if pose.max() <= 1.0:` — NaN.max()=NaN, NaN<=1.0 is False → takes the
    pixel branch → normalized coords used as pixel coords → skeleton drawn
    in the top-left corner (coords 0.25→0px) instead of spread across frame.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # normalized pose, all in [0,1], one joint NaN
    pose = np.full((17, 2), 0.5, dtype=np.float32)
    pose[5] = np.nan  # occluded joint
    # sanity: pose.max() on NaN array returns NaN (the trigger)
    assert np.isnan(pose.max()), "test fixture broken: pose.max() must be NaN"

    draw_skeleton(frame, pose, height=480, width=640)
    drawn_mask = (frame > 0).any(axis=2)
    assert drawn_mask.any(), "no skeleton drawn"
    ys, xs = np.where(drawn_mask)
    # Correct (normalized→pixel): x≈0.5*640=320, y≈0.5*480=240.
    # Buggy (treated as pixel): coords 0.5→0px → cluster near origin (0,0).
    assert abs(xs.mean() - 320) < 80 and abs(ys.mean() - 240) < 80, (
        f"BUG: NaN keypoint made pose.max()=NaN (drawer.py:87), so a normalized "
        f"pose was treated as pixel coords — skeleton drawn at x≈{xs.mean():.0f},"
        f"y≈{ys.mean():.0f} (expected ≈320,240). A single occluded joint flips the "
        f"normalized/pixel decision for the whole skeleton."
    )
