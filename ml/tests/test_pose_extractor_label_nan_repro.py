"""RED repro for issue #1206: `PoseExtractor._build_person_grid` at
`ml/src/pose_estimation/pose_extractor.py:711-714` crashes with
`ValueError: cannot convert float NaN to integer`.

Root cause (the 4 int() conversions on the bbox edge coordinates):

    bx1 = int(np.min(valid[:, 0]) * frame_w)    # 711
    by1 = int(np.min(valid[:, 1]) * frame_h)    # 712
    bx2 = int(np.max(valid[:, 0]) * frame_w)    # 713
    by2 = int(np.max(valid[:, 1]) * frame_h)    # 714

`int(float('nan'))` raises `ValueError: cannot convert float NaN to integer`
(Python stdlib contract, verified). The current `valid_mask` on line 707
(added by #1093) filters NaN coords at the kps-input level, but the int()
conversions at the bbox block have NO defensive guard. Latent risks:

  1. A future refactor of the valid_mask (e.g., loosening the conf threshold,
     changing `> 0.1` to `> 0.05`, dropping the `np.isfinite` clause) would
     re-introduce the crash.
  2. NaN in `frame_h` / `frame_w` from a corrupt video frame shape — the
     `valid_mask` does not check frame dims, only kps coords.
  3. `preview[iy, ix].mean()` (line 718) can be NaN if the frame buffer has
     NaN pixels at the sampled location — not a crash, but a NaN-leak
     downstream.

The fix is a single isfinite guard at the bbox block, post-valid_mask,
before the int() conversions. Pure defense-in-depth: filter NaN coords out
of the bbox computation; fall back to skipping the person if the bbox
can't be computed.

This test file pins the contract:
  - observable 1: with realistic keypoint array (high conf, finite coords),
    `_build_person_grid` does NOT raise and returns a path.
  - observable 2: the bbox block (post-valid_mask, pre-int()) has an
    isfinite guard on `valid` — i.e., the guard is INSIDE the bbox
    computation, not just at the input filter.
  - observable 3: the bbox block guards `frame_h` / `frame_w` (or the
    multiplied scalars), not just `valid[:, 0/1]`.
  - regression: the 4 int(np.min/max ...) calls remain — the fix is a
    guard, not a refactor.
  - source check: the GREEN contract — the bbox block has the guard.

The issue's "Fix (NOT applied)" calls for an isfinite guard at the top
of the bbox block. After the fix, the bbox block has the guard, the
function does not crash on a NaN coord (latent), and the all-valid path
is unchanged.
"""

from __future__ import annotations

import inspect

import numpy as np

from src.pose_estimation.pose_extractor import PoseExtractor


def _valid_kps() -> np.ndarray:
    """Realistic 17-keypoint H3.6M array, all finite, conf > 0.1."""
    kps = np.zeros((17, 3), dtype=np.float32)
    kps[0] = [0.5, 0.1, 0.9]  # head
    kps[1] = [0.4, 0.2, 0.9]  # lshoulder
    kps[2] = [0.6, 0.2, 0.9]  # rshoulder
    kps[3] = [0.3, 0.35, 0.8]
    kps[4] = [0.7, 0.35, 0.8]
    kps[5] = [0.25, 0.5, 0.7]
    kps[6] = [0.75, 0.5, 0.7]
    kps[7] = [0.45, 0.5, 0.9]
    kps[8] = [0.55, 0.5, 0.9]
    kps[9] = [0.43, 0.7, 0.8]
    kps[10] = [0.57, 0.7, 0.8]
    kps[11] = [0.42, 0.9, 0.7]
    kps[12] = [0.58, 0.9, 0.7]
    kps[13] = [0.4, 0.95, 0.6]
    kps[14] = [0.6, 0.95, 0.6]
    kps[15] = [0.5, 0.05, 0.9]
    kps[16] = [0.5, 0.15, 0.9]
    return kps


