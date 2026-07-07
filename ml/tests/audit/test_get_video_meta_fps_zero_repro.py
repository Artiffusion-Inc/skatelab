"""RED repro — `get_video_meta` leaks `VideoMeta(fps=0.0)` for corrupt video.

`cv2.CAP_PROP_FPS=0.0` is OpenCV's documented sentinel for "unknown
framerate" (damaged container, broken mp4 atoms, re-encoded clips, old
phone exports). `get_video_meta` (utils/video.py:49-54) does
`fps = cap.get(cv2.CAP_PROP_FPS)` then `float(fps)` with NO guard — 0.0
passes straight into `VideoMeta(fps=0.0)`. This is the **upstream root
cause of the whole #499 fps=0 family**: 11+ downstream per-site guards
exist BECAUSE this producer leaks fps=0. `VideoMeta.duration_sec`
(types.py:450) already knows fps=0 is degenerate (`if self.fps > 0 else
0.0`) — but that is a read-only property on an already-poisoned VideoMeta;
the guard belongs at CONSTRUCTION (`get_video_meta`), not at every read.

Blast radius: every fps-consuming consumer (pose_tracker DA, smoothing CY,
phase_detector, physics CV/CW, metrics DB, TAS CZ, viz DC, backend save
DD). One guard here collapses the family at source; per-site guards become
defense-in-depth, not the only line.

The fix (NOT applied — repro only): normalize fps at the trust boundary —
`None` / `<= 0` / non-finite → sane default 30.0 (matching
`VideoMeta.duration_sec`'s "fps=0 is degenerate" philosophy). The video is
NOT rejected (frames still extractable; analysis still runs at a nominal
framerate) — only the degenerate metadata is corrected.

Contract: `get_video_meta` on a corrupt video (CAP_PROP_FPS=0.0) must
return a `VideoMeta` with a finite, strictly-positive fps (NOT 0.0), so
`duration_sec` is non-degenerate (num_frames/fps, not 0.0) and downstream
`/fps` divisions never hit ZeroDivisionError.

RED now: the observable assertions below describe CORRECT behavior —
fps=0 input → VideoMeta.fps > 0 finite, duration_sec = num_frames/fps
(non-zero). They FAIL because `float(0.0)` passes through. The
source-check confirms the guard is present (root cause locked).

Pure-Python: `cv2.VideoCapture` mocked via `patch('src.utils.video.cv2.
VideoCapture')` — no real video file, no GPU, no DB.
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2

from src.types import VideoMeta
from src.utils.video import get_video_meta


def _mock_cap(
    *, fps: float, width: int = 640, height: int = 480, num_frames: int = 150
) -> MagicMock:
    """A mock cv2.VideoCapture whose .get(propId) returns the given fps /
    dims. isOpened()=True so open_video() doesn't raise. release()=noop."""
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


def _meta_with_fps(fps: float) -> VideoMeta:
    """Call get_video_meta with cv2.VideoCapture mocked to return the given
    raw CAP_PROP_FPS value. The path must exist for open_video (it checks
    path.exists()); use a real file (this repro file itself) so the check
    passes without patching."""
    path = Path(__file__)  # real file — open_video's exists() check passes
    with patch("src.utils.video.cv2.VideoCapture", return_value=_mock_cap(fps=fps)):
        return get_video_meta(path)


# --------------------------------------------------------------------------- #
# Observable 1: fps=0.0 (corrupt video sentinel) — must NOT leak as 0.0.
# Normalized to a finite, strictly-positive fps. duration_sec non-degenerate.
# --------------------------------------------------------------------------- #


def test_get_video_meta_fps_zero_normalized_repro():
    """CORRECT behavior: CAP_PROP_FPS=0.0 (corrupt-video sentinel) →
    `get_video_meta` returns `VideoMeta.fps` finite AND > 0 (NOT 0.0), so
    `duration_sec = num_frames / fps` is non-degenerate (150/30 = 5.0s, not
    0.0). Downstream `/fps` never hits ZeroDivisionError.

    RED now: `float(0.0)` passes through → VideoMeta.fps=0.0 →
    duration_sec=0.0 (degenerate for a 150-frame video). After the fix:
    fps<=0 normalized to 30.0 → duration_sec=5.0.
    """
    meta = _meta_with_fps(fps=0.0)
    assert meta.fps > 0 and meta.fps == meta.fps, (
        f"BUG: get_video_meta leaked fps=0.0 (got {meta.fps!r}) — upstream "
        f"root cause of #499 fps=0 family. Corrupt video → "
        f"VideoMeta.fps=0.0 → every downstream /fps ZeroDivisionError. "
        f"Normalize fps<=0 to a sane default (30.0) at construction."
    )
    assert meta.duration_sec > 0, (
        f"BUG: VideoMeta.fps=0.0 → duration_sec={meta.duration_sec!r} "
        f"(degenerate for a 150-frame video). duration_sec guard is a "
        f"read-only property on an already-poisoned VideoMeta; the guard "
        f"belongs at get_video_meta construction."
    )


