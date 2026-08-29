"""RED repro — `VizPipeline.draw_frame_counter` and `collect_export_data`
divide by `meta.fps` with no fps=0 guard:

    time_sec = frame_idx / fps                       # pipeline.py:178
    self.export_timestamps.append(round(frame_idx / self.meta.fps, 3))  # :200

Corrupt / truncated video reports `cv2.CAP_PROP_FPS = 0` (OpenCV sentinel
for unknown framerate). `meta.fps = 0.0` → `draw_frame_counter(frame, 0)`
→ `0 / 0.0` → ZeroDivisionError on the FIRST frame (Python scalar `0/0.0`
raises, unlike NumPy `0/0 → nan`). The viz loop aborts before the first
overlay frame is rendered — NO annotated output video for a session whose
metrics computed successfully. `collect_export_data` crashes the same way,
aborting the CSV/NPY export timestamp column mid-collection.

Sibling consistency (#499 fps=0 family): the TimerLayer overlay sibling
(`visualization/layers/timer_layer.py:25`) guards `if fps <= 0: return
frame` — graceful skip of the timestamp overlay. VizPipeline's
frame-counter overlay (bottom-left) and export-timestamp column do the
SAME `frame_idx / fps` division WITHOUT a guard. Same-input, sibling-
overlay, inconsistent-guard. 10+ other sibling paths already guard fps=0
(VideoMeta.duration_sec, phase_detector:234, physics_engine #937/#939,
pose_tracker #952, smoothing #948, analyzer_save #647, TAS #950,
metrics #958, spin_classifier #505).

The fix (NOT applied — repro only): guard the timestamp division, mirroring
the TimerLayer sibling's `if fps <= 0` graceful-skip design but keeping the
frame counter (which does NOT need fps — `frame_idx/total` is fps-
independent):
  - draw_frame_counter (pipeline.py:178): `time_sec = frame_idx / fps if fps > 0 else 0.0`
    → timestamp renders `00:00.00`, frame counter still shows `frame_idx/total`.
  - collect_export_data (pipeline.py:200): `round(frame_idx / self.meta.fps, 3) if self.meta.fps > 0 else 0.0`
    → export timestamp column degrades to 0.0.
Per-division guard, smallest diff, mirrors TimerLayer's "degrade, not crash".

The correct contract: `VizPipeline(meta.fps=0.0).draw_frame_counter(frame,
frame_idx)` must NOT raise ZeroDivisionError — must render the frame
counter with timestamp `00:00.00` (frame_idx/total still useful without
fps), mirroring the TimerLayer sibling's graceful degradation.
`collect_export_data` must append a finite (0.0) timestamp, NOT crash.

RED now: the observable assertions below describe the CORRECT behavior —
fps=0 no crash, frame returned, finite export timestamp. They FAIL because
`frame_idx / 0.0` raises. The source-check confirms the `if fps > 0` guard
is present at both divide sites (root cause locked).

Pure-Python (no GPU, no DB): `draw_frame_counter` is a pure-data overlay
op; `collect_export_data` appends to lists. Both testable with a dummy
frame and a VizPipeline constructed with meta.fps=0.0.
"""

import inspect
from pathlib import Path

import numpy as np

from src.types import VideoMeta
from src.visualization.pipeline import VizPipeline


def _viz(fps: float = 0.0) -> VizPipeline:
    """A VizPipeline with meta.fps=fps. draw_frame_counter / collect_export_data
    only touch self.meta.{width,height,num_frames,fps} + self.poses_norm /
    self.poses_px, so set the meta and a minimal poses array. fps=0.0 is
    the corrupt-video case; fps=30.0 is the regression baseline.
    """
    pipe = VizPipeline.__new__(VizPipeline)
    pipe.meta = VideoMeta(Path("corrupt.mp4"), 320, 240, fps, 10)
    pipe.poses_norm = np.zeros((10, 17, 2), dtype=np.float32)
    pipe.poses_px = None
    pipe.export_frames = []
    pipe.export_timestamps = []
    pipe.export_floor_angles = []
    pipe.export_joint_angles = []
    pipe.export_poses = []
    return pipe


def _frame() -> np.ndarray:
    return np.zeros((240, 320, 3), dtype=np.uint8)


# --------------------------------------------------------------------------- #
# Observable 1: `draw_frame_counter(fps=0.0)` — no crash, returns frame,
# frame counter rendered with 00:00.00 timestamp.
# --------------------------------------------------------------------------- #


def test_draw_frame_counter_fps_zero_no_crash_repro():
    """CORRECT behavior: `draw_frame_counter(frame, 0)` with meta.fps=0.0
    must return the frame (frame counter rendered with timestamp
    00:00.00), NOT raise ZeroDivisionError.

    RED now: `frame_idx / 0.0` (pipeline.py:178) raises ZeroDivisionError
    on the FIRST frame (frame_idx=0, `0/0.0` raises in Python). After the
    fix: `time_sec = frame_idx / fps if fps > 0 else 0.0` → timestamp
    00:00.00, frame counter `0/10` still rendered.
    """
    pipe = _viz(fps=0.0)
    out = pipe.draw_frame_counter(_frame(), 0)
    assert isinstance(out, np.ndarray), (
        f"BUG: draw_frame_counter(fps=0.0) did not return a frame (got "
        f"{type(out).__name__}: {out!r}). Corrupt video fps=0 → "
        f"frame_idx/0.0 ZeroDivisionError on the FIRST frame; viz loop "
        f"aborts before any overlay is rendered — NO annotated video."
    )


