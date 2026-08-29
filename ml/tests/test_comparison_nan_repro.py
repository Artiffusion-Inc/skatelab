"""RED repro — `ComparisonRenderer.process` int(NaN) crash on NaN resize meta.

`ComparisonRenderer.process` (ml/src/visualization/comparison.py:157-159)
crashes with uncaught `ValueError: cannot convert float NaN to integer` when
the resize calculation is fed NaN values:

  a_h = int(athlete_meta.height * target_w / athlete_meta.width)
  r_h = int(reference_meta.height * target_w / reference_meta.width)

`get_video_meta` already guards non-finite width/height at the I/O source
(#1041) and `width <= 0` / `height <= 0` (#982) — so the only unguarded
NaN source remaining is `self.config.resize_width` (corrupt YAML, NaN env
var, hand-crafted test fixture). `int(NaN * x / y)` = `int(NaN)` raises
`ValueError: cannot convert float NaN to integer` from the stdlib with no
hint that the cause is corrupt config.

Sibling of `test_comparison_corrupt_video_width_zero_repro.py` (width=0 →
ZeroDivisionError). Different exception class (`ValueError` vs
`ZeroDivisionError`), same root cause (no guard on the resize meta).

The fix (NOT applied — repro only): guard `target_w` (and meta) with
`math.isfinite` at the resize site, raise a typed `ValueError` naming the
corrupt-resize-meta condition. Or guard at the I/O source for `resize_width`
in the YAML/config loader — but the resize site is the natural trust
boundary (process() is the public entry point for the comparison CLI
scripts/compare_videos.py and the comparison API).

Contract: NaN `meta.width` / `meta.height` / `target_w` → `process` raises
a typed `ValueError` naming the corrupt-resize-meta condition, NOT a raw
`int(NaN)` ValueError from the stdlib. The `isnan`/`isinf`/`isfinite` guard
must be present in the source (root cause locked).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add ml to path for imports (matches existing test_comparison.py convention)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.visualization.comparison import (
    ComparisonConfig,
    ComparisonMode,
    ComparisonRenderer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_video_meta():
    """Return a mock VideoMeta-like object with valid 640x480, 30fps."""
    meta = MagicMock()
    meta.width = 640
    meta.height = 480
    meta.fps = 30.0
    meta.num_frames = 10
    return meta


def _renderer_with_resize_width(resize_width: float) -> ComparisonRenderer:
    """Build a ComparisonRenderer with the given resize_width in the config."""
    cfg = ComparisonConfig(
        mode=ComparisonMode.SIDE_BY_SIDE,
        resize_width=resize_width,  # type: ignore[arg-type]
        max_frames=3,
    )
    return ComparisonRenderer(config=cfg)


def _video_paths(tmp_path: Path):
    """Create dummy video paths for process() args."""
    athlete = tmp_path / "athlete.mp4"
    athlete.write_bytes(b"dummy")
    reference = tmp_path / "reference.mp4"
    reference.write_bytes(b"dummy")
    output = tmp_path / "out.mp4"
    return athlete, reference, output


# ---------------------------------------------------------------------------
# Observable 1: NaN resize_width → process() raises typed ValueError, NOT
# raw int(NaN) stdlib ValueError.
# ---------------------------------------------------------------------------


@patch("src.visualization.comparison.draw_skeleton")
@patch("src.visualization.comparison.get_skating_optimized_config")
@patch("src.visualization.comparison.PoseSmoother")
@patch("src.visualization.comparison.PoseExtractor")
@patch("src.visualization.comparison.H264Writer")
@patch("src.visualization.comparison.get_video_meta")
@patch("src.visualization.comparison.cv2.VideoCapture")
def test_process_nan_resize_width_raises_typed_value_error(
    mock_cap_cls,
    mock_get_meta,
    mock_writer_cls,
    mock_extractor_cls,
    mock_smoother_cls,
    mock_get_config,
    mock_draw,
    tmp_path,
    mock_video_meta,
):
    """CORRECT behavior: NaN `resize_width` (corrupt YAML / hand-crafted
    fixture) → `process` raises a typed `ValueError` naming the
    corrupt-resize-meta condition, NOT the opaque stdlib
    `ValueError: cannot convert float NaN to integer` from `int(NaN)`.

    The stdlib ValueError is the symptom; the typed error names the cause
    (corrupt resize meta / NaN config) so the user has signal.

    RED now: NaN `resize_width` is multiplied into the resize calc →
    `int(NaN * 480 / 640)` → stdlib `ValueError: cannot convert float NaN
    to integer`. After the fix: typed ValueError at the resize guard.
    """
    mock_get_meta.return_value = mock_video_meta
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.set.return_value = True
    cap.release.return_value = None
    cap.read.return_value = (False, None)
    mock_cap_cls.return_value = cap
    mock_writer_cls.return_value = MagicMock()
    extractor = MagicMock()
    tracked = MagicMock()
    tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
    extractor.extract_video_tracked.return_value = tracked
    mock_extractor_cls.return_value = extractor

    renderer = _renderer_with_resize_width(float("nan"))
    athlete, reference, output = _video_paths(tmp_path)

    # Match on words NOT in the stdlib "cannot convert float NaN to integer"
    # message, so we only match the typed "corrupt resize meta" error.
    with pytest.raises(ValueError, match=r"(?i)corrupt|finite|resize|width|height"):
        renderer.process(athlete, reference, output)


# ---------------------------------------------------------------------------
# Observable 2: NaN athlete_meta.height → process() raises typed ValueError.
# ---------------------------------------------------------------------------


@patch("src.visualization.comparison.draw_skeleton")
@patch("src.visualization.comparison.get_skating_optimized_config")
@patch("src.visualization.comparison.PoseSmoother")
@patch("src.visualization.comparison.PoseExtractor")
@patch("src.visualization.comparison.H264Writer")
@patch("src.visualization.comparison.get_video_meta")
@patch("src.visualization.comparison.cv2.VideoCapture")
def test_process_nan_athlete_height_raises_typed_value_error(
    mock_cap_cls,
    mock_get_meta,
    mock_writer_cls,
    mock_extractor_cls,
    mock_smoother_cls,
    mock_get_config,
    mock_draw,
    tmp_path,
):
    """CORRECT behavior: NaN `athlete_meta.height` (defensive — even though
    `get_video_meta` guards it at the I/O source today, a future caller
    could pass a hand-crafted `VideoMeta` or a meta with NaN) →
    `process` raises a typed `ValueError` naming the corrupt-resize-meta
    condition.

    RED now: NaN height → `int(NaN * 1280 / 640)` → stdlib
    `ValueError: cannot convert float NaN to integer`. After the fix:
    typed ValueError at the resize guard.
    """
    bad_meta = MagicMock()
    bad_meta.width = 640
    bad_meta.height = float("nan")
    bad_meta.fps = 30.0
    bad_meta.num_frames = 10
    mock_get_meta.return_value = bad_meta
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.set.return_value = True
    cap.release.return_value = None
    cap.read.return_value = (False, None)
    mock_cap_cls.return_value = cap
    mock_writer_cls.return_value = MagicMock()
    extractor = MagicMock()
    tracked = MagicMock()
    tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
    extractor.extract_video_tracked.return_value = tracked
    mock_extractor_cls.return_value = extractor

    cfg = ComparisonConfig(mode=ComparisonMode.SIDE_BY_SIDE, resize_width=1280, max_frames=3)
    renderer = ComparisonRenderer(config=cfg)
    athlete, reference, output = _video_paths(tmp_path)

    with pytest.raises(ValueError, match=r"(?i)corrupt|finite|resize|width|height"):
        renderer.process(athlete, reference, output)


# ---------------------------------------------------------------------------
# Observable 3: NaN reference_meta.width → process() raises typed ValueError.
# ---------------------------------------------------------------------------


@patch("src.visualization.comparison.draw_skeleton")
@patch("src.visualization.comparison.get_skating_optimized_config")
@patch("src.visualization.comparison.PoseSmoother")
@patch("src.visualization.comparison.PoseExtractor")
@patch("src.visualization.comparison.H264Writer")
@patch("src.visualization.comparison.get_video_meta")
@patch("src.visualization.comparison.cv2.VideoCapture")
def test_process_nan_reference_width_raises_typed_value_error(
    mock_cap_cls,
    mock_get_meta,
    mock_writer_cls,
    mock_extractor_cls,
    mock_smoother_cls,
    mock_get_config,
    mock_draw,
    tmp_path,
):
    """CORRECT behavior: NaN `reference_meta.width` → `process` raises
    typed `ValueError`. Same corrupt-resize-meta family as the other NaN
    sources.

    RED now: NaN width → `int(480 * 1280 / NaN)` → stdlib ValueError.
    After the fix: typed ValueError at the resize guard.
    """
    athlete_meta = MagicMock()
    athlete_meta.width = 640
    athlete_meta.height = 480
    athlete_meta.fps = 30.0
    athlete_meta.num_frames = 10

    ref_meta = MagicMock()
    ref_meta.width = float("nan")
    ref_meta.height = 480
    ref_meta.fps = 30.0
    ref_meta.num_frames = 10

    mock_get_meta.side_effect = [athlete_meta, ref_meta]
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.set.return_value = True
    cap.release.return_value = None
    cap.read.return_value = (False, None)
    mock_cap_cls.return_value = cap
    mock_writer_cls.return_value = MagicMock()
    extractor = MagicMock()
    tracked = MagicMock()
    tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
    extractor.extract_video_tracked.return_value = tracked
    mock_extractor_cls.return_value = extractor

    cfg = ComparisonConfig(mode=ComparisonMode.SIDE_BY_SIDE, resize_width=1280, max_frames=3)
    renderer = ComparisonRenderer(config=cfg)
    athlete, reference, output = _video_paths(tmp_path)

    with pytest.raises(ValueError, match=r"(?i)corrupt|finite|resize|width|height"):
        renderer.process(athlete, reference, output)


# ---------------------------------------------------------------------------
# Regression guard: valid finite resize meta passes through unchanged.
# ---------------------------------------------------------------------------


@patch("src.visualization.comparison.draw_skeleton")
@patch("src.visualization.comparison.get_skating_optimized_config")
@patch("src.visualization.comparison.PoseSmoother")
@patch("src.visualization.comparison.PoseExtractor")
@patch("src.visualization.comparison.H264Writer")
@patch("src.visualization.comparison.get_video_meta")
@patch("src.visualization.comparison.cv2.VideoCapture")
def test_process_valid_resize_meta_passes_through(
    mock_cap_cls,
    mock_get_meta,
    mock_writer_cls,
    mock_extractor_cls,
    mock_smoother_cls,
    mock_get_config,
    mock_draw,
    tmp_path,
    mock_video_meta,
):
    """Regression guard: valid 640x480 meta + 1280 resize_width passes
    through unchanged — the corrupt-resize-meta guard must NOT alter
    valid finite meta. PASSES today; locks the contract.
    """
    mock_get_meta.return_value = mock_video_meta
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.set.return_value = True
    cap.release.return_value = None
    cap.read.return_value = (False, None)
    mock_cap_cls.return_value = cap
    mock_writer_cls.return_value = MagicMock()
    extractor = MagicMock()
    tracked = MagicMock()
    tracked.poses = np.zeros((0, 17, 3), dtype=np.float32)
    extractor.extract_video_tracked.return_value = tracked
    mock_extractor_cls.return_value = extractor

    renderer = _renderer_with_resize_width(1280)
    athlete, reference, output = _video_paths(tmp_path)

    # Must not raise — no resize meta corruption.
    renderer.process(athlete, reference, output)


# ---------------------------------------------------------------------------
# Source check: root cause locked — `math.isfinite` (or equivalent NaN/inf
# check) guard present in `ComparisonRenderer.process` on the resize meta.
# ---------------------------------------------------------------------------


def test_process_resize_meta_isfinite_guard_source():
    """GREEN contract source check: the NaN resize-meta crash is fixed by
    a guard in `ComparisonRenderer.process` (the natural trust boundary —
    `process` is the public entry point for the comparison CLI and API)
    that rejects non-finite width/height/target_w with a typed ValueError
    naming the corrupt-resize-meta condition. Mirrors the existing I/O
    source guards in `get_video_meta` (#1041) — but at the resize site
    because `resize_width` is config-sourced (YAML), not I/O-sourced.
    """
    src = inspect.getsource(ComparisonRenderer.process)
    # Guard must reference finite / isnan / isinf somewhere in the resize
    # meta section of process() — the corrupt-resize-meta family.
    has_finite_guard = "isfinite" in src or "isnan" in src or "isinf" in src
    assert has_finite_guard, (
        "BUG: ComparisonRenderer.process must guard non-finite resize meta "
        "(width/height/target_w) — raise a typed ValueError naming the "
        "corrupt-resize-meta condition, NOT let `int(NaN * x / y)` raise "
        "the opaque stdlib `ValueError: cannot convert float NaN to integer` "
        "deep in the resize calculation."
    )
