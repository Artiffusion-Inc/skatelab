"""RED repro for issue #1160: extract_video_tracked (batch_extractor.py:208)
crashes with `ValueError: cannot convert float NaN to integer` when frame
dims (h, w) are NaN.

Root cause:
    scale = 1920 / max(h, w)
    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
`int(float('nan'))` is `ValueError` (Python stdlib contract, verified).
Python `max(NaN, finite)` returns the finite value, so the `if max(h,w) > 1920`
branch can be entered with `scale` finite but `w*scale` still NaN when w is
NaN. No `math.isfinite` / `np.isfinite` guard exists before the int()
conversions, so the stdlib `ValueError` escapes — undocumented, no field
name, no graceful degradation (a single bad frame halts the whole video).

The issue's "Fix (NOT applied)" calls for an `isfinite` guard at the top of
the resize block. This test file pins the contract: NaN frame dims must NOT
propagate to `int(NaN)`, the path must produce a clean signal (frame left
untouched so downstream detection still runs, OR a typed error naming the
corrupt field), and valid large frames must continue to resize normally.

Pure-Python: `cv2.VideoCapture` and `cv2.resize` mocked — no real video,
no GPU, no DB. The mock frame's `shape[:2]` returns NaN values to drive
the exact code path the issue names.
"""

from __future__ import annotations

import inspect
import math
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.pose_estimation.batch_extractor import BatchPoseExtractor
from src.types import VideoMeta


def _make_extractor(monkeypatch) -> BatchPoseExtractor:
    """Build a BatchPoseExtractor with mocked detector + moganet.
    Mock detector/moganet never run — overridden per-test.
    """

    class FakeMogaNet:
        def __init__(self, **kwargs):
            self.closed = False

        def infer_batch(self, crops, bboxes):
            raise AssertionError("overridden per-test")

        def close(self):
            self.closed = True

    class FakeDetector:
        def __init__(self, **kwargs):
            pass

        def detect_frame(self, frame):
            raise AssertionError("overridden per-test")

    monkeypatch.setattr(
        "src.pose_estimation.moganet_batch.MogaNetBatch",
        FakeMogaNet,
    )
    monkeypatch.setattr(
        "src.detection.person_detector.PersonDetector",
        FakeDetector,
    )
    return BatchPoseExtractor(batch_size=4, device="cpu")


def _patch_video(monkeypatch, frames, meta):
    class FakeCapture:
        def __init__(self, path):
            self._idx = 0

        def isOpened(self):
            return self._idx < len(frames)

        def read(self):
            if self._idx < len(frames):
                f = frames[self._idx]
                self._idx += 1
                return True, f
            return False, None

        def release(self):
            pass

    monkeypatch.setattr(
        "src.pose_estimation.batch_extractor.cv2.VideoCapture",
        FakeCapture,
    )
    monkeypatch.setattr(
        "src.pose_estimation.batch_extractor.get_video_meta",
        lambda path: meta,
    )


class _ShapeProxy:  # noqa: PLW1641  # test util, not hashed
    """Minimal stand-in for ndarray.shape that supports [:2] and [0]/1].

    Real ndarray shape is always int, so we cannot get NaN h/w into
    `frame.shape[:2]` via a real array. This proxy reproduces the exact
    indexing the code uses (`h, w = frame.shape[:2]`) and lets us inject
    NaN to drive the resize path the issue names.
    """

    __slots__ = ("_dims",)

    def __init__(self, dims: tuple[float, ...]) -> None:
        self._dims = dims

    def __getitem__(self, key):
        if isinstance(key, slice):
            return tuple(self._dims[key])
        return self._dims[key]

    def __len__(self) -> int:
        return len(self._dims)

    def __eq__(self, other) -> bool:
        if isinstance(other, _ShapeProxy):
            return self._dims == other._dims
        return NotImplemented

    def __repr__(self) -> str:
        return f"_ShapeProxy({self._dims!r})"


class _FakeFrame:
    """A frame-like object whose shape[:2] returns the given (h, w)."""

    __slots__ = ("shape",)

    def __init__(self, *, h: float, w: float, channels: int = 3) -> None:
        self.shape = _ShapeProxy((h, w, channels))


def _nan_shape_frame(*, h: float, w: float, channels: int = 3) -> _FakeFrame:
    """Frame with `shape[:2] == (h, w)`. Numpy arrays always have integer
    shape, so a real ndarray can never produce a NaN shape — this fake
    reproduces the exact code path the issue names
    (`h, w = frame.shape[:2]` then `int(w * scale)`) without requiring
    a real corrupt-video input."""
    return _FakeFrame(h=h, w=w, channels=channels)


