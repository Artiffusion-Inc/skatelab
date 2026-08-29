"""RED repro — TAS element segmenter fps=0 ZeroDivisionError.

Two crash sites, no `fps > 0` guard:

1. `TASElementSegmenter._try_add_segment` (ml/src/tas/inference.py:114):
   `duration = (end - start) / fps` — Python scalar `int / 0.0` →
   ZeroDivisionError at the TOP of the method, BEFORE the duration filter
   (line 116) and before `extract_segment_features` (line 123).
2. `extract_segment_features` (ml/src/tas/classifier.py:25):
   `duration = T / fps` — same `int / 0.0` → ZeroDivisionError. Runs BEFORE
   the `if T < 2` single-frame guard (line 36). Also line 53
   `np.gradient(angles) * fps` → `* 0.0` → rot_speed=0.0 (not a crash but
   semantically wrong: rotation speed cannot be measured without fps).

Corrupt / truncated / re-encoded video reports `cv2.CAP_PROP_FPS = 0`
(documented OpenCV sentinel for missing/unreadable framerate metadata).
`meta.fps = 0.0` flows from gpu_server (server.py:468
`_tas_segmenter.segment(poses, fps=prepared.meta.fps)`) into
`_extract_segments` → `_try_add_segment(..., fps=0.0)` → `(end-start)/0.0`
→ ZeroDivisionError. TAS runs concurrently with biomechanics
(`asyncio.to_thread`), so the element timeline is lost or the worker job
crashes — pose estimation / phase detection / smoothing / biomechanics all
succeeded.

Sibling consistency (#499 fps=0 family): the RULE-BASED element segmenter
sibling (#505) already guards `num_frames / fps if fps > 0 else 0.0`
(element_segmenter.py:458). The TAS ML segmenter is the sibling that
missed the guard — same input, sibling path, inconsistent guard. 8 other
siblings already guard fps=0 (VideoMeta.duration_sec, ElementPhase.
airtime_sec, phase_detector:234, physics_engine 3D #937 + 2D #939, pose
tracker #952, smoothing #948).

The fix (NOT applied — repro only): per-division guard, mirroring #505:
  - inference.py:114: `duration = (end - start) / fps if fps > 0 else 0.0`
    → duration=0.0 → min-duration filter drops the segment (correct: no
    meaningful duration without a framerate).
  - classifier.py:25: `duration = T / fps if fps > 0 else 0.0`.
  - classifier.py:53: guard `rot_speed` so fps=0 → 0.0 (not `* 0.0`).
Per-division is the smallest diff and matches the #505 sibling pattern
exactly (root-cause fix at the divide site, covers every caller routing
through `_try_add_segment` / `extract_segment_features`).

The correct contract: `TASElementSegmenter.segment(poses, fps=0.0)` and
`extract_segment_features(poses, fps=0.0)` with finite poses must NOT
raise ZeroDivisionError — must return a finite duration (0.0) and drop
the segment via the min-duration filter (inference) / report finite
features (classifier). NOT crash the element timeline.

RED now: the observable assertions below describe the CORRECT behavior —
fps=0 no crash, finite duration 0.0, segments dropped. They FAIL because
`(end-start)/0.0` raises. The source-check confirms the `if fps > 0`
guard is present at both divide sites (root cause locked).

Pure-Python (no GPU, no DB): `_try_add_segment` and
`extract_segment_features` are pure-data functions. The ONNX model in
`segment` needs the model file, but `_try_add_segment` /
`extract_segment_features` are testable directly without it.
"""

import inspect

import numpy as np

from src.tas.classifier import extract_segment_features
from src.tas.inference import TASElementSegmenter


def _seg_poses(n: int = 30) -> np.ndarray:
    """A (n, 17, 2) normalized pose sequence — finite, varied enough that
    `extract_segment_features` does not short-circuit. n=30 so duration
    at fps=30 is 1.0s (passes any reasonable min-duration filter).
    """
    rng = np.random.default_rng(0)
    return rng.standard_normal((n, 17, 2)).astype(np.float32)


# --------------------------------------------------------------------------- #
# Observable 1: `extract_segment_features(fps=0.0)` — no crash, finite
# duration 0.0, finite features.
# --------------------------------------------------------------------------- #


def test_extract_segment_features_fps_zero_no_crash_repro():
    """CORRECT behavior: `extract_segment_features(poses, fps=0.0)` must
    return a features dict with finite `duration=0.0` and finite
    `rotation_speed`, NOT raise ZeroDivisionError.

    RED now: `T / 0.0` (classifier.py:25) raises ZeroDivisionError before
    any feature is computed. After the fix: `T / fps if fps > 0 else 0.0`
    → duration=0.0; rotation_speed guarded → 0.0.
    """
    feats = extract_segment_features(_seg_poses(), fps=0.0)
    assert isinstance(feats, dict), (
        f"BUG: extract_segment_features(fps=0.0) did not return a dict "
        f"(got {type(feats).__name__}: {feats!r})."
    )
    assert np.isfinite(feats["duration"]), (
        f"BUG: extract_segment_features(fps=0.0) leaked non-finite "
        f"duration={feats['duration']!r}. T/fps ZeroDivisionError today; "
        f"guard must yield 0.0 (mirror #505 sibling)."
    )
    assert feats["duration"] == 0.0, (
        f"BUG: fps=0 duration should be 0.0 (no meaningful duration), got {feats['duration']!r}."
    )
    assert np.isfinite(feats["rotation_speed"]), (
        f"BUG: extract_segment_features(fps=0.0) leaked non-finite "
        f"rotation_speed={feats['rotation_speed']!r}. np.gradient*fps at "
        f"fps=0 → 0.0 (not crash), but guard for consistency with duration."
    )


