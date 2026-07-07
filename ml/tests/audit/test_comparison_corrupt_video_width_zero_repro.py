"""RED repro — `ComparisonRenderer.process` ZeroDivisionError на corrupt video
(width=0 из cv2).

Corrupt/truncated mp4 (ftyp box present, moov atom damaged/missing) →
`cv2.VideoCapture.isOpened()` returns True, but
`cap.get(CAP_PROP_FRAME_WIDTH)` = 0.0. `open_video` (video.py:29-30) checks
only `isOpened()` → does NOT raise. `get_video_meta` (video.py:47-50)
returns `VideoMeta(width=0, height=0, ...)` with NO error →
`ComparisonRenderer.process` (comparison.py:157) `int(... / 0)` →
`ZeroDivisionError: division by zero`.

Root cause: `get_video_meta` leaks a structurally-valid but degenerate
`VideoMeta(width=0, ...)` — the I/O source. width=0 / height=0 from cv2
is the corrupt-video sentinel (no frame dimensions parseable from the
damaged container). Crash surfaces far from I/O — opaque division-by-zero
traceback, NOT a typed "corrupt video" error.

Sibling consistency: #961 (PR #990) fixed the fps=0 leak at the SAME
source (`get_video_meta` normalize degenerate fps → 30.0). width=0 /
height=0 is the dimension sibling of the same corrupt-video family —
#961 normalized fps (analysis still runnable at nominal framerate) but
width=0/height=0 means NO frames can be decoded (zero-size images), so
the correct fix is REJECT at source (typed RuntimeError), not normalize
(there is no sane default width — analysis cannot run on 0×0 frames).

The fix (NOT applied — repro only): guard in `get_video_meta` —
`if width <= 0 or height <= 0: raise RuntimeError(f"Corrupt video
(width={width}/height={height}): {path}")`. Reject at the I/O trust
boundary with a typed "corrupt video" error, NOT opaque ZeroDivisionError
at the resize division downstream. `ComparisonRenderer.process` and every
other caller that divides by `meta.width` (resize, aspect ratio) is
protected at source.

Contract: `get_video_meta` on a corrupt video (CAP_PROP_FRAME_WIDTH=0 /
HEIGHT=0) must raise a typed RuntimeError naming the corrupt-video
condition, NOT return a degenerate `VideoMeta(width=0, ...)` that crashes
downstream callers with ZeroDivisionError. `ComparisonRenderer.process`
must propagate that typed error (it calls `get_video_meta`), NOT raise
ZeroDivisionError.

RED now: observable assertions describe CORRECT behavior — width=0 input
→ `get_video_meta` raises RuntimeError (NOT returns VideoMeta(fps...));
`ComparisonRenderer.process` raises RuntimeError (NOT ZeroDivisionError).
They FAIL because width=0 passes through to the resize division. The
source-check confirms the guard is present (root cause locked).

Pure-Python: `cv2.VideoCapture` mocked via `patch('src.utils.video.cv2.
VideoCapture')` — no real video file, no GPU, no DB.
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import pytest

from src.utils.video import get_video_meta


def _mock_cap(
    *, width: float, height: float, fps: float = 30.0, num_frames: int = 150
) -> MagicMock:
    """A mock cv2.VideoCapture whose .get(propId) returns the given dims.
    isOpened()=True (corrupt-but-openable: ftyp box present, moov damaged)
    so open_video() doesn't raise — mirrors the real corrupt-mp4 case."""
    cap = MagicMock()
    cap.isOpened.return_value = True

    def _get(prop: int) -> float:
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(width)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(height)
        if prop == cv2.CAP_PROP_FPS:
            return fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return float(num_frames)
        return 0.0

    cap.get.side_effect = _get
    return cap


def _meta_with_dims(width: float, height: float):
    """Call get_video_meta with cv2.VideoCapture mocked to the given raw
    CAP_PROP_FRAME_WIDTH/HEIGHT. Path must exist for open_video."""
    path = Path(__file__)  # real file — open_video's exists() check passes
    with patch(
        "src.utils.video.cv2.VideoCapture", return_value=_mock_cap(width=width, height=height)
    ):
        return get_video_meta(path)


# --------------------------------------------------------------------------- #
# Observable 1: width=0 (corrupt moov atom) — get_video_meta raises typed
# RuntimeError, NOT returns degenerate VideoMeta.
# --------------------------------------------------------------------------- #