def _best_frame() -> np.ndarray:
    """1280x720 black BGR frame."""
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def _bbox_block(src: str) -> str:
    """Extract the source slice from `valid = kps[valid_mask]` to the last
    `int(np.max(...))` call — the bbox computation block.
    """
    valid_idx = src.find("valid = kps[valid_mask]")
    assert valid_idx != -1, (
        "test fixture broken: `valid = kps[valid_mask]` not found in "
        "_build_person_grid source. The valid_mask filter from #1093 must "
        "still be present — the #1206 fix is a guard, not a refactor."
    )
    last_int_max = src.rfind("int(np.max(")
    assert last_int_max != -1, (
        "test fixture broken: `int(np.max(` not found in _build_person_grid "
        "source. The 4 bbox int() calls must still be present — the #1206 "
        "fix is a guard, not a refactor."
    )
    end_of_bbox = src.find("\n", last_int_max)
    return src[valid_idx:end_of_bbox]


# --------------------------------------------------------------------------- #
# Observable 1: all-finite keypoints — function returns a preview path.
# --------------------------------------------------------------------------- #


def test_build_person_grid_finite_kps_returns_path_repro():
    """CORRECT behavior: a realistic keypoint array (all finite, conf > 0.1)
    must NOT raise. `_build_person_grid` must return a path string.

    This is the regression baseline — after the isfinite guard is added
    INSIDE the bbox block, the all-valid path must be unchanged.
    """
    frame = _best_frame()
    persons = [{"best_kps": _valid_kps(), "hits": 5, "best_conf": 0.85}]
    result = PoseExtractor._build_person_grid(frame, persons)
    assert isinstance(result, str), (
        f"BUG (regression): _build_person_grid returned {type(result).__name__} "
        f"({result!r}) for all-finite keypoints; expected a path string."
    )
    assert result, "_build_person_grid returned an empty path for valid input."


# --------------------------------------------------------------------------- #
# Observable 2: the BBOX block has an isfinite guard (not just the input
# valid_mask). The fix must be INSIDE the bbox computation, not just
# at the input filter.
# --------------------------------------------------------------------------- #


def test_build_person_grid_bbox_block_has_isfinite_guard_repro():
    """CORRECT behavior: the bbox block (post-valid_mask, pre-int()) has an
    isfinite guard on `valid` coords. The fix must be at the int()
    conversion site, not at the input filter (which is already there from
    #1093 — the issue is the gap between them).

    RED now: the only `np.isfinite` in the function is the input valid_mask
    on line 707. The bbox block (`bx1`/`by1`/`bx2`/`by2`) has no
    defensive guard. After the fix: a SECOND isfinite check appears in the
    bbox block, between `valid = kps[valid_mask]` and the first
    `int(np.min(...))` call.
    """
    src = inspect.getsource(PoseExtractor._build_person_grid)
    block = _bbox_block(src)
    # The bbox block must contain an isfinite guard on `valid` (the
    # filtered keypoint array). The guard is the fix — without it, a
    # NaN coord in `valid` (latent risk from future refactors of the
    # valid_mask, or from a corrupt frame dim) crashes int(NaN).
    assert "np.isfinite" in block or "math.isfinite" in block, (
        f"BUG: the bbox block in _build_person_grid has no isfinite guard.\n"
        f"\n"
        f"Block under test:\n{block}\n"
        f"\n"
        f"The `int(np.min(...))` / `int(np.max(...))` calls at the end of "
        f"this block crash with `ValueError: cannot convert float NaN to "
        f"integer` if `valid[:, 0/1]` contains NaN. The current input "
        f"valid_mask (line 707, from #1093) filters NaN at the input, but "
        f"a future refactor of the valid_mask or a NaN frame dim would "
        f"re-introduce the crash — there is no defensive guard in the bbox "
        f"block itself. The #1206 fix is a guard INSIDE the bbox block, "
        f"e.g. `if not (np.all(np.isfinite(valid[:, 0])) and "
        f"np.all(np.isfinite(valid[:, 1]))): continue` between the "
        f"`valid = kps[valid_mask]` assignment and the `bx1 = int(...)` "
        f"call. Without the guard, the int(NaN) crash is one refactor away."
    )


