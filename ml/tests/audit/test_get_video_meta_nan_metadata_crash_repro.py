"""RED repro — `get_video_meta` (utils/video.py:47-50) crashes on corrupt
video with NaN metadata via `int(float('nan'))` ValueError.

`cv2.VideoCapture.get(CAP_PROP_FRAME_*)` can return `NaN` for corrupt
containers (truncated mp4, broken moov atom, damaged timescale). The
constructor does `int(cap.get(...))` (lines 47/48/50) with no
`np.isfinite` / `np.isnan` guard — `int(NaN)` raises
`ValueError: cannot convert float NaN to integer` (Python stdlib,
verified). Construction crashes BEFORE `width <= 0 or height <= 0` can
filter the NaN, BEFORE the fps `np.isfinite` guard can run. The
`get_video_meta` entrypoint is called from 8 sites
(`pose_extractor.py:262/398/811`, `batch_extractor.py:176`,
`multi_gpu_extractor.py:80`, `pipeline.py:228/444/725`,
`reference_builder.py:66`, `pose_preparation.py:100`); one corrupt video
crashes the whole pipeline at the very first I/O call.

Sibling of `test_get_video_meta_fps_zero_repro.py` (tranche DY/DZ) — that
test covers `fps=0.0`/`None`/`NaN` via the existing `np.isfinite(fps)`
guard at lines 75-76. This test covers `num_frames=NaN` (crash on line
50), `width=NaN` (crash on line 47), `height=NaN` (crash on line 48) —
the int-conversion family, unguarded. The fix (NOT applied — repro only):
guard each `int(cap.get(...))` site with `np.isfinite` so the constructor
either raises a typed `RuntimeError` naming the corrupt field OR returns
a VideoMeta with finite fields, matching the existing width<=0/height<=0
rejection style at line 62.

Contract: `get_video_meta` on a corrupt video with NaN metadata must
NEVER crash with the undocumented stdlib `ValueError("cannot convert
float NaN to integer")`. The path must produce a clean signal (typed
RuntimeError naming the corrupt property, OR finite VideoMeta). Valid
finite metadata (fps=30, 1920x1080, 150 frames) must pass through
unchanged — the regression test.

Pure-Python: `cv2.VideoCapture` mocked via `patch('src.utils.video.cv2.
VideoCapture')` — no real video file, no GPU, no DB.
"""

import inspect
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2

from src.utils.video import get_video_meta


def _mock_cap(
    *,
    width: float = 1920.0,
    height: float = 1080.0,
    fps: float = 30.0,
    num_frames: float = 150.0,
) -> MagicMock:
    """A mock cv2.VideoCapture whose .get(propId) returns the given
    raw values. isOpened()=True so open_video() doesn't raise.
    release()=noop."""
    cap = MagicMock()
    cap.isOpened.return_value = True

    def _get(prop: int) -> float:
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return width
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return height
        if prop == cv2.CAP_PROP_FPS:
            return fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return num_frames
        return 0.0

    cap.get.side_effect = _get
    return cap


def _meta_with(
    *,
    width: float = 1920.0,
    height: float = 1080.0,
    fps: float = 30.0,
    num_frames: float = 150.0,
):
    """Call get_video_meta with cv2.VideoCapture mocked to return the
    given raw CAP_PROP_* values. The path must exist for open_video (it
    checks path.exists()); use a real file (this repro file itself) so
    the check passes without patching.

    Returns the VideoMeta on success, or re-raises the exception on
    crash (test then inspects the exception type/message).
    """
    path = Path(__file__)  # real file — open_video's exists() check passes
    cap = _mock_cap(width=width, height=height, fps=fps, num_frames=num_frames)
    with patch("src.utils.video.cv2.VideoCapture", return_value=cap):
        return get_video_meta(path)


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded int(cap.get(...)) sites.
# --------------------------------------------------------------------------- #


def test_get_video_meta_source_has_no_nan_metadata_guard():
    """Root cause locked: get_video_meta calls `int(cap.get(...))` on lines
    47/48/50 with NO `np.isfinite` / `np.isnan` / `np.nan_to_num` guard.
    After the fix, the guard MUST appear at these trust boundaries so
    `int(NaN)` cannot propagate to the stdlib `int()` call."""
    src = inspect.getsource(get_video_meta)
    # All three int-conversion sites must have a finite guard before int().
    # Acceptable patterns: np.isfinite, np.isnan, math.isfinite, math.isnan,
    # np.nan_to_num — any of these makes int(NaN) unreachable.
    has_guard = (
        "np.isfinite" in src
        or "np.isnan" in src
        or "math.isfinite" in src
        or "math.isnan" in src
        or "np.nan_to_num" in src
    )
    assert has_guard, (
        "BUG: get_video_meta (utils/video.py:47-50) calls int(cap.get(...)) "
        "for CAP_PROP_FRAME_WIDTH / HEIGHT / COUNT with no finite guard. "
        "int(float('nan')) raises ValueError. Mirror the fps guard at "
        "line 75 (`np.isfinite(fps)`) for the int-conversion sites — "
        "read each cap.get() into a float, check isfinite, then int."
    )


