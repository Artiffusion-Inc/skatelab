"""RED repro — DeepSORTTracker.update all-NaN person → NaN bbox + warning spam (#967).

Bug: `DeepSORTTracker.update` (ml/src/tracking/deepsort_tracker.py:104-124)
computes a per-person bbox via `np.nanmin`/`np.nanmax` over keypoints and
`np.nanmean` over scores. For a person whose keypoints are ALL NaN (full
occlusion / detector glitch), `nanmin(all-NaN)` returns NaN AND emits a
`RuntimeWarning: All-NaN slice encountered` (×4 per all-NaN person per frame).
The resulting `([nan,nan,nan,nan], nan, "person")` detection is fed to
DeepSORT's `update_tracks` with no guard → NaN-anchored phantom track /
Kalman corruption / log flooding.

Fix direction (do NOT apply here): guard the bbox computation with an
`np.isfinite(...).any()` per-person check BEFORE `nanmin`/`nanmax` — skip
the all-NaN person (or sentinel bbox + NaN score so DeepSORT rejects it).
Mirror the `not np.isfinite(...) or ...` pattern already used in
`_track_validator.py:44,52`.

This test MUST fail (RED) against the current code on the warning + bbox
observables; the source-guard test fails until the guard is added.
"""

import inspect
import warnings

import numpy as np
import pytest

try:
    import deep_sort_realtime  # type: ignore[import-not-found]  # noqa: F401

    _DEEPSORT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DEEPSORT_AVAILABLE = False

from src.tracking.deepsort_tracker import DeepSORTTracker

pytestmark = pytest.mark.skipif(
    not _DEEPSORT_AVAILABLE,
    reason="deep-sort-realtime not installed",
)


def _finite_person(cx: float, cy: float) -> np.ndarray:
    """One finite H3.6M-ish pose (17, 2) normalized coords."""
    kps = np.full((17, 2), cx, dtype=np.float32)
    kps[:, 1] = cy
    kps[0] = [cx, cy]  # hip
    kps[9] = [cx, cy + 0.4]  # foot
    kps[15] = [cx, cy - 0.35]  # head
    return kps


def _all_nan_person() -> np.ndarray:
    return np.full((17, 2), np.nan, dtype=np.float32)


def _update(tracker: DeepSORTTracker, kps: np.ndarray, scores: np.ndarray) -> list:
    """Run update with a dummy BGR frame (DeepSORT needs frame or embeddings)."""
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # pkg_resources deprecation
        return tracker.update(kps, scores, frame=frame, frame_width=100, frame_height=100)


def _bbox_compute_source() -> str:
    """Source of DeepSORTTracker.update (bbox-compute site lives there)."""
    return inspect.getsource(DeepSORTTracker.update)


def test_bbox_compute_source_has_isfinite_guard() -> None:
    """Root-cause lock: the bbox-compute path must guard all-NaN persons
    with an `np.isfinite(...).any()` (or equivalent) check before calling
    `nanmin`/`nanmax`/`nanmean`."""
    src = _bbox_compute_source()
    assert "nanmin" in src and "nanmax" in src, "bbox compute via nanmin/nanmax present"
    assert "isfinite" in src or "isnan" in src or ".any()" in src, (
        "all-NaN guard (isfinite/isnan/.any()) must be present at bbox-compute site"
    )


def test_all_nan_person_no_all_nan_slice_warning() -> None:
    """An all-NaN person must NOT emit `All-NaN slice encountered` warnings."""
    tracker = DeepSORTTracker(embedder_gpu=False)
    kps = np.array([_all_nan_person()], dtype=np.float32)
    scores = np.full((1, 17), np.nan, dtype=np.float32)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("error", RuntimeWarning)
        # pkg_resources UserWarning is unrelated — leave default for it.
        _update(tracker, kps, scores)
    nan_slice = [w for w in caught if "All-NaN slice" in str(w.message)]
    assert not nan_slice, (
        f"expected no 'All-NaN slice' warnings, got {len(nan_slice)}: "
        f"{[str(w.message) for w in nan_slice]}"
    )


