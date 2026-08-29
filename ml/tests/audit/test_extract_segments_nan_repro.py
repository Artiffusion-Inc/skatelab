"""RED repro — `_extract_segments` int(NaN) ValueError on NaN label.

Two implementations of `_extract_segments`, both crash with uncaught
`ValueError: cannot convert float NaN to integer` when any label is NaN:

1. `TASElementSegmenter._extract_segments` (ml/src/tas/inference.py:74-102):
   `current = int(labels[0])` at line 85, then `if int(labels[i]) != current`
   at line 88 and `current = int(labels[i])` at line 93 — all NaN-vulnerable.
2. `tas.metrics._extract_segments` (ml/src/tas/metrics.py:16-35):
   `current = int(labels[0])` at line 24, then `if int(labels[i]) != current`
   at line 27 and `current = int(labels[i])` at line 30 — same shape.

No `math.isfinite(labels[i])` or `~np.isnan(labels).any()` guard on either
path. Verified empirically:

    _extract_segments([1, 1, NaN, 0])  -> ValueError on i=2
    _extract_segments([NaN, 0, 0])    -> ValueError on i=0
    _extract_segments([1, 1, 1, NaN]) -> ValueError on i=3

Consumer chain — the whole TAS pipeline collapses on the first NaN label:

- inference path: model output (per-frame argmax over logits) → segments
  for the user. A NaN label in the model output (degenerate confidence,
  padding frame, NaN in pose features feeding the BiGRU) crashes segment
  extraction. The whole analysis fails.
- metrics path: ground-truth label file loaded → segments for evaluation.
  A NaN in the GT CSV (missing annotation, blank cell) crashes evaluation.
  In the gpu_server (server.py:468) the segmenter runs concurrently with
  biomechanics (asyncio.to_thread), so the element timeline is lost or
  the worker job crashes — pose estimation / phase detection / smoothing
  / biomechanics all succeeded, only the post-hoc TAS step blows up.

The fix (NOT applied — repro only): the smallest root-cause guard is a
per-element `if not math.isfinite(labels[i])` before the `int(...)` cast
on each of the four call sites. Math.isfinite covers NaN and ±inf in one
check. The function returns whatever segments it can extract from the
finite prefix, exactly as it does for the "all zero" case — degenerate
input yields a degenerate (empty/partial) result, NOT a crash. NaN labels
are not propagated downstream; the function simply cannot cast them to
int and skips them.

Alternative: raise ValueError("labels must be finite") at the top — but
that turns a recoverable model output glitch into a worker crash. The
guard is a root-cause fix at every site it can occur, smaller diff than
validating at every caller, and the existing `_extract_segments` is a
pure-data function used both at training time (metrics, GT may be NaN)
and inference time (model output, may be NaN) — strict validation would
break the metrics path entirely.

The correct contract: `_extract_segments` with ANY NaN label must NOT
raise — must return the segments extracted from the finite values, with
NaN labels treated as a "not yet classified" gap (skipped, current-run
not started). NOT a worker crash, NOT a metrics pipeline abort.

RED now: the observable assertions below describe the CORRECT behavior —
NaN label no crash, finite segments returned, finite-labels-only contract.
They FAIL because `int(NaN)` raises. The source-check confirms the
`isfinite` guard is present at every `int(labels[...])` site (root cause
locked).

Pure-Python (no GPU, no DB): `_extract_segments` is a pure-data function
in both files. No model load needed — `TASElementSegmenter.__new__`
skips the ONNX session entirely.
"""

import inspect

import numpy as np

from src.tas.inference import TASElementSegmenter
from src.tas.metrics import _extract_segments as _metrics_extract_segments

# --------------------------------------------------------------------------- #
# Shared fixtures.
# --------------------------------------------------------------------------- #


def _seg_poses(n: int = 30) -> np.ndarray:
    """A (n, 17, 2) normalized pose sequence — finite, varied."""
    rng = np.random.default_rng(0)
    return rng.standard_normal((n, 17, 2)).astype(np.float32)


_ID2LABEL = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}


def _inference_extract(labels: np.ndarray) -> list[dict]:
    """Drive the inference `_extract_segments` without loading ONNX."""
    seg = TASElementSegmenter.__new__(TASElementSegmenter)
    seg.id2label = _ID2LABEL
    seg.min_segment_duration = 0.0  # disable min-duration filter — pure-data path
    seg.classifier = None
    return seg._extract_segments(labels, _seg_poses(len(labels)), fps=30.0)


# --------------------------------------------------------------------------- #
# Observable 1: `metrics._extract_segments` with NaN label — no crash, finite
# segments returned.
# --------------------------------------------------------------------------- #