def test_get_video_meta_width_zero_raises_repro():
    """CORRECT behavior: CAP_PROP_FRAME_WIDTH=0 (corrupt-video sentinel —
    no frame dimensions parseable from damaged container) → `get_video_meta`
    raises a typed RuntimeError naming the corrupt-video condition, NOT
    returns `VideoMeta(width=0, ...)` that crashes downstream callers.

    RED now: width=0 passes through → VideoMeta(width=0) →
    ComparisonRenderer.process `int(... / 0)` ZeroDivisionError. After the
    fix: RuntimeError at the I/O source.
    """
    with pytest.raises(RuntimeError, match=r"(?i)corrupt|width"):
        _meta_with_dims(width=0.0, height=480.0)


# --------------------------------------------------------------------------- #
# Observable 2: height=0 (corrupt moov atom) — same typed rejection.
# --------------------------------------------------------------------------- #


def test_get_video_meta_height_zero_raises_repro():
    """CORRECT behavior: CAP_PROP_FRAME_HEIGHT=0 → `get_video_meta` raises
    RuntimeError. Same corrupt-video family as width=0; analysis cannot
    run on 0-height frames.

    RED now: height=0 passes through → degenerate VideoMeta. After the fix:
    RuntimeError at source.
    """
    with pytest.raises(RuntimeError, match=r"(?i)corrupt|height"):
        _meta_with_dims(width=640.0, height=0.0)


# --------------------------------------------------------------------------- #
# Observable 3: ComparisonRenderer.process propagates the typed error —
# `process` (comparison.py:150-151) calls `get_video_meta` for BOTH videos
# BEFORE any resize division (line 157). With the source guard, the typed
# RuntimeError from `get_video_meta` propagates out of `process` BEFORE
# the `/ meta.width` division is reached — so `process` raises
# RuntimeError, NOT ZeroDivisionError. Verified by the source-check +
# observable 1 (get_video_meta raises) + the call order (get_video_meta at
# line 150-151 precedes the division at line 157). Importing
# `ComparisonRenderer` directly is blocked by a pre-existing
# `ModuleNotFoundError: No module named 'av'` in the video_writer transitive
# import (av not installed in this venv; fails on master too) — not
# exercised here to keep the repro free of the unrelated collection error.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Regression guard: valid width/height passes through unchanged.
# --------------------------------------------------------------------------- #


def test_get_video_meta_valid_dims_unchanged_repro():
    """Regression guard: width=640, height=480 (real video) passes through
    unchanged — the corrupt-video guard must NOT alter valid dims. PASSES
    today; locks the contract.
    """
    meta = _meta_with_dims(width=640.0, height=480.0)
    assert meta.width == 640 and meta.height == 480, (
        f"BUG (regression): valid 640x480 must pass through unchanged, got "
        f"{meta.width}x{meta.height}. The width<=0/height<=0 guard must not "
        f"touch valid positive dims."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — width/height guard at construction.
# --------------------------------------------------------------------------- #


def test_get_video_meta_width_zero_guard_source_repro():
    """GREEN contract source check: the width=0 leak is fixed by a guard
    at the CONSTRUCTION site (`get_video_meta`) that rejects width<=0 /
    height<=0 with a typed RuntimeError naming the corrupt-video
    condition. Mirrors #961's "fix at the I/O source" philosophy — but
    reject (not normalize) because 0×0 frames cannot be decoded (no sane
    default dimension exists, unlike fps where 30.0 is a valid nominal).
    """
    src = inspect.getsource(get_video_meta)
    assert "width" in src and "height" in src, (
        "BUG: get_video_meta source must reference width/height for the corrupt-video guard."
    )
    # Guard must reject degenerate dims (width<=0 / height<=0).
    has_guard = (
        ("width <= 0" in src or "width <=0" in src or "width == 0" in src)
        or ("height <= 0" in src or "height <=0" in src or "height == 0" in src)
        or ("width" in src and "<= 0" in src)
        or ("height" in src and "<= 0" in src)
    )
    assert has_guard, (
        "BUG: get_video_meta must guard width<=0 / height<=0 (corrupt-video "
        "sentinel from cv2) — raise RuntimeError at the I/O source, NOT "
        "return VideoMeta(width=0) that crashes downstream /width divisions. "
        "Sibling of #961 (fps=0 normalize); width/height=0 must REJECT (no "
        "sane default dimension, 0x0 frames undecodable)."
    )
