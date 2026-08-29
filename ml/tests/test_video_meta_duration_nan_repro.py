"""RED repro — VideoMeta.duration_sec silently coerces NaN/neg fps to 0.0.

BUG (#1066, HIGH — NaN fps produces 0-second video, indistinguishable from
a legitimate fps=0 broken-header video):

    ml/src/types.py:447-450  VideoMeta.duration_sec:
        `return self.num_frames / self.fps if self.fps > 0 else 0.0`
        ↑ NaN fps → `NaN > 0` is False → duration_sec = 0.0 (silent NaN→0)

Severity: HIGH. Canonical "video duration" accessor. NaN fps → 0-second
video in UI, recommender, DB, choreographer planner.

The fix proposed in the issue:

    if not (math.isfinite(self.fps) and self.fps > 0):
        raise ValueError(f"fps must be finite and > 0, got {self.fps}")
    return self.num_frames / self.fps

We mirror that contract: non-finite or non-positive fps → ValueError,
not a silent 0.0. Tests stay RED until the guard is added.
"""

import inspect
import math
from pathlib import Path

import pytest

from src.types import VideoMeta


def _make_meta(tmp_path: Path, fps: float, num_frames: int = 30) -> VideoMeta:
    return VideoMeta(
        path=tmp_path / "test.mp4",
        fps=fps,
        width=1920,
        height=1080,
        num_frames=num_frames,
    )


def test_duration_sec_nan_fps_raises_value_error(tmp_path: Path):
    """NaN fps must NOT silently coerce to 0.0 — distinguishable from fps=0.

    NaN fps currently slips past `self.fps > 0` (NaN > 0 is False), so
    duration_sec returns 0.0 — INDISTINGUISHABLE from a legitimate fps=0
    broken-header video. NaN is a corrupt-metadata signal and must raise.
    """
    meta = _make_meta(tmp_path, fps=float("nan"), num_frames=30)

    with pytest.raises(ValueError, match=r"fps"):
        _ = meta.duration_sec


def test_duration_sec_negative_fps_raises_value_error(tmp_path: Path):
    """Negative fps is a corrupt-metadata signal and must raise.

    Currently: `self.fps > 0` is False for fps=-1, so duration_sec=0.0
    silently. Bug.
    """
    meta = _make_meta(tmp_path, fps=-1.0, num_frames=30)

    with pytest.raises(ValueError, match=r"fps"):
        _ = meta.duration_sec


def test_duration_sec_nan_num_frames_raises_value_error(tmp_path: Path):
    """NaN num_frames (via finite fps) must NOT silently produce NaN.

    `int(float('nan'))` raises — Python's int() rejects NaN at construction.
    That rejection IS the value-error guard for num_frames. The test asserts
    either:
      - the constructor rejects NaN num_frames (ValueError), OR
      - if a future version accepts it, .duration_sec rejects it.

    Either way: NaN num_frames must not reach `num_frames / fps` silently.
    """
    # int(float('nan')) raises ValueError — that's the natural guard.
    with pytest.raises(ValueError):
        int(float("nan"))

    # If a future VideoMeta stops using strict int typing, the duration
    # property must still guard non-finite num_frames:
    meta = VideoMeta(
        path=tmp_path / "test.mp4",
        fps=30.0,
        width=1920,
        height=1080,
        num_frames=0,  # use 0; we'll mutate the field for the assertion
    )
    # Mutate to NaN to simulate the corrupt path (bypassing constructor).
    object.__setattr__(meta, "num_frames", float("nan"))

    with pytest.raises(ValueError, match=r"(num_frames|frames|fps)"):
        _ = meta.duration_sec


def test_duration_sec_negative_num_frames_raises_value_error(tmp_path: Path):
    """Negative num_frames is corrupt metadata and must raise.

    Currently: passes silently, returns a negative or sign-flipped value.
    """
    meta = VideoMeta(
        path=tmp_path / "test.mp4",
        fps=30.0,
        width=1920,
        height=1080,
        num_frames=-10,
    )

    with pytest.raises(ValueError, match=r"(num_frames|frames|fps)"):
        _ = meta.duration_sec


def test_duration_sec_valid_finite_regression(tmp_path: Path):
    """Valid finite fps regression guard: 30 frames @ 30fps = 1.0s.

    Sanity check that the fix doesn't break the happy path.
    """
    meta = _make_meta(tmp_path, fps=30.0, num_frames=30)

    assert meta.duration_sec == pytest.approx(1.0)


def test_duration_sec_source_uses_isfinite_guard():
    """Source-level guard: the property must call math.isfinite(self.fps).

    Read the source file of ml/src/types.py to confirm the fix is in place
    (and that no future refactor silently drops the guard). The test
    passes only when `math.isfinite` appears inside the `duration_sec`
    property block in ml/src/types.py.
    """
    import re
    from pathlib import Path

    from src import types as types_module

    src_path = Path(inspect.getfile(types_module))
    src = src_path.read_text()

    # Extract the duration_sec property body via regex. Looks for the
    # `def duration_sec` line and captures up to the next top-level
    # `def`/`class`/`@dataclass` or end of indent-4 block.
    pattern = re.compile(
        r"@property\s*\n\s*def\s+duration_sec\s*\([^)]*\)[^:]*:\s*\n"
        r"(?P<body>(?:[ \t]+.*\n|[ \t]*\n)*)",
        re.MULTILINE,
    )
    match = pattern.search(src)
    assert match is not None, (
        f"Could not locate VideoMeta.duration_sec property in {src_path}.\nSource:\n{src}"
    )
    duration_block = match.group("body")

    assert "math.isfinite" in duration_block, (
        f"BUG: VideoMeta.duration_sec source lacks `math.isfinite(self.fps)` "
        f"guard. NaN fps silently coerces to 0.0. The property must guard "
        f"against non-finite fps. Current duration_sec body:\n{duration_block}"
    )