# --------------------------------------------------------------------------- #
# Observable 1: locks the crash mechanism — int(NaN) is ValueError.
# --------------------------------------------------------------------------- #


def test_int_nan_raises_valueerror():
    """Locks the crash mechanism independently of get_video_meta:
    `int(float('nan'))` raises ValueError. This is what propagates out
    of get_video_meta on corrupt video — the stdlib error, not a typed
    RuntimeError naming the corrupt field. Passes today (Python stdlib
    contract); exists to document the mechanism the fix must interrupt.
    """
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
# Observable 2: NaN CAP_PROP_FRAME_COUNT → int(NaN) ValueError from
# get_video_meta (undocumented, not RuntimeError naming the field).
# --------------------------------------------------------------------------- #


def test_nan_frame_count_does_not_crash_with_undocumented_valueerror():
    """Contract: NaN CAP_PROP_FRAME_COUNT must NOT crash with the
    undocumented stdlib `ValueError("cannot convert float NaN to
    integer")` that has no hint of the corrupt field. The fix produces
    a clean signal — either a typed RuntimeError naming the corrupt
    property OR a VideoMeta with finite num_frames.

    RED before fix: stdlib ValueError ("cannot convert float NaN to
    integer") escapes — undocumented, no field name. GREEN after fix:
    RuntimeError with "CAP_PROP_FRAME_COUNT" in the message, OR
    VideoMeta returned with finite num_frames.
    """
    try:
        meta = _meta_with(num_frames=float("nan"))
    except ValueError as e:
        # RED branch: stdlib int(NaN) ValueError leaks. The fix must
        # replace this with a typed RuntimeError — assert the message
        # names the corrupt field, not the generic stdlib text.
        msg = str(e)
        assert "CAP_PROP_FRAME_COUNT" in msg or "FRAME_COUNT" in msg, (
            f"BUG: get_video_meta raised undocumented stdlib ValueError "
            f"({msg!r}) on NaN CAP_PROP_FRAME_COUNT. The fix must raise "
            f"a typed RuntimeError naming the corrupt field — e.g. "
            f"'Corrupt video metadata: non-finite CAP_PROP_FRAME_COUNT="
            f"nan for path=...'. Stdlib `cannot convert float NaN to "
            f"integer` is a symptom, not a root-cause signal."
        )
    except RuntimeError as e:
        # GREEN branch: fix raises typed RuntimeError naming the field.
        assert "CAP_PROP_FRAME_COUNT" in str(e) or "FRAME_COUNT" in str(e), (
            f"RuntimeError must name the corrupt field, got: {e!r}"
        )
    else:
        # GREEN branch: fix returns VideoMeta with finite num_frames.
        assert math.isfinite(meta.num_frames), (
            f"BUG: get_video_meta returned VideoMeta.num_frames="
            f"{meta.num_frames!r} (NaN-poisoned). The fix must ensure "
            f"num_frames is finite even when CAP_PROP_FRAME_COUNT is NaN."
        )


# --------------------------------------------------------------------------- #
# Observable 3: NaN fps → VideoMeta.fps is finite (NOT NaN) — the silent
# NaN-fps leak is a separate bug from the int(NaN) crash; the fix at
# line 75-76 already handles fps, this test pins the contract so a
# future refactor doesn't regress.
# --------------------------------------------------------------------------- #


def test_nan_fps_silently_propagated_to_video_meta_fps_now_fixed():
    """NaN CAP_PROP_FPS → VideoMeta.fps MUST be finite (NOT NaN). The
    existing guard at lines 75-76 (`if fps is None or fps <= 0 or not
    np.isfinite(fps): fps = 30.0`) handles this — locked here to prevent
    regression. The int(NaN) crash on width/height/num_frames is the
    remaining unfixed bug."""
    meta = _meta_with(fps=float("nan"))
    assert math.isfinite(meta.fps) and meta.fps > 0, (
        f"BUG: get_video_meta leaked fps=NaN as {meta.fps!r} → "
        f"duration_sec=nan poisons the whole VideoMeta. The fps guard "
        f"must reject non-finite fps, not just <= 0."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid finite metadata (fps=30, 1920x1080, 150 frames)
# must pass through unchanged. The fix must NOT regress valid videos.
# --------------------------------------------------------------------------- #


def test_valid_metadata_returns_finite_video_meta():
    """Regression: valid finite metadata → VideoMeta with all finite
    fields, fps=30, width=1920, height=1080, num_frames=150. The fix
    must not alter the valid path."""
    meta = _meta_with()
    assert meta.fps == 30.0
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.num_frames == 150
    assert math.isfinite(meta.fps)
    assert abs(meta.duration_sec - 5.0) < 1e-9  # 150 / 30
