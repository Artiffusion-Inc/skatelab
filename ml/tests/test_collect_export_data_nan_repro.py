"""RED repro — `VizPipeline.collect_export_data` silent NaN-leak.

Sits alongside `audit/test_viz_frame_counter_fps_zero_repro.py` which
covers the `fps=0` crash class (the #959 fix already shipped, turning
the `int(NaN) = ValueError` and `ZeroDivisionError` crash sites into a
graceful degrade to 0.0). This file targets the SILENT NaN-LEAK class
(#1115): corrupt video metadata can also surface `fps=nan` (cv2
returning NaN instead of 0 for some codecs), AND callers can pass
`frame_idx=nan` when pose alignment fails. Both routes reach
`round(frame_idx / self.meta.fps, 3)` and silently append NaN to
`self.export_timestamps`, which is then written verbatim to the
biomech CSV by `save_exports`. Downstream (recommender, dashboard)
sees `timestamp_s=nan` for every frame with no signal fps was corrupt.

Bug class: SILENT NaN-LEAK. Different from the #1105 sibling
(`int(NaN) = ValueError` CRASH) and the #959 sibling
(`ZeroDivisionError` CRASH). Same root cause family: missing
`math.isfinite` guard at the trust boundary on the `frame_idx / fps`
division.

Two NaN-leak paths to lock:
  - fps=NaN     → `round(NaN/30, 3) = NaN` (current `if fps > 0 else 0.0`
                   is NaN-blind-pass by accident — `NaN > 0` is False
                   → else 0.0 branch, gives 0.0; but intent is not
                   explicit).
  - frame_idx=NaN → `round(NaN/30, 3) = NaN` (the `if fps > 0` guard is
                   fps-only; NaN frame_idx with valid fps LEAKS NaN).
  - fps=inf     → `inf > 0` is True → `5/inf = 0.0` happens, OK in
                   practice, but the isfinite check makes intent
                   explicit and matches the codebase pattern
                   (`phase_detector.py:383`, `physics_engine.py:381/486`,
                   `VideoMeta.duration_sec`).

The fix (applied): replace the fps-only guard with a `math.isfinite`
guard on BOTH fps and frame_idx. Match the codebase convention:
`math.isfinite(fps) and fps > 0` + `math.isfinite(frame_idx)`. Follow
the #959 degrade-to-0.0 contract: keep the row (joint angles, floor
angle, poses) and mark the timestamp column as 0.0 (unknown elapsed
time). This matches the contract already locked by
`audit/test_viz_frame_counter_fps_zero_repro.py::test_collect_export_data_fps_zero_no_crash_repro`.

RED now: the assertions below describe the CORRECT behavior — the
export_timestamps list MUST contain a finite (0.0) value when either
fps or frame_idx is non-finite, AND a `math.isfinite` guard MUST appear
in the source of `collect_export_data`. They FAIL on master because:
  - the current code has only `if self.meta.fps > 0 else 0.0`, which
    silently leaks NaN for NaN frame_idx (and the source check fails
    on missing isfinite).
  - the NaN fps case happens to be silent-OK by accident (`NaN > 0`
    is False → 0.0 branch) but is not explicit.

Source check via `inspect.getsource` locks the root cause location.

Pure-Python (no GPU, no DB): `collect_export_data` only appends to
lists and calls a pure-data `compute_joint_angles`. Mocked.
"""

from __future__ import annotations

import inspect
import math
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src.visualization.pipeline import VizPipeline

# ---------------------------------------------------------------------------
# Helpers — build a VizPipeline without running __post_init__ (which would
# call build_layers and require a full layer stack). Same pattern as
# audit/test_viz_frame_counter_fps_zero_repro.py.
# ---------------------------------------------------------------------------