# --------------------------------------------------------------------------- #
# Observable 1: locks the crash mechanism — int(NaN) is ValueError.
# --------------------------------------------------------------------------- #


def test_int_nan_raises_valueerror():
    """Locks the stdlib crash mechanism that propagates from
    `int(w * scale)` when w is NaN. Passes today (Python stdlib
    contract); exists to document the mechanism the fix must interrupt."""
    try:
        int(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError(
            "int(float('nan')) did not raise ValueError — Python stdlib "
            "contract changed? Re-check the assertion below."
        )


# --------------------------------------------------------------------------- #
# Observable 2: NaN w (with finite large h) — the exact issue scenario.
# NaN w alone crashes: max(NaN, h_finite) = h_finite → scale finite,
# but int(NaN * finite) = int(NaN) = ValueError. No guard.
# --------------------------------------------------------------------------- #


def test_nan_w_does_not_crash_with_valueerror(monkeypatch):
    """Frame with `w=NaN, h=3840` (large h forces the resize branch via
    `max(h, w) > 1920`). On master: `int(NaN * scale) = ValueError` —
    RED. After fix: NaN caught by `isfinite` guard at the top of the
    per-frame block, the corrupt frame is skipped, and the
    pre-allocated NaN pose stays. The function may then raise
    "No valid pose detected" at the end (all frames corrupt) — that
    is a legitimate, documented end-of-function signal, not the
    stdlib int(NaN) crash. The RED signal is the SPECIFIC stdlib
    "cannot convert float NaN to integer" ValueError from line 208.
    """
    frame = _nan_shape_frame(h=3840, w=float("nan"))
    meta = VideoMeta(
        path=Path("corrupt_nan_w.mp4"),
        width=1920,
        height=3840,
        fps=30.0,
        num_frames=1,
    )
    _patch_video(monkeypatch, [frame], meta)
    extractor = _make_extractor(monkeypatch)

    # Sanity: the int(NaN) crash mechanism is real (stdlib contract).
    # Locked here so the assertion below targets the right exception.
    def _stub_detect_and_crop(self, f):
        h, w = int(f.shape[0]), int(f.shape[1])
        return [np.zeros((h, w, 3), dtype=np.uint8)], [(0, 0, w, h)]

    monkeypatch.setattr(BatchPoseExtractor, "_detect_and_crop", _stub_detect_and_crop)
    extractor._moganet.infer_batch = MagicMock(
        side_effect=lambda crops, bboxes: (
            np.full((1, 17, 2), 0.5, dtype=np.float32),
            np.ones((1, 17), dtype=np.float32),
        )
    )

    # RED on master: int(NaN * scale) raises ValueError("cannot convert
    # float NaN to integer") at line 208. GREEN post-fix: the isfinite
    # guard short-circuits the frame, the function either completes
    # normally (if other valid frames exist) or raises the documented
    # "No valid pose detected" at the end. Either way, the stdlib
    # int(NaN) crash must NOT occur.
    try:
        extractor.extract_video_tracked("corrupt_nan_w.mp4")
    except ValueError as e:
        msg = str(e)
        if "cannot convert float NaN to integer" in msg:
            raise AssertionError(
                f"BUG: extract_video_tracked (batch_extractor.py:208) raised "
                f"undocumented stdlib int(NaN) ValueError ({msg!r}) on NaN w. "
                f"The fix must guard `int(w*scale)` / `int(h*scale)` with "
                f"`math.isfinite(h) and math.isfinite(w)` so the stdlib "
                f"int(NaN) is unreachable."
            ) from e
        # Any other ValueError (e.g. "No valid pose detected" at the
        # end when all frames are corrupt) is a legitimate post-fix
        # signal — the stdlib int(NaN) crash is what we test for, and
        # it did NOT occur.
        assert "No valid pose detected" in msg, (
            f"Unexpected ValueError on NaN w (not int(NaN), not 'No valid pose'): {e!r}"
        )


# --------------------------------------------------------------------------- #
# Observable 3 (root-cause lock): source must guard int(w*scale)/int(h*scale)
# with an isfinite (or equivalent) check. This test is RED on master (no
# guard exists in source) and GREEN after the fix. Covers BOTH the
# NaN-w crash (the actual stdlib int(NaN) ValueError) AND the NaN-h /
# both-NaN silent-skip case (`max(NaN, finite) = NaN`,
# `NaN > 1920 = False`, resize skipped, corrupt frame goes undetected —
# a separate silent bug the same guard must catch).
# --------------------------------------------------------------------------- #


def test_source_has_isfinite_guard_before_int_resize():
    """Root cause locked: extract_video_tracked computes
    `int(w * scale)` and `int(h * scale)` at line 208 with no
    `math.isfinite` / `np.isfinite` / `math.isnan` / `np.isnan` /
    `np.nan_to_num` guard. After the fix, an isfinite (or equivalent)
    check MUST appear in the per-frame block BEFORE the int() conversion
    at line 208 so stdlib int(NaN) is unreachable.

    Note: the test checks for a finite/Nan guard in the per-frame block
    (between `h, w = frame.shape[:2]` and `cv2.resize`), not anywhere
    in the function — `np.isnan` appears later in `valid_mask` and must
    not satisfy this assertion.
    """
    src = inspect.getsource(BatchPoseExtractor.extract_video_tracked)
    # Find the per-frame block: from `h, w = frame.shape[:2]` to the
    # actual `cv2.resize(` call (not a comment mention).
    capture_idx = src.find("h, w = frame.shape[:2]")
    # Use `cv2.resize(` (with paren) to skip comment occurrences.
    resize_idx = src.find("cv2.resize(")
    assert capture_idx != -1, "h, w capture not found in source"
    assert resize_idx != -1, "cv2.resize call not found in source"
    assert capture_idx < resize_idx, (
        f"capture_idx ({capture_idx}) must precede resize_idx ({resize_idx}) in source"
    )
    per_frame_block = src[capture_idx:resize_idx]
    has_guard = (
        "math.isfinite" in per_frame_block
        or "np.isfinite" in per_frame_block
        or "math.isnan" in per_frame_block
        or "np.isnan" in per_frame_block
        or "np.nan_to_num" in per_frame_block
    )
    assert has_guard, (
        "BUG: extract_video_tracked (batch_extractor.py:208) calls "
        "`int(w * scale)` / `int(h * scale)` with no isfinite guard in "
        "the per-frame block. `int(float('nan'))` raises ValueError, "
        "crashing the whole video on a single corrupt frame. Add a "
        "guard like `if not (math.isfinite(h) and math.isfinite(w)):` "
        "between `h, w = frame.shape[:2]` and the resize block — skip "
        "the frame (leave pre-allocated NaN pose) or raise a typed "
        "error naming the corrupt field."
    )


# --------------------------------------------------------------------------- #
# Regression: valid large frame still resizes (the fix must not regress).
# --------------------------------------------------------------------------- #


def test_valid_large_frame_still_resizes_normally(monkeypatch):
    """Regression: a 4K (3840×2160) frame MUST still hit the resize path
    and downscale to ≤1920 max-dim, identical to master behavior. The
    isfinite guard must let all-finite frames pass through unchanged.
    """
    # Real ndarray — shape is integer by construction.
    frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
    meta = VideoMeta(
        path=Path("valid_4k.mp4"),
        width=3840,
        height=2160,
        fps=30.0,
        num_frames=1,
    )
    _patch_video(monkeypatch, [frame], meta)
    extractor = _make_extractor(monkeypatch)

    # Capture the frame shape that reaches _detect_and_crop.
    captured_shapes: list[tuple[int, int]] = []

    def detect_and_crop(self, f):
        captured_shapes.append((int(f.shape[0]), int(f.shape[1])))
        # Return a real crop + bbox so the function gets a valid pose
        # and does NOT raise "No valid pose detected" at the end.
        h, w = int(f.shape[0]), int(f.shape[1])
        return [np.zeros((h, w, 3), dtype=np.uint8)], [(0, 0, w, h)]

    monkeypatch.setattr(BatchPoseExtractor, "_detect_and_crop", detect_and_crop)
    # MogaNet returns a center keypoint in the (already-resized) frame.
    extractor._moganet.infer_batch = MagicMock(
        side_effect=lambda crops, bboxes: (
            np.full((1, 17, 2), 0.5, dtype=np.float32),
            np.ones((1, 17), dtype=np.float32),
        )
    )

    # Must not raise. Valid finite dims → resize happens normally.
    extractor.extract_video_tracked("valid_4k.mp4")
    assert captured_shapes, "_detect_and_crop never called"
    h, w = captured_shapes[0]
    assert max(h, w) <= 1920, (
        f"BUG: resize did not run for 4K frame — got {h}x{w}. "
        f"The isfinite guard must NOT skip the resize for finite frames."
    )
    assert (h, w) == (1080, 1920), f"expected 1920x1080, got {h}x{w}"
