"""RED repro — H264Writer unguarded fps (0/NaN/inf/-5) corrupts MP4 or leaks container.

BUG #1048 (MEDIUM — unguarded fps at H264Writer.__init__):
    ml/src/utils/video_writer.py:54-71 H264Writer.__init__:
        `self._container = av.open(str(path), "w")`  # container opened FIRST
        `rate = Fraction(fps).limit_denominator(1000)`  # NO fps validation
        `self._stream = self._container.add_stream(..., rate=rate)`

    Three failure modes for degenerate fps (cv2.CAP_PROP_FPS can return 0 / NaN / -1
    on corrupt / unknown-fps MP4 / webm / mkv):

    1. fps=0   → Fraction(0, 1) silently set → unplayable 0-time-base MP4 (no error)
    2. fps=NaN → ValueError AFTER container is opened → resource leak
    3. fps=inf → OverflowError AFTER container is opened → resource leak
    4. fps=-5  → Fraction(-5, 1) silently set → invalid negative rate

    Mirror #1041 get_video_meta family: finite + positive validation pattern
    (issues #982 / #961 applied to other fps/load sites).

The fix contract: H264Writer.__init__ must raise ValueError BEFORE av.open when
fps is not finite and strictly positive. Valid fps=30 must continue to work
(regression). The source must contain an `isfinite` (or equivalent) AND
greater-than-zero guard.

These tests assert the post-fix contract. They FAIL on master (RED) and PASS
after the fix (GREEN).
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import numpy as np

from src.utils.video_writer import H264Writer

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _try_init(tmp_path: Path, fps: float) -> tuple[bool, BaseException | None]:
    """Attempt H264Writer init with degenerate fps. Return (raised?, exc)."""
    out = tmp_path / "out.mp4"
    raised = False
    exc: BaseException | None = None
    try:
        H264Writer(str(out), width=64, height=64, fps=fps)
    except BaseException as e:  # noqa: BLE001 — we want any exception type
        raised = True
        exc = e
    return raised, exc


# ---------------------------------------------------------------------------
# RED tests
# ---------------------------------------------------------------------------


def test_h264_writer_zero_fps_raises_valueerror(tmp_path: Path) -> None:
    """fps=0 must raise ValueError, NOT silently produce a 0-time-base MP4."""
    raised, exc = _try_init(tmp_path, fps=0.0)
    assert raised, (
        "BUG #1048: H264Writer(fps=0) did not raise. "
        "Fraction(0, 1) silently set as rate → unplayable 0-time-base MP4."
    )
    assert isinstance(exc, ValueError), (
        f"BUG #1048: H264Writer(fps=0) raised {type(exc).__name__}, "
        f"expected ValueError. exc={exc!r}"
    )


def test_h264_writer_nan_fps_raises_valueerror(tmp_path: Path) -> None:
    """fps=NaN must raise ValueError, NOT a ValueError from Fraction AFTER av.open."""
    raised, exc = _try_init(tmp_path, fps=float("nan"))
    assert raised, "BUG #1048: H264Writer(fps=NaN) did not raise."
    assert isinstance(exc, ValueError), (
        f"BUG #1048: H264Writer(fps=NaN) raised {type(exc).__name__}, "
        f"expected ValueError. exc={exc!r}"
    )
    # Ensure message names fps (helps the user diagnose corrupt-video input)
    assert "fps" in str(exc).lower(), (
        f"BUG #1048: ValueError message must mention 'fps', got: {exc!r}"
    )


def test_h264_writer_inf_fps_raises_valueerror(tmp_path: Path) -> None:
    """fps=inf must raise ValueError, NOT OverflowError AFTER av.open."""
    raised, exc = _try_init(tmp_path, fps=float("inf"))
    assert raised, "BUG #1048: H264Writer(fps=inf) did not raise."
    assert isinstance(exc, ValueError), (
        f"BUG #1048: H264Writer(fps=inf) raised {type(exc).__name__}, "
        f"expected ValueError. exc={exc!r}"
    )


def test_h264_writer_negative_fps_raises_valueerror(tmp_path: Path) -> None:
    """fps=-5 must raise ValueError (negative rate is invalid)."""
    raised, exc = _try_init(tmp_path, fps=-5.0)
    assert raised, "BUG #1048: H264Writer(fps=-5) did not raise."
    assert isinstance(exc, ValueError), (
        f"BUG #1048: H264Writer(fps=-5) raised {type(exc).__name__}, "
        f"expected ValueError. exc={exc!r}"
    )


def test_h264_writer_valid_fps_unchanged(tmp_path: Path) -> None:
    """Regression: fps=30 must NOT raise — H264Writer still works normally."""
    out = tmp_path / "ok.mp4"
    writer = H264Writer(str(out), width=64, height=64, fps=30.0)
    try:
        # round-trip a black frame so the stream gets exercised
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    finally:
        writer.close()
    assert out.exists() and out.stat().st_size > 0, (
        f"regression: H264Writer(fps=30) produced no output at {out}"
    )


def test_h264_writer_source_has_isfinite_and_positive_guard() -> None:
    """Source check: H264Writer.__init__ must guard fps with isfinite + > 0.

    Mirror #961 / #982 style — finite and positive validation before av.open.
    """
    src = inspect.getsource(H264Writer.__init__)
    # Must have BOTH a finiteness check (math.isfinite / np.isfinite / Fraction-aware)
    # AND a strict-positive comparison in the body of __init__.
    has_isfinite = ("math.isfinite" in src) or ("np.isfinite" in src) or ("isfinite" in src)
    # `fps > 0` as a real guard — not the comment "fps can return 0"
    has_positive = "fps > 0" in src
    assert has_isfinite, (
        f"BUG #1048: H264Writer.__init__ has no `isfinite` guard for fps. Source snippet:\n{src}"
    )
    assert has_positive, (
        f"BUG #1048: H264Writer.__init__ has no `fps > 0` (positive) guard. Source snippet:\n{src}"
    )
    # And the guard must appear BEFORE the `av.open(str(path), "w")` call —
    # otherwise the container is still leaked on degenerate fps. Match the
    # actual call (with `str(path)` arg) so we don't trip on a comment
    # reference to `av.open`.
    guard_pos = src.find("isfinite")
    open_pos = src.find('av.open(str(path), "w")')
    assert guard_pos != -1 and open_pos != -1 and guard_pos < open_pos, (
        "BUG #1048: fps guard must run BEFORE av.open, otherwise the container "
        f"is still leaked on degenerate fps. guard_pos={guard_pos} open_pos={open_pos} "
        f"Source:\n{src}"
    )