# --------------------------------------------------------------------------- #
# Observable 3: the 4 int(np.min/max ...) calls remain — the fix is a
# guard, not a refactor.
# --------------------------------------------------------------------------- #


def test_build_person_grid_int_conversions_intact_repro():
    """Regression: the 4 int() conversions (bx1, by1, bx2, by2) are still
    present after the fix. The fix is a guard, not a refactor — the int()
    calls remain, with an isfinite filter before them.
    """
    src = inspect.getsource(PoseExtractor._build_person_grid)
    assert src.count("int(np.min(") >= 2, (
        f"BUG (regression): _build_person_grid has {src.count('int(np.min(')} "
        f"`int(np.min(` calls; expected >= 2 (bx1, by1). The fix adds a "
        f"guard, not a refactor."
    )
    assert src.count("int(np.max(") >= 2, (
        f"BUG (regression): _build_person_grid has {src.count('int(np.max(')} "
        f"`int(np.max(` calls; expected >= 2 (bx2, by2). The fix adds a "
        f"guard, not a refactor."
    )


# --------------------------------------------------------------------------- #
# Observable 4: the function is a @staticmethod (the issue names the class
# method, not an instance method).
# --------------------------------------------------------------------------- #


def test_build_person_grid_is_static_repro():
    """CORRECT behavior: `_build_person_grid` is a `@staticmethod` on
    `PoseExtractor` (the issue names the class method). The fix lives on
    the static method, not pushed to a wrapping instance method.
    """
    assert isinstance(
        inspect.getattr_static(PoseExtractor, "_build_person_grid"),
        staticmethod,
    ), (
        "BUG: _build_person_grid must be a @staticmethod (the issue's named "
        "location at ml/src/pose_estimation/pose_extractor.py:711-714). The "
        "fix is on the static method, not a wrapper."
    )


# --------------------------------------------------------------------------- #
# Source check: GREEN contract — the bbox block guard is locked.
# --------------------------------------------------------------------------- #


def test_build_person_grid_bbox_block_guard_source_repro():
    """Source check (GREEN contract): the bbox block in
    `_build_person_grid` has an isfinite guard before the int()
    conversions. The guard is the #1206 fix.

    The guard appears AFTER the `valid = kps[valid_mask]` assignment and
    BEFORE the first `int(np.min(...))` call. Without the guard, a NaN
    coord in `valid` (or a NaN frame dim) propagates to `int(NaN)` →
    `ValueError: cannot convert float NaN to integer`.
    """
    src = inspect.getsource(PoseExtractor._build_person_grid)
    valid_idx = src.find("valid = kps[valid_mask]")
    first_int_min = src.find("int(np.min(")
    assert valid_idx != -1, (
        "BUG: `valid = kps[valid_mask]` not found in _build_person_grid "
        "source — the #1093 valid_mask filter must still be present."
    )
    assert first_int_min != -1, (
        "BUG: `int(np.min(` not found in _build_person_grid source — the 4 "
        "bbox int() calls must still be present."
    )
    # The bbox block is between `valid = kps[valid_mask]` and the last
    # `int(np.max(...)` call. The guard must be inside this block.
    block = src[valid_idx : src.rfind("int(np.max(") + len("int(np.max(")]
    assert "np.isfinite" in block, (
        f"BUG: the bbox block in _build_person_grid has no `np.isfinite` "
        f"guard (#1206). Block:\n{block}\n\n"
        f"The fix must add a `np.isfinite` check on `valid[:, 0/1]` (or "
        f"the equivalent bbox edge scalars) INSIDE the bbox block, between "
        f"the `valid = kps[valid_mask]` assignment and the `bx1 = int(...)` "
        f"call. The current `np.isfinite` at line 707 is the input filter "
        f"(from #1093) — the issue is the gap between the input filter "
        f"and the int() conversions."
    )