def test_all_nan_person_bbox_finite_or_skipped() -> None:
    """The all-NaN person must NOT yield a NaN bbox fed to DeepSORT — either
    the person is skipped (no detection) or its bbox is finite (sentinel)."""
    tracker = DeepSORTTracker(embedder_gpu=False)
    kps = np.array([_all_nan_person()], dtype=np.float32)
    scores = np.full((1, 17), np.nan, dtype=np.float32)
    # Capture the detections list handed to update_tracks by intercepting.
    det_captures: list = []
    orig = tracker._tracker  # noqa: SLF001 — lazy-init'd by _ensure_tracker
    # Force eager init so we can wrap update_tracks.
    tracker._ensure_tracker()  # noqa: SLF001
    real_update_tracks = tracker._tracker.update_tracks  # noqa: SLF001

    def _spy(detections, *args, **kwargs):  # type: ignore[no-untyped-def]
        det_captures.append(detections)
        return real_update_tracks(detections, *args, **kwargs)

    tracker._tracker.update_tracks = _spy  # type: ignore[method-assign]  # noqa: SLF001
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            warnings.simplefilter("ignore", UserWarning)
            _update(tracker, kps, scores)
    finally:
        tracker._tracker.update_tracks = real_update_tracks  # type: ignore[method-assign]  # noqa: SLF001
    # Skipping the all-NaN person entirely is acceptable (no update_tracks call);
    # if update_tracks WAS called, no NaN bbox may leak through.
    if not det_captures:
        return
    dets = det_captures[-1]
    for bbox, score, _label in dets:
        bbox_arr = np.asarray(bbox, dtype=np.float64)
        assert np.isfinite(bbox_arr).all(), f"NaN bbox leaked to DeepSORT: {bbox} (score={score})"


def test_all_finite_persons_bbox_unchanged() -> None:
    """Regression: all-finite persons get a normal finite bbox (padding applied)."""
    tracker = DeepSORTTracker(embedder_gpu=False)
    kps = np.array([_finite_person(0.3, 0.5), _finite_person(0.7, 0.5)], dtype=np.float32)
    scores = np.full((2, 17), 0.8, dtype=np.float32)
    tracker._ensure_tracker()  # noqa: SLF001
    det_captures: list = []
    real_update_tracks = tracker._tracker.update_tracks  # noqa: SLF001

    def _spy(detections, *args, **kwargs):  # type: ignore[no-untyped-def]
        det_captures.append(detections)
        return real_update_tracks(detections, *args, **kwargs)

    tracker._tracker.update_tracks = _spy  # type: ignore[method-assign]  # noqa: SLF001
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            _update(tracker, kps, scores)
    finally:
        tracker._tracker.update_tracks = real_update_tracks  # type: ignore[method-assign]  # noqa: SLF001
    dets = det_captures[-1]
    assert len(dets) == 2
    for bbox, score, _label in dets:
        bbox_arr = np.asarray(bbox, dtype=np.float64)
        assert np.isfinite(bbox_arr).all(), f"finite person got non-finite bbox {bbox}"
        assert np.isfinite(score) and score > 0.0


def test_mixed_batch_finite_unaffected_nan_guarded() -> None:
    """Mixed batch (one finite + one all-NaN): finite track unaffected, NaN
    track guarded (no NaN bbox, no All-NaN slice warning)."""
    tracker = DeepSORTTracker(embedder_gpu=False)
    finite = _finite_person(0.4, 0.5)
    nan_person = _all_nan_person()
    kps = np.array([finite, nan_person], dtype=np.float32)
    scores = np.array(
        [np.full(17, 0.8, np.float32), np.full(17, np.nan, np.float32)],
        dtype=np.float32,
    )
    tracker._ensure_tracker()  # noqa: SLF001
    det_captures: list = []
    real_update_tracks = tracker._tracker.update_tracks  # noqa: SLF001

    def _spy(detections, *args, **kwargs):  # type: ignore[no-untyped-def]
        det_captures.append(detections)
        return real_update_tracks(detections, *args, **kwargs)

    tracker._tracker.update_tracks = _spy  # type: ignore[method-assign]  # noqa: SLF001
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("ignore", UserWarning)
            _update(tracker, kps, scores)
    finally:
        tracker._tracker.update_tracks = real_update_tracks  # type: ignore[method-assign]  # noqa: SLF001
    nan_slice = [w for w in caught if "All-NaN slice" in str(w.message)]
    assert not nan_slice, f"mixed batch leaked All-NaN warning: {len(nan_slice)}"
    dets = det_captures[-1]
    for bbox, _score, _label in dets:
        bbox_arr = np.asarray(bbox, dtype=np.float64)
        assert np.isfinite(bbox_arr).all(), f"mixed batch NaN bbox leaked: {bbox}"
