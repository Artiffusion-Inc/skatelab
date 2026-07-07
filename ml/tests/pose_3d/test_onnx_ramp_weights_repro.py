"""Repro tests for #1047: ONNXPoseEstimator sliding-window ramp weights REVERSED.

Bug: `ONNXPoseExtractor.estimate_3d` writes
    `window_weights[:ramp_len] = np.linspace(0.5, 1.0, ramp_len)`  (ramp UP)
    `window_weights[-ramp_len:] = np.linspace(1.0, 0.5, ramp_len)`  (ramp DOWN)
When `frame_count <= 2 * ramp_len` (i.e., `frame_count <= w // 2` for the last
sliding-window chunk) the two slices OVERLAP, the second write overwrites the
first, and the final weight vector is monotonically DECREASING (peak at idx 0)
instead of a symmetric/non-reversed shape.

Contract: the per-window `window_weights` must NOT be monotonically decreasing
from idx 0. The intended shape is symmetric (linspace up + linspace down) so
`weights[i] == weights[-1-i]` for all `i`. The fix is to merge the two ramp
slices with `np.maximum(...)` (or replace with a symmetric `np.minimum(...)`
formula) so overlapping slices no longer overwrite each other.

RED strategy: each test runs the ACTUAL `estimate_3d` source via exec on
the ramp block and checks the resulting `window_weights` shape. On master
the buggy two-write pattern produces a reversed vector that fails the
symmetry/no-monotonic-decrease checks. On fix the merged form passes.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import textwrap
from pathlib import Path

import numpy as np

# Load onnx_extractor directly to avoid pulling in cv2/numba chain
_HERE = Path(__file__).resolve()
_SRC_FILE = _HERE.parents[2] / "src" / "pose_3d" / "onnx_extractor.py"
_spec = importlib.util.spec_from_file_location("onnx_extractor_under_test", _SRC_FILE)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["onnx_extractor_under_test"] = _mod
_spec.loader.exec_module(_mod)
ONNXPoseExtractor = _mod.ONNXPoseExtractor


def _ramp_weights_from_source(frame_count: int, w: int = 81) -> np.ndarray:
    """Exec the ramp block from `estimate_3d` source verbatim and return the
    resulting `window_weights` array. This catches the bug at the source level:
    on master the result is the buggy monotonically-decreasing vector.
    """
    block = _ramp_block_text()
    block = textwrap.dedent(block)
    scope: dict[str, object] = {"np": np, "frame_count": frame_count, "w": w}
    # noqa: S102 — exec is intentional: replicate the ramp block from
    # the source to verify the contract end-to-end (RED on master, GREEN on fix).
    exec(block, scope)  # noqa: S102
    return scope["window_weights"]  # type: ignore[return-value]


def _ramp_block_text() -> str:
    """Return the ramp block source text (from `window_weights = np.ones(...)`
    through the end of the `if ramp_len > 0:` body).
    """
    src = inspect.getsource(ONNXPoseExtractor.estimate_3d)
    lines = src.splitlines()
    start = None
    for i, line in enumerate(lines):
        if "window_weights = np.ones(frame_count, dtype=np.float32)" in line:
            start = i
            break
    assert start is not None, "`window_weights = np.ones(...)` not found"
    if_start = None
    for j in range(start + 1, len(lines)):
        if "if ramp_len > 0:" in lines[j]:
            if_start = j
            break
    assert if_start is not None, "`if ramp_len > 0:` not found"
    if_indent = len(lines[if_start]) - len(lines[if_start].lstrip())
    body_indent = if_indent + 4
    block_end = len(lines)
    for j in range(if_start + 1, len(lines)):
        ln = lines[j]
        if not ln.strip():
            continue
        cur_indent = len(ln) - len(ln.lstrip())
        if cur_indent < body_indent:
            block_end = j
            break
    return "\n".join(lines[start:block_end])


# --- tests ------------------------------------------------------------------


def test_short_window_ramp_not_reversed_repro():
    """frame_count=5 with w=81 → ramp_len=5 → both slices overlap entirely.

    BUGGY: monotonically decreasing [1.0, 0.875, 0.75, 0.625, 0.5]
    FIXED: symmetric — either a triangle (peak at center) or flat
           (np.maximum merge on overlapping slices — both pass symmetry).

    Assert the SYMMETRY of the ramp: weights[i] == weights[-1-i].
    The buggy output is asymmetric: weights[0]=1.0, weights[-1]=0.5.
    """
    weights = _ramp_weights_from_source(frame_count=5, w=81)
    # Symmetric: weights[i] == weights[-1-i] for all i
    for i in range(len(weights)):
        assert abs(weights[i] - weights[-1 - i]) < 1e-5, (
            f"asymmetric ramp at i={i}: {weights[i]} vs {weights[-1 - i]}; full vector: {weights}"
        )
    # NOT monotonically decreasing from idx 0
    # BUGGY: weights[0] = 1.0 (max), weights[-1] = 0.5 (min) — reversed
    # FIXED: weights[0] == weights[-1] (symmetric)
    assert abs(weights[0] - weights[-1]) < 1e-5, (
        f"ramp reversed: weights[0]={weights[0]}, weights[-1]={weights[-1]}; full vector: {weights}"
    )


def test_medium_window_ramp_not_reversed_repro():
    """frame_count=16, w=81 → ramp_len=16 → full overlap.

    BUGGY: monotonically decreasing [1.0, 0.9375, 0.875, ..., 0.5625, 0.5]
    FIXED: symmetric.
    """
    weights = _ramp_weights_from_source(frame_count=16, w=81)
    # Symmetric
    for i in range(len(weights)):
        assert abs(weights[i] - weights[-1 - i]) < 1e-5, (
            f"asymmetric ramp at i={i}: {weights[i]} vs {weights[-1 - i]}; full vector: {weights}"
        )
    # NOT reversed
    assert abs(weights[0] - weights[-1]) < 1e-5, (
        f"ramp reversed: weights[0]={weights[0]}, weights[-1]={weights[-1]}; full vector: {weights}"
    )


def test_long_window_ramp_symmetric_regression():
    """frame_count=50, w=81 → ramp_len=20 → disjoint slices (regression).

    Both the original code and the np.minimum fix produce a symmetric ramp.
    We assert the intended shape: edges at 0.5, symmetric, the central
    plateau is at the min(up[center], down[center]) which for the symmetric
    triangle is `1.0 - ramp_len / (frame_count - 1) * 0.5` — for fc=50,
    ramp_len=20 this is ≈ 0.745.
    """
    weights = _ramp_weights_from_source(frame_count=50, w=81)
    assert abs(float(weights[0]) - 0.5) < 1e-5
    assert abs(float(weights[-1]) - 0.5) < 1e-5
    # Center value = min(up[25], down[25]) ≈ 0.745
    assert 0.7 < float(weights[25]) < 0.8, f"unexpected center value: {weights[25]}"
    # Symmetric
    for i in range(len(weights)):
        assert abs(weights[i] - weights[-1 - i]) < 1e-5, (
            f"asymmetric ramp at i={i}: {weights[i]} vs {weights[-1 - i]}"
        )


def test_overflow_window_ramp_not_reversed_repro():
    """frame_count=25, w=81 → ramp_len=20 → partial overlap.

    Overlap region is [0:20] ∩ [5:25] = [5:20] (length 15). The FIX must
    merge with `maximum` to preserve the rising left ramp. The BUG lets the
    second write win in [5:20], producing a peak at idx 5 (start of the
    overlap region) instead of the window center.

    BUGGY output peak at idx 5 (=1.0), weights[0]=0.5.
    FIXED output symmetric.
    """
    weights = _ramp_weights_from_source(frame_count=25, w=81)
    # Symmetric
    for i in range(len(weights)):
        assert abs(weights[i] - weights[-1 - i]) < 1e-5, (
            f"asymmetric ramp at i={i}: {weights[i]} vs {weights[-1 - i]}; full vector: {weights}"
        )
    # Both edges equal
    assert abs(weights[0] - weights[-1]) < 1e-5, (
        f"ramp reversed: weights[0]={weights[0]}, weights[-1]={weights[-1]}; full vector: {weights}"
    )


def test_ramp_overwrite_source_repro():
    """Source-level check: the ramp block must use a max-merge or symmetric
    formula — not two sequential slice writes where the second silently
    overwrites the first on overlapping windows.

    On master the source has the buggy two-write pattern, so this test FAILS
    (RED). On fix the pattern is replaced with `np.maximum(...)` merge or a
    symmetric `np.minimum(...)` formula, so the test PASSES (GREEN).

    We scope the check to the ramp block only (from `window_weights = np.ones`
    through the end of the `if ramp_len > 0:` body) to avoid matching the
    unrelated `np.maximum(weights, 1e-6)` on the normalization floor.
    """
    src = inspect.getsource(ONNXPoseExtractor.estimate_3d)
    assert "ramp_len" in src, "ramp_len variable not found in estimate_3d"
    # The buggy block used `np.linspace(0.5, 1.0, ramp_len)`; the fix may
    # use `np.linspace(0.5, 1.0, frame_count)` (or any length). Accept
    # either — the bug is in HOW the two slices are combined, not the
    # linspace length.

    ramp_block = _ramp_block_text()
    has_max_merge = "np.maximum(" in ramp_block
    has_symmetric_min = "np.minimum(" in ramp_block
    assert has_max_merge or has_symmetric_min, (
        "Ramp block does not use np.maximum merge or np.minimum symmetric "
        "formula. Two sequential slice writes will overlap on short/medium "
        "windows and the second write will overwrite the first, producing "
        "a reversed (peak-at-idx-0) weight vector instead of a symmetric "
        "triangle peaked at the center."
    )