# --------------------------------------------------------------------------- #
# Observable 2: fps=None (some OpenCV builds return None for missing prop) —
# same normalization.
# --------------------------------------------------------------------------- #


def test_get_video_meta_fps_none_normalized_repro():
    """CORRECT behavior: CAP_PROP_FPS=None (some OpenCV builds return None
    for a missing/broken metadata atom) → normalized to finite > 0 fps.
    `float(None)` raises TypeError today (or passes as 0.0 if coerced) —
    either way degenerate.

    RED now: `float(None)` → TypeError, OR if the guard only checks `<= 0`
    it misses None. After the fix: None / <=0 / non-finite all normalized.
    """
    meta = _meta_with_fps(fps=None)  # type: ignore[arg-type]
    assert meta.fps > 0, (
        f"BUG: get_video_meta leaked fps=None as {meta.fps!r}. None is a "
        f"real CAP_PROP_FPS return on some OpenCV builds for missing "
        f"metadata; the guard must cover None, not just <= 0."
    )


# --------------------------------------------------------------------------- #
# Observable 3: fps=NaN (corrupt float metadata) — normalized to finite.
# --------------------------------------------------------------------------- #


def test_get_video_meta_fps_nan_normalized_repro():
    """CORRECT behavior: CAP_PROP_FPS=NaN (garbage float in a damaged
    container) → normalized to a finite, > 0 fps. `float(nan)` is finite-
    passing but degenerate — `num_frames / nan = nan` poisons duration_sec.

    RED now: `float(nan)` passes → VideoMeta.fps=nan → duration_sec=nan.
    After the fix: non-finite fps normalized to 30.0.
    """
    import math

    meta = _meta_with_fps(fps=float("nan"))
    assert math.isfinite(meta.fps) and meta.fps > 0, (
        f"BUG: get_video_meta leaked fps=NaN as {meta.fps!r} → "
        f"duration_sec=nan poisons the whole VideoMeta. The guard must "
        f"reject non-finite fps, not just <= 0."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps passes through unchanged.
# --------------------------------------------------------------------------- #


def test_get_video_meta_valid_fps_unchanged_repro():
    """Regression guard: fps=29.97 (real video) passes through unchanged —
    the normalization must NOT alter a valid finite > 0 fps. PASSES today;
    locks the contract.
    """
    meta = _meta_with_fps(fps=29.97)
    assert abs(meta.fps - 29.97) < 1e-9, (
        f"BUG (regression): valid fps=29.97 must pass through unchanged, "
        f"got {meta.fps!r}. The fps<=0/None/NaN normalization must not "
        f"touch a valid finite > 0 fps."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — guard at the construction site.
# --------------------------------------------------------------------------- #


def test_get_video_meta_fps_zero_guard_source_repro():
    """GREEN contract source check: the fps=0 leak is fixed by a guard at
    the CONSTRUCTION site (`get_video_meta`, utils/video.py:49-54) that
    normalizes `None` / `<= 0` / non-finite fps to a sane default (30.0),
    collapsing the #499 fps=0 family at its upstream root. The raw
    `fps=float(fps)` pass-through must be gone.
    """
    src = inspect.getsource(get_video_meta)
    assert "fps <= 0" in src or "fps > 0" in src, (
        "BUG: get_video_meta must guard CAP_PROP_FPS — normalize None / "
        "<= 0 / non-finite to a sane default (30.0) at construction. This "
        "is the upstream root cause of the #499 fps=0 family; 11+ "
        "downstream per-site guards exist because this producer leaks "
        "fps=0. Fix once here, not at every read."
    )
    # The raw degenerate fps must be normalized BEFORE the VideoMeta is
    # constructed — the guard must run on the cap.get() result, not just
    # leave float(fps) to pass 0.0/None/NaN through.
    assert "np.isfinite" in src, (
        "BUG: guard must reject non-finite (NaN/inf) fps, not just <= 0. "
        "A damaged container can return CAP_PROP_FPS=NaN — float(nan) "
        "passes the <=0 check and poisons duration_sec=nan."
    )