def _viz(fps: float = 30.0) -> VizPipeline:
    """Construct a bare VizPipeline with the given fps.

    `collect_export_data` only touches `self.meta.{fps}`, `self.poses_norm`,
    `self.poses_px`, and appends to the export_* lists. All of those are
    set explicitly here. `compute_joint_angles` is mocked per-test.
    """
    pipe = VizPipeline.__new__(VizPipeline)
    pipe.meta = SimpleNamespace(width=320, height=240, fps=fps, num_frames=10)
    pipe.poses_norm = np.zeros((10, 17, 2), dtype=np.float32)
    pipe.poses_px = None
    pipe.frame_indices = np.arange(10)
    pipe.layers = []
    pipe.export_frames = []
    pipe.export_timestamps = []
    pipe.export_floor_angles = []
    pipe.export_joint_angles = []
    pipe.export_poses = []
    return pipe


# ---------------------------------------------------------------------------
# Observable 1: NaN frame_idx with valid fps → NaN must NOT leak to
# export_timestamps. Today: `round(NaN/30.0, 3) = NaN` silently appended.
# ---------------------------------------------------------------------------


def test_collect_export_data_nan_frame_idx_no_leak_repro():
    """CORRECT: `collect_export_data(frame_idx=nan, ...)` must not append
    NaN to `export_timestamps`. The fix follows the #959 contract:
    degrade the timestamp to 0.0 (unknown elapsed time) and keep the
    rest of the row (joint angles, floor angle, pose).

    RED: master has only `if self.meta.fps > 0 else 0.0`, which is
    NaN-frame_idx-blind — `round(NaN/30.0, 3) = NaN` silently appended,
    then `save_exports` writes `timestamp_s=nan` to the biomech CSV.
    """
    pipe = _viz(fps=30.0)
    with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
        pipe.collect_export_data(frame_idx=float("nan"), pose_idx=0, floor_angle=0.0)

    assert len(pipe.export_timestamps) == 1, (
        f"collect_export_data dropped the timestamp row entirely "
        f"(timestamps: {pipe.export_timestamps!r}). The #959 contract "
        f"is degrade-to-0.0 (keep the row, mark timestamp unknown)."
    )
    assert math.isfinite(pipe.export_timestamps[0]), (
        f"BUG: collect_export_data(frame_idx=nan, fps=30.0) silently "
        f"leaked NaN to export_timestamps={pipe.export_timestamps!r}. "
        f"`round(NaN/30.0, 3) = NaN` written verbatim to the biomech CSV "
        f"by save_exports. Fix: guard with `math.isfinite` on BOTH fps "
        f"and frame_idx (mirror phase_detector.py:383 / physics_engine.py:381)."
    )
    assert pipe.export_timestamps[0] == 0.0, (
        f"BUG: corrupt frame_idx should degrade timestamp to 0.0, got "
        f"{pipe.export_timestamps[0]!r}."
    )


# ---------------------------------------------------------------------------
# Observable 2: inf fps → must not silently emit 0.0 via the `inf > 0`
# path. The isfinite guard must catch this and degrade explicitly.
# ---------------------------------------------------------------------------


def test_collect_export_data_inf_fps_no_leak_repro():
    """CORRECT: `collect_export_data` with meta.fps=inf must not produce
    a non-finite timestamp. The fix follows the #959 degrade-to-0.0
    contract.

    RED: `inf > 0` is True, so the current `if fps > 0 else 0.0` takes
    the `5/inf = 0.0` path — works numerically but the guard is
    semantically wrong (intends to catch only fps=0 broken-header).
    The isfinite guard makes the intent explicit.
    """
    pipe = _viz(fps=float("inf"))
    with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
        pipe.collect_export_data(frame_idx=5, pose_idx=0, floor_angle=0.0)

    assert len(pipe.export_timestamps) == 1, (
        f"collect_export_data dropped the timestamp row entirely "
        f"(timestamps: {pipe.export_timestamps!r}). The contract is "
        f"degrade-to-0.0 (keep the row, mark timestamp unknown)."
    )
    assert math.isfinite(pipe.export_timestamps[0]), (
        f"BUG: inf fps produced non-finite timestamp "
        f"{pipe.export_timestamps[0]!r}. The isfinite guard must catch inf."
    )
    assert pipe.export_timestamps[0] == 0.0, (
        f"BUG: inf fps should degrade timestamp to 0.0, got {pipe.export_timestamps[0]!r}."
    )


