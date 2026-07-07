"""RED repro — `VizPipeline.draw_frame_counter` int(NaN) crash.

Sibling to `test_collect_export_data_nan_repro.py` (#1115) which locked
the `math.isfinite` guard for the export-timestamp column. This file
targets the OVERLAY crash class (#1105): `draw_frame_counter` divides
`frame_idx / fps` and feeds the result to two unguarded `int()`
conversions that explode on NaN.

The fps=0 / `int(NaN)` crash family was partly addressed by #959
(`if fps > 0 else 0.0` short-circuit). That short-circuit happens to
defang NaN fps by accident (`NaN > 0` is False → 0.0 branch), but
does NOT cover:

  - NaN frame_idx with valid fps:  `nan / 30.0 = nan` passes the
    `fps > 0` guard, then `int(nan) // 60` and
    `int((nan % 1) * 100)` both raise `ValueError`.
  - inf frame_idx with valid fps:  `inf / 30.0 = inf`, then
    `int(inf) // 60` raises `OverflowError` (Python rejects
    `int(inf)`).

The contract (mirrors the #959 degrade-to-0.0 sibling design and
the `collect_export_data` #1115 fix): a non-finite `time_sec` MUST
degrade to 0.0, so the frame counter renders as `00:00.00` (the
fps-independent `frame_idx/total` part is still useful) and the
viz loop does not abort. Lock the root cause location via
`inspect.getsource` — `math.isfinite` must guard the
`frame_idx / fps` division.

Pure-Python (no GPU, no DB): `draw_frame_counter` is a pure-data
overlay op, testable with a dummy frame and a VizPipeline
constructed with the bug-triggering inputs.
"""

from __future__ import annotations

import inspect
import math
from pathlib import Path

import numpy as np

from src.types import VideoMeta
from src.visualization.pipeline import VizPipeline

# ---------------------------------------------------------------------------
# Helpers — build a VizPipeline without running __post_init__ (which would
# call build_layers and require a full layer stack). Same pattern as
# test_collect_export_data_nan_repro.py.
# ---------------------------------------------------------------------------


def _viz(fps: float = 30.0, num_frames: int = 10) -> VizPipeline:
    """A VizPipeline with meta.fps=fps. `draw_frame_counter` only touches
    self.meta.{width,height,num_frames,fps}, so set those plus a minimal
    poses array.
    """
    pipe = VizPipeline.__new__(VizPipeline)
    pipe.meta = VideoMeta(Path("corrupt.mp4"), 320, 240, fps, num_frames)
    pipe.poses_norm = np.zeros((num_frames, 17, 2), dtype=np.float32)
    pipe.poses_px = None
    pipe.frame_indices = np.arange(num_frames)
    pipe.layers = []
    pipe.export_frames = []
    pipe.export_timestamps = []
    pipe.export_floor_angles = []
    pipe.export_joint_angles = []
    pipe.export_poses = []
    return pipe