# --------------------------------------------------------------------------- #
# Observable 2: non-zero frame_idx at fps=0 — `5 / 0.0` also no crash.
# Locks that the guard covers all frame_idx, not just 0.
# --------------------------------------------------------------------------- #


def test_draw_frame_counter_fps_zero_nonzero_idx_no_crash_repro():
    """CORRECT behavior: `draw_frame_counter(frame, 5)` with meta.fps=0.0
    must not crash. frame_idx=5 → `5 / 0.0` raises today.
    """
    pipe = _viz(fps=0.0)
    out = pipe.draw_frame_counter(_frame(), 5)
    assert isinstance(out, np.ndarray), (
        "BUG: draw_frame_counter(fps=0.0, frame_idx=5) crashed. "
        "5/0.0 ZeroDivisionError today; guard must cover all frame_idx."
    )


# --------------------------------------------------------------------------- #
# Observable 3: `collect_export_data(fps=0.0)` — no crash, appends finite
# (0.0) timestamp. Export collection not aborted mid-loop.
# --------------------------------------------------------------------------- #


def test_collect_export_data_fps_zero_no_crash_repro():
    """CORRECT behavior: `collect_export_data(frame_idx=0, pose_idx=0)`
    with meta.fps=0.0 must append a finite (0.0) timestamp, NOT raise
    ZeroDivisionError. The CSV/NPY export timestamp column degrades to
    0.0 (unknown elapsed time), export collection continues.

    RED now: `frame_idx / self.meta.fps` (pipeline.py:200) raises
    ZeroDivisionError, aborting the per-frame export collection mid-loop.
    After the fix: `... if self.meta.fps > 0 else 0.0` → 0.0 appended.
    """
    pipe = _viz(fps=0.0)
    pipe.collect_export_data(frame_idx=0, pose_idx=0, floor_angle=0.0)
    assert len(pipe.export_timestamps) == 1, (
        f"BUG: collect_export_data(fps=0.0) did not append a timestamp "
        f"(got {pipe.export_timestamps!r}). frame_idx/fps ZeroDivisionError "
        f"today aborts export collection mid-loop."
    )
    assert np.isfinite(pipe.export_timestamps[0]), (
        f"BUG: collect_export_data(fps=0.0) appended non-finite timestamp "
        f"{pipe.export_timestamps[0]!r}. Degrade to 0.0 (mirror TimerLayer)."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps unchanged — fps=30 reports finite nonzero
# timestamp for frame_idx>0.
# --------------------------------------------------------------------------- #


def test_draw_frame_counter_valid_fps_unchanged_repro():
    """Regression guard: fps=30 with frame_idx=15 must report a finite
    nonzero timestamp (15/30 = 0.5s). The fps>0 guard must not change the
    valid-fps case. PASSES today; locks the contract.
    """
    pipe = _viz(fps=30.0)
    pipe.collect_export_data(frame_idx=15, pose_idx=0, floor_angle=0.0)
    assert pipe.export_timestamps[0] == 0.5, (
        f"BUG (regression): fps=30, frame_idx=15 should give 0.5s, got "
        f"{pipe.export_timestamps[0]!r}. The fps>0 guard must not change "
        f"the valid-fps case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `if fps > 0` guard at both divide sites.
# --------------------------------------------------------------------------- #


def test_viz_frame_counter_fps_zero_guard_source_repro():
    """GREEN contract source check: the fps=0 crash is fixed by a
    per-division `if fps > 0 else 0.0` guard at BOTH `draw_frame_counter`
    (pipeline.py:178) and `collect_export_data` (pipeline.py:200),
    mirroring the TimerLayer sibling (timer_layer.py:25) graceful-
    degradation design (degrade to 0.0, keep the fps-independent frame
    counter).
    """
    dc_src = inspect.getsource(VizPipeline.draw_frame_counter)
    assert "fps > 0" in dc_src, (
        "BUG: draw_frame_counter must guard `frame_idx / fps if fps > 0 "
        "else 0.0` (pipeline.py:178). Corrupt video fps=0 → "
        "ZeroDivisionError on the FIRST frame. Mirror TimerLayer sibling."
    )
    ce_src = inspect.getsource(VizPipeline.collect_export_data)
    assert "fps > 0" in ce_src, (
        "BUG: collect_export_data must guard `frame_idx / self.meta.fps if "
        "self.meta.fps > 0 else 0.0` (pipeline.py:200). Same fps=0 crash "
        "as draw_frame_counter; export timestamp column must degrade to 0.0."
    )