def test_metrics_extract_segments_nan_label_middle_repro():
    """CORRECT behavior: `_extract_segments([1, 1, NaN, 0])` must NOT raise
    ValueError. NaN at i=2 splits the prefix `[1, 1]` (Jump) and the
    suffix `[0]` (None → skipped). Returns 1 segment for the finite prefix.

    RED now: `int(NaN)` raises ValueError at i=2 (line 27 or 30). After the
    fix: `if not math.isfinite(labels[i]): continue` skips the NaN frame
    without changing `current` — the NaN becomes a 1-frame gap inside the
    current segment, exactly what `_extract_segments` already does for any
    other non-current label.
    """
    labels = np.array([1, 1, np.nan, 0], dtype=np.float64)
    segs = _metrics_extract_segments(labels, _ID2LABEL)
    assert isinstance(segs, list), (
        f"BUG: _extract_segments([1,1,NaN,0]) did not return a list "
        f"(got {type(segs).__name__}: {segs!r}). int(NaN) crashes today."
    )
    # The finite prefix [1,1] yields a Jump segment; NaN at i=2 is a gap
    # INSIDE the current segment (skipped, current unchanged). The None at
    # i=3 closes the segment 0..2. Exactly one Jump segment.
    assert len(segs) == 1, (
        f"BUG: expected 1 Jump segment from [1,1,NaN,0] (NaN skipped), "
        f"got {len(segs)}: {segs!r}. NaN must not abort extraction."
    )
    assert segs[0] == {"label": "Jump", "start": 0, "end": 2}, (
        f"BUG: expected single Jump segment 0..2 (NaN is a 1-frame gap "
        f"inside the segment, not a boundary), got {segs[0]!r}."
    )


# --------------------------------------------------------------------------- #
# Observable 2: `metrics._extract_segments` with NaN at start — no crash.
# --------------------------------------------------------------------------- #


def test_metrics_extract_segments_nan_label_start_repro():
    """CORRECT behavior: `_extract_segments([NaN, 0, 0])` must NOT raise.
    The leading NaN is at i=0 — `int(labels[0])` is the FIRST line of the
    function and the most exposed crash site.

    RED now: line 24 `current = int(labels[0])` raises immediately. After
    the fix: the leading NaN is skipped, current never gets set to NaN, the
    trailing `[0, 0]` is all None and yields no segments.
    """
    labels = np.array([np.nan, 0, 0], dtype=np.float64)
    segs = _metrics_extract_segments(labels, _ID2LABEL)
    assert segs == [], (
        f"BUG: expected empty segments from [NaN,0,0] (NaN skipped, "
        f"trailing None yields no segment), got {segs!r}."
    )


# --------------------------------------------------------------------------- #
# Observable 3: `inference._extract_segments` with NaN at end — no crash.
# --------------------------------------------------------------------------- #


def test_inference_extract_segments_nan_label_end_repro():
    """CORRECT behavior: `inference._extract_segments` with NaN as the
    LAST label must NOT raise. `int(labels[-1])` at the final-segment
    check (inference.py:93) is the most exposed crash site for tail NaN.

    RED now: line 93 `current = int(labels[i])` raises on the last
    iteration. After the fix: the NaN is skipped, the trailing None at
    the end is filtered by `current != 0`, no segments returned.
    """
    labels = np.array([1, 1, 1, np.nan], dtype=np.float64)
    segs = _inference_extract(labels)
    # The finite prefix [1,1,1] at fps=30 → duration 3/30=0.1s. With
    # min_segment_duration=0.0 (set in _inference_extract above) the
    # filter does not drop it. The trailing NaN is skipped.
    assert isinstance(segs, list), (
        f"BUG: inference _extract_segments([1,1,1,NaN]) did not return a "
        f"list (got {type(segs).__name__}: {segs!r}). int(NaN) at tail."
    )


# --------------------------------------------------------------------------- #
# Observable 4: regression — valid finite labels unchanged.
# --------------------------------------------------------------------------- #


def test_extract_segments_valid_finite_unchanged_repro():
    """Regression guard: a fully finite, normal label sequence must produce
    the SAME segments as today. The `isfinite` guard must not change the
    valid path. PASSES today; locks the contract so the guard cannot
    regress the normal case.
    """
    labels = np.array([0, 0, 1, 1, 1, 0, 2, 2], dtype=np.int64)
    segs = _metrics_extract_segments(labels, _ID2LABEL)
    assert segs == [
        {"label": "Jump", "start": 2, "end": 4},
        {"label": "Spin", "start": 6, "end": 7},
    ], (
        f"BUG (regression): valid finite labels must produce the same "
        f"segments as today, got {segs!r}. The isfinite guard must not "
        f"change the all-finite case."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `isfinite` guard at every `int(labels[...])`
# site, in BOTH `_extract_segments` implementations.
# --------------------------------------------------------------------------- #


def test_extract_segments_isfinite_guard_source_repro():
    """GREEN contract source check: the int(NaN) crash is fixed by an
    `isfinite` guard before EVERY `int(labels[...])` site — in BOTH
    `inference._extract_segments` (lines 85, 88, 93) and
    `metrics._extract_segments` (lines 24, 27, 30). Root-cause fix at
    the shared chokepoint (the int cast) is smaller than validating at
    every caller and locks the fix for the next sibling.
    """
    inf_src = inspect.getsource(TASElementSegmenter._extract_segments)
    assert "isfinite" in inf_src, (
        "BUG: TASElementSegmenter._extract_segments must guard every "
        "`int(labels[...])` with `math.isfinite(labels[i])` (inference.py:85, "
        "88, 93). NaN label → int(NaN) → ValueError today."
    )
    metrics_src = inspect.getsource(_metrics_extract_segments)
    assert "isfinite" in metrics_src, (
        "BUG: tas.metrics._extract_segments must guard every "
        "`int(labels[...])` with `math.isfinite(labels[i])` (metrics.py:24, "
        "27, 30). NaN label → int(NaN) → ValueError today. GT CSV NaN "
        "crashes the metrics pipeline."
    )