# --------------------------------------------------------------------------- #
# Observable 2: `_try_add_segment(fps=0.0)` — no crash, returns None
# (duration 0.0 < min-duration → dropped). Element timeline not killed.
# --------------------------------------------------------------------------- #


def test_try_add_segment_fps_zero_no_crash_drops_repro():
    """CORRECT behavior: `_try_add_segment(label=1, start=0, end=30,
    poses, fps=0.0)` must NOT raise ZeroDivisionError. With duration=0.0
    the min-duration filter (line 116) drops the segment → return None.
    The element timeline degrades to "no segments" (correct: no
    meaningful duration without a framerate), NOT a worker crash.

    RED now: `(end - start) / 0.0` (inference.py:114) raises
    ZeroDivisionError. After the fix: `... if fps > 0 else 0.0` →
    duration=0.0 < min_dur → return None.

    Uses a real TASElementSegmenter instance. The ONNX model load is
    skipped by constructing via __new__ (no model file needed — only
    `_try_add_segment` + `id2label` + `min_segment_duration` are touched).
    """
    seg = TASElementSegmenter.__new__(TASElementSegmenter)
    seg.id2label = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}
    seg.min_segment_duration = 0.3
    seg.classifier = None  # skip RF classifier (no model file)

    # Jump segment, 30 frames. fps=0 → duration 0.0 → dropped (None).
    result = seg._try_add_segment(1, 0, 30, _seg_poses(30), fps=0.0)

    assert result is None, (
        f"BUG: _try_add_segment(fps=0.0) returned {result!r}, expected None "
        f"(duration 0.0 < min-duration → dropped). Must not raise "
        f"ZeroDivisionError either — (end-start)/fps at fps=0 crashes today."
    )


# --------------------------------------------------------------------------- #
# Observable 3: `_try_add_segment` with fps=0 + classifier attached — the
# classifier path (extract_segment_features) must also not crash. Locks
# that the guard at line 114 is reached BEFORE the classifier call (line
# 123) is skipped (duration=0.0 drops before it). Regression: a fix that
# only guards the classifier but not line 114 still crashes here.
# --------------------------------------------------------------------------- #


def test_try_add_segment_fps_zero_classifier_path_not_reached_repro():
    """CORRECT behavior: with `duration=0.0` (fps=0), the min-duration
    filter drops the segment BEFORE `extract_segment_features` is called,
    so the classifier path is never reached. A dummy classifier that
    raises if called confirms it was NOT called.

    RED now: line 114 raises before the filter, so this never gets to
    test the classifier path — it crashes at the division. After the fix:
    duration=0.0 → filter returns None → classifier never called.
    """
    seg = TASElementSegmenter.__new__(TASElementSegmenter)
    seg.id2label = {0: "None", 1: "Jump", 2: "Spin", 3: "Step"}
    seg.min_segment_duration = 0.3

    class _Boom:
        def predict(self, _features):  # noqa: ANN001
            raise AssertionError(
                "classifier.predict must NOT be called when fps=0 — "
                "duration=0.0 must drop the segment before the classifier."
            )

    seg.classifier = _Boom()
    result = seg._try_add_segment(1, 0, 30, _seg_poses(30), fps=0.0)
    assert result is None, (
        f"BUG: fps=0 segment should be dropped (None) before the classifier, got {result!r}."
    )


# --------------------------------------------------------------------------- #
# Regression guard: valid fps unchanged — fps=30 features finite nonzero,
# segment passes the filter.
# --------------------------------------------------------------------------- #


def test_extract_segment_features_valid_fps_unchanged_repro():
    """Regression guard: fps=30 must still report finite `duration` = T/30.
    The fps>0 guard must not change the valid-fps case. PASSES today; locks
    the contract so the guard cannot regress the normal path.
    """
    poses = _seg_poses(30)
    feats = extract_segment_features(poses, fps=30.0)
    assert np.isfinite(feats["duration"]) and feats["duration"] > 0.0, (
        f"BUG (regression): fps=30 duration should be ~1.0, got "
        f"{feats['duration']!r}. The fps>0 guard must not change valid fps."
    )


# --------------------------------------------------------------------------- #
# Source check: root cause locked — `if fps > 0` guard at both divide sites.
# --------------------------------------------------------------------------- #


def test_tas_fps_zero_guard_source_repro():
    """GREEN contract source check: the fps=0 crash is fixed by a
    per-division `if fps > 0 else 0.0` guard at BOTH divide sites,
    mirroring the #505 rule-based sibling (element_segmenter.py:458).
    """
    inf_src = inspect.getsource(TASElementSegmenter._try_add_segment)
    assert "fps > 0" in inf_src, (
        "BUG: _try_add_segment must guard `(end - start) / fps if fps > 0 "
        "else 0.0` (inference.py:114). Corrupt video fps=0 → "
        "ZeroDivisionError today. Mirror #505 sibling."
    )
    clf_src = inspect.getsource(extract_segment_features)
    assert "fps > 0" in clf_src, (
        "BUG: extract_segment_features must guard `T / fps if fps > 0 else "
        "0.0` (classifier.py:25). Same fps=0 crash as _try_add_segment."
    )
