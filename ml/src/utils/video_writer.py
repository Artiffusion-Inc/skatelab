"""PyAV-based H.264 video writer.

Replaces cv2.VideoWriter (mp4v) and ffmpeg subprocess calls with a single
consistent interface that produces browser-compatible H.264 / yuv420p output.

When ``codec="auto"`` (default), tries NVENC (``h264_nvenc``) first and
falls back to libx264.  NVENC options use constqp mode with qp=28 for speed;
libx264 uses the caller-supplied ``preset`` and ``crf`` parameters.
"""

from __future__ import annotations

import logging
from fractions import Fraction
from typing import TYPE_CHECKING

import av

if TYPE_CHECKING:
    from pathlib import Path

    import numpy as np

logger = logging.getLogger(__name__)


def _probe_nvenc() -> bool:
    """Return True if h264_nvenc codec is available."""
    try:
        c = av.open("/dev/null", "w")  # noqa: SIM115
        s = c.add_stream("h264_nvenc")
        s.width = 64  # type: ignore[reportAttributeAccessIssue]
        s.height = 64  # type: ignore[reportAttributeAccessIssue]
        s.pix_fmt = "yuv420p"  # type: ignore[reportAttributeAccessIssue]
        del s, c  # release resources
        return True
    except Exception:
        return False


class H264Writer:
    """Write BGR frames to an H.264 mp4 file via PyAV."""

    def __init__(
        self,
        path: str | Path,
        width: int,
        height: int,
        fps: float,
        *,
        codec: str = "auto",
        preset: str = "fast",
        crf: int = 23,
    ) -> None:
        self._container = av.open(str(path), "w")
        rate = Fraction(fps).limit_denominator(1000)

        resolved_codec = codec
        if resolved_codec == "auto":
            resolved_codec = "h264_nvenc" if _probe_nvenc() else "libx264"
            logger.info("Video codec: %s", resolved_codec)

        self._stream = self._container.add_stream(resolved_codec, rate=rate)
        self._stream.width = width  # type: ignore[reportAttributeAccessIssue]
        self._stream.height = height  # type: ignore[reportAttributeAccessIssue]
        self._stream.pix_fmt = "yuv420p"  # type: ignore[reportAttributeAccessIssue]

        if resolved_codec == "h264_nvenc":
            self._stream.options = {"preset": "p4", "rc": "constqp", "qp": "28"}  # type: ignore[reportAttributeAccessIssue]
        else:
            self._stream.options = {"preset": preset, "crf": str(crf)}  # type: ignore[reportAttributeAccessIssue]

    def write(self, frame: np.ndarray) -> None:
        """Write a BGR frame (numpy array)."""
        av_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")  # type: ignore[arg-type]
        for packet in self._stream.encode(av_frame):  # type: ignore[attr-defined]
            self._container.mux(packet)

    def close(self) -> None:
        """Flush remaining packets and close the file."""
        for packet in self._stream.encode():  # type: ignore[attr-defined]
            self._container.mux(packet)
        self._container.close()

    def __enter__(self) -> H264Writer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