# ---------------------------------------------------------------------------
# Observable 3: regression — valid fps + valid frame_idx unchanged.
# Locks the contract that the fix does not break the happy path.
# ---------------------------------------------------------------------------


def test_collect_export_data_valid_fps_valid_frame_idx_unchanged_repro():
    """Regression: fps=30, frame_idx=15 must still report 0.5s. The
    isfinite guard must not change the valid-input case.
    """
    pipe = _viz(fps=30.0)
    with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
        pipe.collect_export_data(frame_idx=15, pose_idx=0, floor_angle=0.0)
    assert pipe.export_timestamps[0] == 0.5, (
        f"BUG (regression): fps=30, frame_idx=15 should give 0.5s, got "
        f"{pipe.export_timestamps[0]!r}. The isfinite guard must not "
        f"change the valid-fps/valid-frame_idx case."
    )
    assert math.isfinite(pipe.export_timestamps[0]), (
        f"BUG (regression): valid input produced non-finite timestamp "
        f"{pipe.export_timestamps[0]!r}."
    )


# ---------------------------------------------------------------------------
# Observable 4: NaN fps — the existing `if fps > 0 else 0.0` happens to
# be silent-OK (NaN > 0 is False → 0.0), but the test locks the contract
# that the fix must keep this behavior with an explicit isfinite guard.
# ---------------------------------------------------------------------------


def test_collect_export_data_nan_fps_no_leak_repro():
    """CORRECT: collect_export_data with meta.fps=NaN must not produce
    NaN in export_timestamps. The fix follows the #959 degrade-to-0.0
    contract.
    """
    pipe = _viz(fps=float("nan"))
    with mock.patch("src.analysis.angles.compute_joint_angles", return_value={}):
        pipe.collect_export_data(frame_idx=5, pose_idx=0, floor_angle=0.0)

    assert len(pipe.export_timestamps) == 1, (
        f"collect_export_data dropped the timestamp row entirely "
        f"(timestamps: {pipe.export_timestamps!r}). The contract is "
        f"degrade-to-0.0 (keep the row, mark timestamp unknown)."
    )
    assert math.isfinite(pipe.export_timestamps[0]), (
        f"BUG: collect_export_data(fps=NaN) leaked NaN to "
        f"export_timestamps={pipe.export_timestamps!r}."
    )
    assert pipe.export_timestamps[0] == 0.0, (
        f"BUG: NaN fps should degrade timestamp to 0.0, got {pipe.export_timestamps[0]!r}."
    )


# ---------------------------------------------------------------------------
# Source check: lock the root cause location — `math.isfinite` MUST
# appear in `collect_export_data` source. Today the source has only
# `if self.meta.fps > 0 else 0.0`, no isfinite. After the fix, isfinite
# must guard the division.
# ---------------------------------------------------------------------------


def test_collect_export_data_isfinite_guard_source_repro():
    """GREEN contract source check: `collect_export_data` source must
    contain `math.isfinite` guarding the `frame_idx / self.meta.fps`
    division. Without this guard, NaN/inf on either side silently leaks
    NaN to the CSV biomech export. Mirrors the codebase pattern at
    `phase_detector.py:383`, `physics_engine.py:381/486`,
    `types.py:459 VideoMeta.duration_sec`.
    """
    src = inspect.getsource(VizPipeline.collect_export_data)
    assert "math.isfinite" in src, (
        "BUG: VizPipeline.collect_export_data must guard the "
        "`frame_idx / self.meta.fps` division with `math.isfinite` "
        "(pipeline.py:208-210). NaN frame_idx with valid fps silently "
        "leaks NaN to export_timestamps → CSV `timestamp_s=nan`. "
        "NaN fps is NaN-blind-pass with `if fps > 0 else 0.0` only by "
        "accident. Mirror the trust-boundary pattern at phase_detector.py:383."
    )