def _frame() -> np.ndarray:
    return np.zeros((240, 320, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Observable 1: NaN frame_idx with valid fps — must NOT raise
# `ValueError: cannot convert float NaN to integer`. The #1115 contract
# (degrade to 0.0) applies: timestamp renders as 00:00.00, frame counter
# (frame_idx/total — fps-independent) still rendered.
# ---------------------------------------------------------------------------


def test_draw_frame_counter_nan_frame_idx_no_crash_repro():
    """CORRECT: `draw_frame_counter(frame, nan)` with meta.fps=30.0
    must return the frame, NOT raise ValueError at `int(time_sec) // 60`
    or `int((seconds % 1) * 100)`.

    RED now: `nan / 30.0 = nan` passes the `fps > 0` guard
    (`30.0 > 0` is True), so `time_sec = nan`, and both `int(nan)`
    calls raise. The viz loop aborts before the bottom-left frame
    counter is rendered.
    """
    pipe = _viz(fps=30.0)
    out = pipe.draw_frame_counter(_frame(), float("nan"))  # type: ignore[reportArgumentType]
    assert isinstance(out, np.ndarray), (
        f"BUG: draw_frame_counter(frame_idx=nan, fps=30.0) did not "
        f"return a frame (got {type(out).__name__}: {out!r}). "
        f"`int(nan) // 60` or `int((nan%1)*100)` raises ValueError; "
        f"the viz loop aborts before the bottom-left frame counter "
        f"is rendered. Fix: `math.isfinite` guard on `frame_idx / fps` "
        f"-> degrade to 0.0 (mirror `collect_export_data` #1115)."
    )


# ---------------------------------------------------------------------------
# Observable 2: inf frame_idx with valid fps — must NOT raise
# `OverflowError: cannot convert float infinity to integer`. Same root
# cause family as Observable 1.
# ---------------------------------------------------------------------------


def test_draw_frame_counter_inf_frame_idx_no_crash_repro():
    """CORRECT: `draw_frame_counter(frame, inf)` with meta.fps=30.0
    must return the frame, NOT raise OverflowError at `int(time_sec) // 60`.

    RED now: `inf / 30.0 = inf` passes the `fps > 0` guard, then
    `int(inf)` raises OverflowError. Mirror the #1115 isfinite guard.
    """
    pipe = _viz(fps=30.0)
    out = pipe.draw_frame_counter(_frame(), float("inf"))  # type: ignore[reportArgumentType]
    assert isinstance(out, np.ndarray), (
        f"BUG: draw_frame_counter(frame_idx=inf, fps=30.0) did not "
        f"return a frame (got {type(out).__name__}: {out!r}). "
        f"`int(inf) // 60` raises OverflowError; same root cause "
        f"family as NaN frame_idx. Fix: isfinite guard."
    )


# ---------------------------------------------------------------------------
# Observable 3: NaN fps — regression / contract lock. The current
# `if fps > 0 else 0.0` short-circuit happens to defang NaN fps
# (`NaN > 0` is False -> else 0.0), but the contract is fragile
# (accidental, not explicit). The isfinite guard makes the intent
# explicit and matches the #1115 / `phase_detector.py:383` /
# `physics_engine.py:381` trust-boundary pattern.
# ---------------------------------------------------------------------------


def test_draw_frame_counter_nan_fps_no_crash_repro():
    """CORRECT: `draw_frame_counter(frame, 30)` with meta.fps=NaN
    must return the frame. The `if fps > 0` short-circuit happens
    to defang this (NaN > 0 is False -> else 0.0), but the contract
    must hold explicitly via `math.isfinite`.
    """
    pipe = _viz(fps=float("nan"))
    out = pipe.draw_frame_counter(_frame(), 30)
    assert isinstance(out, np.ndarray), (
        f"BUG: draw_frame_counter(fps=nan, frame_idx=30) did not "
        f"return a frame (got {type(out).__name__}: {out!r}). "
        f"Although `NaN > 0` is False and the current `else 0.0` "
        f"branch defangs this by accident, the contract must be "
        f"locked explicitly via `math.isfinite`."
    )


# ---------------------------------------------------------------------------
# Observable 4: regression — valid finite input unchanged. fps=30,
# frame_idx=90 -> minutes=0, seconds=3 (90/30=3.0s). The isfinite
# guard must not change the valid-fps/valid-frame_idx case.
# ---------------------------------------------------------------------------


def test_draw_frame_counter_valid_finite_unchanged_repro():
    """Regression: fps=30, frame_idx=90 must report 00:00:03 (3.0s).
    The isfinite guard must not change the valid-fps/valid-frame_idx
    case. Locks that the fix is surgical and does not regress the
    happy path.
    """
    pipe = _viz(fps=30.0, num_frames=300)
    out = pipe.draw_frame_counter(_frame(), 90)
    assert isinstance(out, np.ndarray), (
        f"BUG (regression): draw_frame_counter(fps=30, frame_idx=90) "
        f"did not return a frame (got {type(out).__name__}: {out!r})."
    )
    # 90 / 30 = 3.0s -> "00:00:03.00" with minutes:02d:seconds:02d.ms:02d
    # and frame counter "90/300  00:00:03.00".
    # We don't introspect the rendered text (draw_text_outlined uses
    # cv2.putText, no easy readback), but we lock the contract: no
    # exception raised on a valid input. The valid-path render is
    # covered by ml/tests/visualization/test_pipeline.py::TestDrawFrameCounter.
    assert math.isfinite(90 / 30.0), "sanity: 90/30 must be finite"


# ---------------------------------------------------------------------------
# Observable 5: source check — `math.isfinite` must guard the
# `frame_idx / fps` division in `draw_frame_counter`. Locks the root
# cause location so a future "simplification" cannot silently drop
# the guard. Mirrors `test_collect_export_data_isfinite_guard_source_repro`.
# ---------------------------------------------------------------------------


def test_draw_frame_counter_isfinite_guard_source_repro():
    """GREEN contract source check: `draw_frame_counter` source must
    contain `math.isfinite` guarding the `frame_idx / fps` division.

    Without this guard, NaN/inf on EITHER side of the division
    propagates into `int(time_sec) // 60` and
    `int((seconds % 1) * 100)`, both of which raise. The `if fps > 0`
    short-circuit is NaN-fps-blind-pass by accident and inf-fps-blind
    in spirit, and is fps-only (ignores NaN/inf frame_idx).

    Mirrors the codebase trust-boundary pattern at
    `collect_export_data` (pipeline.py:215-220, #1115),
    `phase_detector.py:383`, `physics_engine.py:381/486`,
    `types.py:459 VideoMeta.duration_sec`.
    """
    src = inspect.getsource(VizPipeline.draw_frame_counter)
    assert "math.isfinite" in src, (
        "BUG: VizPipeline.draw_frame_counter must guard the "
        "`frame_idx / fps` division with `math.isfinite` "
        "(pipeline.py:183-186). The current `if fps > 0` short-circuit "
        "is NaN-frame_idx-blind - `nan / 30.0 = nan` passes the guard "
        "and crashes at `int(nan) // 60` / `int((nan%1)*100)`. "
        "Mirror the #1115 `collect_export_data` pattern."
    )
