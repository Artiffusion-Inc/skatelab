"""Tests for ElementSegmenter — all public classes and methods, edge cases, logic branches."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.analysis.element_segmenter import ElementSegmenter
from src.types import ElementPhase, ElementSegment, H36Key, SegmentationResult
from src.utils.video import VideoMeta

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def video_meta() -> VideoMeta:
    """Standard video metadata for tests."""
    return VideoMeta(
        path=Path("test.mp4"),
        width=640,
        height=480,
        fps=30.0,
        num_frames=90,
    )


@pytest.fixture
def still_poses() -> np.ndarray:
    """Completely still poses — all keypoints at same position every frame."""
    return np.full((50, 17, 2), 0.4, dtype=np.float32)


@pytest.fixture
def active_poses() -> np.ndarray:
    """Poses with motion in every frame — sinusoidal wrist movement."""
    n = 60
    poses = np.zeros((n, 17, 2), dtype=np.float32)
    t = np.linspace(0, 1, n)
    for i in range(n):
        poses[i, H36Key.LWRIST, 0] = 0.3 * np.sin(2 * np.pi * t[i] * 3)
        poses[i, H36Key.RWRIST, 0] = -0.3 * np.sin(2 * np.pi * t[i] * 3)
        poses[i, H36Key.LWRIST, 1] = 0.2 * np.cos(2 * np.pi * t[i] * 3)
    return poses


@pytest.fixture
def mixed_poses() -> np.ndarray:
    """Poses with alternating active/still sections.

    - Frames  0-20: active (arm motion)
    - Frames 20-35: still
    - Frames 35-55: active (jump-like hip motion)
    - Frames 55-70: still
    - Frames 70-90: active (arm motion)
    """
    n = 90
    poses = np.zeros((n, 17, 2), dtype=np.float32)

    # Active: frames 0-20
    for i in range(0, 20):
        t = i / 20
        poses[i, H36Key.LWRIST, 0] = 0.25 * np.sin(2 * np.pi * t * 2)
        poses[i, H36Key.RWRIST, 0] = -0.25 * np.sin(2 * np.pi * t * 2)

    # Still: frames 20-35 — all zeros (no change)

    # Active: frames 35-55 — jump-like hip trajectory
    for i in range(35, 55):
        t = (i - 35) / 20
        poses[i, H36Key.LHIP, 1] = -0.15 * np.sin(t * np.pi)
        poses[i, H36Key.RHIP, 1] = -0.15 * np.sin(t * np.pi)

    # Still: frames 55-70

    # Active: frames 70-90
    for i in range(70, 90):
        t = (i - 70) / 20
        poses[i, H36Key.LWRIST, 0] = 0.2 * np.sin(2 * np.pi * t * 2)
        poses[i, H36Key.RWRIST, 0] = -0.2 * np.sin(2 * np.pi * t * 2)

    return poses


@pytest.fixture
def jump_poses_with_takeoff_landing() -> np.ndarray:
    """Poses that trigger has_jump_pattern=True in feature extraction.

    Hip Y derivative must cross -0.02 (takeoff) and +0.02 (landing).
    """
    n = 50
    poses = np.full((n, 17, 2), 0.5, dtype=np.float32)
    # Baseline hip Y = 0.5
    # Frames 10-15: rapid descent (hip Y drops fast → negative derivative)
    for i in range(10, 15):
        poses[i, H36Key.LHIP, 1] = 0.5 - 0.15 * (i - 10)
        poses[i, H36Key.RHIP, 1] = 0.5 - 0.15 * (i - 10)
    # Frames 15-25: at peak
    for i in range(15, 25):
        poses[i, H36Key.LHIP, 1] = 0.1
        poses[i, H36Key.RHIP, 1] = 0.1
    # Frames 25-30: rapid ascent (hip Y rises fast → positive derivative)
    for i in range(25, 30):
        poses[i, H36Key.LHIP, 1] = 0.1 + 0.15 * (i - 25)
        poses[i, H36Key.RHIP, 1] = 0.1 + 0.15 * (i - 25)
    # Rest at baseline
    return poses


# ---------------------------------------------------------------------------
# Test Initialization
# ---------------------------------------------------------------------------


class TestElementSegmenterInit:
    """Test constructor and attribute initialization."""

    def test_default_params(self):
        seg = ElementSegmenter()
        assert seg._stillness_threshold is None
        assert seg._min_still_duration == 0.5
        assert seg._min_segment_duration == 0.5
        assert seg._boundary_window == 10
        assert seg._tas_model_path is None
        assert seg._tas_classifier_path is None
        assert seg._tas_segmenter is None

    def test_custom_params(self):
        seg = ElementSegmenter(
            stillness_threshold=0.05,
            min_still_duration=1.0,
            min_segment_duration=2.0,
            boundary_window=5,
        )
        assert seg._stillness_threshold == 0.05
        assert seg._min_still_duration == 1.0
        assert seg._min_segment_duration == 2.0
        assert seg._boundary_window == 5

    def test_tas_paths_as_strings(self):
        seg = ElementSegmenter(
            tas_model_path="/tmp/model.pt",
            tas_classifier_path="/tmp/classifier.pkl",
        )
        assert isinstance(seg._tas_model_path, Path)
        assert isinstance(seg._tas_classifier_path, Path)
        assert seg._tas_model_path == Path("/tmp/model.pt")
        assert seg._tas_classifier_path == Path("/tmp/classifier.pkl")

    def test_tas_path_none_by_default(self):
        seg = ElementSegmenter()
        assert seg._tas_model_path is None
        assert seg._tas_classifier_path is None


# ---------------------------------------------------------------------------
# Test _get_tas_segmenter (lazy init)
# ---------------------------------------------------------------------------


class TestGetTasSegmenter:
    """Test lazy initialization of TAS segmenter."""

    def test_returns_none_when_no_path(self):
        seg = ElementSegmenter()
        assert seg._get_tas_segmenter() is None

    def test_returns_none_when_path_does_not_exist(self, tmp_path):
        nonexistent = tmp_path / "missing_model.pt"
        seg = ElementSegmenter(tas_model_path=str(nonexistent))
        assert seg._get_tas_segmenter() is None

    def test_caches_instance(self, tmp_path):
        """Lazy init should cache the TAS segmenter after first call."""
        model_path = tmp_path / "model.pt"
        model_path.touch()

        seg = ElementSegmenter(tas_model_path=str(model_path))

        with patch("src.tas.inference.TASElementSegmenter") as MockTAS:
            mock_instance = MagicMock()
            MockTAS.return_value = mock_instance

            result1 = seg._get_tas_segmenter()
            result2 = seg._get_tas_segmenter()

            # Should only construct once
            MockTAS.assert_called_once()
            assert result1 is result2
            assert seg._tas_segmenter is mock_instance

    def test_passes_classifier_path(self, tmp_path):
        """TAS segmenter should receive classifier_path."""
        model_path = tmp_path / "model.pt"
        classifier_path = tmp_path / "classifier.pkl"
        model_path.touch()
        classifier_path.touch()

        seg = ElementSegmenter(
            tas_model_path=str(model_path),
            tas_classifier_path=str(classifier_path),
        )

        with patch("src.tas.inference.TASElementSegmenter") as MockTAS:
            MockTAS.return_value = MagicMock()
            seg._get_tas_segmenter()
            MockTAS.assert_called_once_with(
                model_path=model_path,
                classifier_path=classifier_path,
                min_segment_duration=0.5,
            )


# ---------------------------------------------------------------------------
# Test _compute_motion_energy
# ---------------------------------------------------------------------------


class TestComputeMotionEnergy:
    """Test motion energy computation."""

    def test_output_shape(self, active_poses):
        seg = ElementSegmenter()
        energy = seg._compute_motion_energy(active_poses)
        assert energy.shape == (len(active_poses),)
        assert energy.dtype == np.float32

    def test_non_negative(self, active_poses):
        seg = ElementSegmenter()
        energy = seg._compute_motion_energy(active_poses)
        assert np.all(energy >= 0)

    def test_still_poses_near_zero(self, still_poses):
        seg = ElementSegmenter()
        energy = seg._compute_motion_energy(still_poses)
        # All poses identical → diff=0 → energy≈0 after smoothing
        assert np.max(energy) < 1e-4

    def test_single_frame(self):
        """Single-frame poses: np.diff produces empty, np.pad(mode='edge') fails.

        _compute_motion_energy uses np.pad(mode='edge') which cannot extend
        an axis of length 0 (the diff array). This is a known limitation.
        """
        poses = np.random.rand(1, 17, 2).astype(np.float32)
        seg = ElementSegmenter()
        with pytest.raises(ValueError, match="can't extend empty axis"):
            seg._compute_motion_energy(poses)

    def test_two_frames(self):
        """Two-frame poses should produce valid energy."""
        poses = np.random.rand(2, 17, 2).astype(np.float32)
        seg = ElementSegmenter()
        energy = seg._compute_motion_energy(poses)
        assert energy.shape == (2,)


# ---------------------------------------------------------------------------
# Test _detect_stillness
# ---------------------------------------------------------------------------


class TestDetectStillness:
    """Test stillness detection logic."""

    def test_adaptive_threshold(self):
        """With threshold=None, should use 25th percentile."""
        energy = np.concatenate([np.ones(20) * 0.5, np.zeros(10), np.ones(20) * 0.5]).astype(
            np.float32
        )
        seg = ElementSegmenter(stillness_threshold=None, min_still_duration=0.1)
        mask = seg._detect_stillness(energy, fps=30.0)
        assert mask.dtype == np.bool_
        assert mask.shape == energy.shape

    def test_explicit_threshold(self):
        """With explicit threshold, stillness = energy < threshold."""
        energy = np.array([0.01, 0.02, 0.5, 0.6, 0.01, 0.02], dtype=np.float32)
        seg = ElementSegmenter(stillness_threshold=0.1, min_still_duration=0.01)
        mask = seg._detect_stillness(energy, fps=30.0)
        # First two and last two frames should be still
        assert mask[0] and mask[1]
        assert not mask[2] and not mask[3]

    def test_morphological_opening_removes_short_stillness(self):
        """Short stillness periods should be removed by morphological opening.

        binary_opening removes short True (stillness) bursts, not short False
        (activity) gaps. A 2-frame stillness in a long active section should
        be removed when min_still_duration > 2/fps.
        """
        # Active section with a tiny 2-frame stillness in the middle
        energy = np.concatenate([np.ones(20) * 0.5, np.zeros(2), np.ones(20) * 0.5]).astype(
            np.float32
        )
        # min_still_duration=0.5 → 15 frames at 30fps → opening removes <15-frame stillness
        seg = ElementSegmenter(stillness_threshold=0.1, min_still_duration=0.5)
        mask = seg._detect_stillness(energy, fps=30.0)
        # The 2-frame stillness at frames 20-21 should be removed
        assert not mask[20]
        assert not mask[21]

    def test_all_active(self):
        """All-active signal should produce all-False mask."""
        energy = np.ones(30, dtype=np.float32) * 0.5
        seg = ElementSegmenter(stillness_threshold=0.1, min_still_duration=0.01)
        mask = seg._detect_stillness(energy, fps=30.0)
        assert not np.any(mask)

    def test_all_still(self):
        """All-still signal should produce all-True mask."""
        energy = np.zeros(30, dtype=np.float32)
        seg = ElementSegmenter(stillness_threshold=0.1, min_still_duration=0.01)
        mask = seg._detect_stillness(energy, fps=30.0)
        assert np.all(mask)

    def test_min_still_duration_filters_short_gaps(self):
        """Short stillness periods should be filtered out."""
        # 30fps, min_still_duration=0.5 → 15 frames minimum
        energy = np.array(
            [0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.5, 0.5],
            dtype=np.float32,
        )
        seg = ElementSegmenter(stillness_threshold=0.1, min_still_duration=0.5)
        mask = seg._detect_stillness(energy, fps=30.0)
        # Only 2 still frames at 30fps → 2/30=0.067s < 0.5s → filtered out
        assert not np.any(mask)


# ---------------------------------------------------------------------------
# Test _extract_active_segments
# ---------------------------------------------------------------------------


class TestExtractActiveSegments:
    """Test active segment extraction from stillness mask."""

    def test_empty_mask(self):
        """Empty mask should return no segments."""
        seg = ElementSegmenter()
        segments = seg._extract_active_segments(np.array([], dtype=bool))
        assert segments == []

    def test_all_still(self):
        """All-still mask should return no segments."""
        seg = ElementSegmenter()
        mask = np.ones(20, dtype=bool)
        segments = seg._extract_active_segments(mask)
        assert segments == []

    def test_all_active(self):
        """All-active mask (no stillness) is one maximal active run [0, n).

        A direct scan for runs of False (active) returns the whole video as a
        single half-open segment when the mask is entirely False. (The previous
        transition-based implementation dropped this case because it relied on
        still->active transitions that never occur when nothing is still.)
        """
        seg = ElementSegmenter()
        mask = np.zeros(30, dtype=bool)  # All False = all active
        segments = seg._extract_active_segments(mask)
        assert segments == [(0, 30)]

    def test_starts_active(self):
        """Video starts active, then goes still."""
        seg = ElementSegmenter()
        # F=F, F=F, T=T, T=T → starts active for 2 frames
        mask = np.array([False, False, True, True, True], dtype=bool)
        segments = seg._extract_active_segments(mask)
        assert len(segments) >= 1
        assert segments[0][0] == 0

    def test_ends_active(self):
        """Video that transitions from still to active at end.

        The 'ends with active' branch in _extract_active_segments triggers
        when starts[-1] > ends[-1] (a start without a matching end).
        """
        seg = ElementSegmenter()
        # Still → Active → Still → Active (ends active)
        mask = np.array(
            [True, True, False, False, True, True, False, False],
            dtype=bool,
        )
        segments = seg._extract_active_segments(mask)
        for start, end in segments:
            assert 0 <= start < end <= len(mask)

    def test_multiple_segments(self):
        """Multiple active/still alternations."""
        seg = ElementSegmenter()
        mask = np.array(
            [
                True,
                True,  # still
                False,
                False,
                False,  # active
                True,
                True,  # still
                False,
                False,  # active
                True,  # still
            ],
            dtype=bool,
        )
        segments = seg._extract_active_segments(mask)
        for start, end in segments:
            assert 0 <= start < end <= len(mask)


# --- prod-ready-audit repro (M6) -------------------------------------------
# RED-by-design: _extract_active_segments mis-pairs starts/ends via zip() when
# the video STARTS or ENDS with an active segment (len(starts) != len(ends)).
# The leading-active branch consumes ends[0]; the zip() loop then mis-pairs the
# remaining starts/ends; the `i+1 < len(starts)` guard skips valid pairs; the
# `starts[-1] > ends[-1]` end-check misses the trailing segment. Result: drops
# or misidentifies active segments. Existing tests above assert only
# 0 <= start < end <= len(mask) (validity), so the bug went undetected.
#
# These cases assert EXACT boundaries (and count) of the active runs (runs of
# False in the stillness mask). Today the function returns the wrong segments
# so these FAIL (RED). A correct implementation returns the runs of False.
# --------------------------------------------------------------------------


class TestExtractActiveSegmentsExactBoundariesM6:
    """Exact-boundary repro for the M6 zip() mis-pairing bug.

    Stillness mask convention: True = still, False = active. Active segments
    are maximal runs of False, returned as (start, end) half-open tuples.
    """

    @staticmethod
    def _normalize(segments):
        return [(int(s), int(e)) for s, e in segments]

    def test_starts_active_then_still_then_active_trailing_active(self):
        """mask=[F,F,T,T,F,F,T,T,T] -> active runs [0,2) and [4,6).

        Bug: leading-active branch consumes ends[0]=2 -> (0,2); the zip loop
        pairs starts[0]=4 with ends[0]=2 (already consumed, but zip restarts at
        index 0) and the `i+1 < len(starts)` guard (1 < 1 False) skips it; the
        trailing check `starts[-1]=4 > ends[-1]=6` is False so the [4,6) segment
        is dropped. Today returns [(0,2)].
        """
        seg = ElementSegmenter()
        mask = np.array([False, False, True, True, False, False, True, True, True], dtype=bool)
        segments = self._normalize(seg._extract_active_segments(mask))
        assert segments == [(0, 2), (4, 6)]

    def test_starts_active_three_active_runs(self):
        """mask=[F,F,T,T,F,F,T,T,F,F] -> active runs [0,2),[4,6),[8,10).

        Bug: leading-active -> (0,2); zip pairs starts=[4,8] with ends=[2,6]:
        i=0 (s=4,e=2): i+1=1 < 2 True and 4<2 False -> skip; i=1 (s=8,e=6):
        i+1=2 < 2 False -> skip; trailing check starts[-1]=8 > ends[-1]=6 True
        -> appends (8,10). Today returns [(0,2),(8,10)], dropping the middle
        [4,6) run.
        """
        seg = ElementSegmenter()
        mask = np.array(
            [False, False, True, True, False, False, True, True, False, False],
            dtype=bool,
        )
        segments = self._normalize(seg._extract_active_segments(mask))
        assert segments == [(0, 2), (4, 6), (8, 10)]

    def test_starts_still_ends_active(self):
        """mask=[T,T,F,F,T,T,F,F,T,T] -> active runs [2,4) and [6,8).

        Bug: no leading-active branch. zip pairs starts=[2,6] with ends=[4,8]:
        i=0 (s=2,e=4): i+1=1 < 2 True -> append (2,4); i=1 (s=6,e=8): i+1=2 < 2
        False -> skip; trailing check starts[-1]=6 > ends[-1]=8 False -> no
        append. Today returns [(2,4)], dropping the trailing [6,8) run.
        """
        seg = ElementSegmenter()
        mask = np.array(
            [True, True, False, False, True, True, False, False, True, True],
            dtype=bool,
        )
        segments = self._normalize(seg._extract_active_segments(mask))
        assert segments == [(2, 4), (6, 8)]


# ---------------------------------------------------------------------------
# Test _refine_boundaries
# ---------------------------------------------------------------------------


class TestRefineBoundaries:
    """Test boundary refinement logic."""

    def test_empty_segments(self):
        seg = ElementSegmenter()
        assert seg._refine_boundaries(np.zeros((10, 17, 2), dtype=np.float32), []) == []

    def test_refinement_preserves_count(self, active_poses):
        seg = ElementSegmenter()
        original = [(5, 15), (25, 40)]
        refined = seg._refine_boundaries(active_poses, original)
        assert len(refined) <= len(original)

    def test_refinement_produces_valid_segments(self, active_poses):
        seg = ElementSegmenter()
        original = [(5, 15), (25, 40)]
        refined = seg._refine_boundaries(active_poses, original)
        for start, end in refined:
            assert 0 <= start < end <= len(active_poses)

    def test_start_near_zero(self, active_poses):
        """Segment with start < boundary_window should handle gracefully."""
        seg = ElementSegmenter(boundary_window=10)
        original = [(2, 20)]
        refined = seg._refine_boundaries(active_poses, original)
        # Should not crash; start is clamped to 0 for search
        for start, _end in refined:
            assert start >= 0

    def test_end_near_max(self, active_poses):
        """Segment with end + boundary_window > len(poses)."""
        seg = ElementSegmenter(boundary_window=10)
        original = [(40, len(active_poses) - 2)]
        refined = seg._refine_boundaries(active_poses, original)
        for _start, end in refined:
            assert end <= len(active_poses)

    def test_single_frame_window_edge(self):
        """Very short poses with large boundary window."""
        poses = np.random.rand(5, 17, 2).astype(np.float32)
        seg = ElementSegmenter(boundary_window=10)
        original = [(1, 4)]
        refined = seg._refine_boundaries(poses, original)
        # Should not crash even though window exceeds array size
        for start, end in refined:
            assert 0 <= start < end <= len(poses)


# ---------------------------------------------------------------------------
# Test _classify_by_rules
# ---------------------------------------------------------------------------


class TestClassifyByRules:
    """Test rule-based classification decision tree."""

    def _make_seg(self) -> ElementSegmenter:
        return ElementSegmenter()

    def test_flip_high_rotation(self):
        """rotation_speed_max > 500 + jump pattern → flip."""
        etype, conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": True, "rotation_speed_max": 600}
        )
        assert etype == "flip"
        assert conf == 0.7

    def test_toe_loop_rotation(self):
        """350 < rotation_speed_max <= 500 + jump → toe_loop."""
        etype, _conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": True, "rotation_speed_max": 400}
        )
        assert etype == "toe_loop"

    def test_waltz_jump_moderate_rotation(self):
        """200 < rotation_speed_max <= 350 + jump → waltz_jump."""
        etype, conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": True, "rotation_speed_max": 250}
        )
        assert etype == "waltz_jump"
        assert conf == 0.65

    def test_waltz_jump_low_rotation(self):
        """100 < rotation_speed_max <= 200 + jump → waltz_jump (lower conf)."""
        etype, conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": True, "rotation_speed_max": 150}
        )
        assert etype == "waltz_jump"
        assert conf == 0.6

    def test_jump_pattern_rotation_below_100(self):
        """Jump pattern but rotation too low → falls through to edge/unknown."""
        etype, _conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": True, "rotation_speed_max": 50}
        )
        # rotation_speed_max=50 < 100 → doesn't match any jump rotation threshold
        # falls through to edge check, then unknown
        assert etype == "unknown"

    def test_three_turn_edge_changes(self):
        """Edge changes > 0 → three_turn."""
        etype, conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": False, "edge_change_count": 2}
        )
        assert etype == "three_turn"
        assert conf == 0.7

    def test_unknown_no_features(self):
        """No jump, no edge changes → unknown."""
        etype, conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": False, "edge_change_count": 0}
        )
        assert etype == "unknown"
        assert conf == 0.3

    def test_rotation_speed_as_bool_edge_case(self):
        """rotation_speed_max is bool → isinstance check should skip it."""
        # The code checks `not isinstance(rotation_max, bool)` before comparing
        etype, _conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": True, "rotation_speed_max": True}
        )
        # True is bool → all rotation checks skip → falls through
        # edge_change_count not set → defaults to 0 → unknown
        assert etype == "unknown"

    def test_edge_changes_as_bool_edge_case(self):
        """edge_change_count is bool → isinstance check should skip it."""
        etype, _conf = self._make_seg()._classify_by_rules(
            {"has_jump_pattern": False, "edge_change_count": True}
        )
        # True is bool → edge check skips → unknown
        assert etype == "unknown"

    def test_missing_keys_default(self):
        """Missing keys should use .get() defaults."""
        etype, conf = self._make_seg()._classify_by_rules({})
        assert etype == "unknown"
        assert conf == 0.3


# ---------------------------------------------------------------------------
# Test _extract_segment_features
# ---------------------------------------------------------------------------


class TestExtractSegmentFeatures:
    """Test feature extraction for a segment."""

    def test_basic_features(self, active_poses):
        seg = ElementSegmenter()
        features = seg._extract_segment_features(active_poses[:30], fps=30.0)
        assert features["duration_frames"] == 30
        assert features["duration_sec"] == 1.0
        assert features["motion_energy_mean"] >= 0

    def test_duration_calculation(self, active_poses):
        seg = ElementSegmenter()
        features = seg._extract_segment_features(active_poses[:15], fps=30.0)
        assert features["duration_frames"] == 15
        assert abs(features["duration_sec"] - 0.5) < 0.01

    def test_jump_pattern_detected(self, jump_poses_with_takeoff_landing):
        """Features should detect jump pattern when hip derivative crosses thresholds."""
        seg = ElementSegmenter()
        features = seg._extract_segment_features(jump_poses_with_takeoff_landing, fps=30.0)
        assert features["has_jump_pattern"] is True

    def test_no_jump_pattern_in_still(self, still_poses):
        seg = ElementSegmenter()
        features = seg._extract_segment_features(still_poses[:30], fps=30.0)
        assert features["has_jump_pattern"] is False

    def test_knee_angles_with_missing_data(self):
        """All-zero joints should produce knee_angle=0 (skipped)."""
        poses = np.zeros((10, 17, 2), dtype=np.float32)
        seg = ElementSegmenter()
        features = seg._extract_segment_features(poses, fps=30.0)
        assert features["knee_angle_min"] == 0.0
        assert features["knee_angle_max"] == 0.0
        assert features["knee_angle_range"] == 0.0

    def test_shoulder_rotation_short_segment(self):
        """Two-frame segment should produce valid features (single-frame crashes due to np.pad)."""
        poses = np.random.rand(2, 17, 2).astype(np.float32)
        seg = ElementSegmenter()
        features = seg._extract_segment_features(poses, fps=30.0)
        assert "rotation_speed_max" in features
        assert "rotation_speed_mean" in features

    def test_edge_indicator_features(self, active_poses):
        seg = ElementSegmenter()
        features = seg._extract_segment_features(active_poses[:30], fps=30.0)
        assert "edge_change_count" in features
        assert "edge_indicator_mean" in features


# ---------------------------------------------------------------------------
# Test _compute_edge_indicator
# ---------------------------------------------------------------------------


class TestComputeEdgeIndicator:
    """Test edge indicator computation."""

    def test_output_shape(self, active_poses):
        seg = ElementSegmenter()
        edge = seg._compute_edge_indicator(active_poses)
        assert edge.shape == (len(active_poses),)
        assert edge.dtype == np.float32

    def test_values_bounded(self, active_poses):
        seg = ElementSegmenter()
        edge = seg._compute_edge_indicator(active_poses)
        assert np.all(np.abs(edge) <= 1.0 + 1e-6)

    def test_still_poses_constant(self, still_poses):
        """Still poses → zero foot velocity → edge indicator = 0."""
        seg = ElementSegmenter()
        edge = seg._compute_edge_indicator(still_poses)
        assert np.allclose(edge, 0.0)


# ---------------------------------------------------------------------------
# Test _compute_shoulder_rotation
# ---------------------------------------------------------------------------


class TestComputeShoulderRotation:
    """Test shoulder rotation angle computation."""

    def test_output_shape(self, active_poses):
        seg = ElementSegmenter()
        angles = seg._compute_shoulder_rotation(active_poses)
        assert angles.shape == (len(active_poses),)
        assert angles.dtype == np.float32

    def test_angles_in_radians(self, active_poses):
        seg = ElementSegmenter()
        angles = seg._compute_shoulder_rotation(active_poses)
        assert np.all(angles >= -np.pi - 1e-6)
        assert np.all(angles <= np.pi + 1e-6)

    def test_horizontal_shoulders(self):
        """Perfectly horizontal shoulders should give angle ≈ 0."""
        poses = np.zeros((5, 17, 2), dtype=np.float32)
        poses[:, H36Key.LSHOULDER, :] = [-0.15, 0.3]
        poses[:, H36Key.RSHOULDER, :] = [0.15, 0.3]
        seg = ElementSegmenter()
        angles = seg._compute_shoulder_rotation(poses)
        assert np.allclose(angles, 0.0, atol=0.01)


# ---------------------------------------------------------------------------
# Test _compute_knee_angle_series
# ---------------------------------------------------------------------------


class TestComputeKneeAngleSeries:
    """Test knee angle series computation."""

    def test_left_side(self, active_poses):
        seg = ElementSegmenter()
        angles = seg._compute_knee_angle_series(active_poses, side="left")
        assert angles.shape == (len(active_poses),)
        assert angles.dtype == np.float32

    def test_right_side(self, active_poses):
        seg = ElementSegmenter()
        angles = seg._compute_knee_angle_series(active_poses, side="right")
        assert angles.shape == (len(active_poses),)
        assert angles.dtype == np.float32

    def test_missing_joints_produce_zero(self):
        """All-zero hip/knee/ankle should yield angle=0 (skipped)."""
        poses = np.zeros((5, 17, 2), dtype=np.float32)
        seg = ElementSegmenter()
        angles = seg._compute_knee_angle_series(poses, side="left")
        assert np.allclose(angles, 0.0)

    def test_partial_missing_data(self):
        """Some frames with missing data, some with valid data."""
        poses = np.random.rand(10, 17, 2).astype(np.float32) * 0.5 + 0.25
        # Make frames 3 and 7 have all-zero joints
        poses[3, :, :] = 0.0
        poses[7, :, :] = 0.0
        seg = ElementSegmenter()
        angles = seg._compute_knee_angle_series(poses, side="left")
        # Frames 3 and 7 should be 0.0 (missing data), others should be > 0
        assert angles[3] == 0.0
        assert angles[7] == 0.0
        # Most other frames should have valid angles
        valid = [a for i, a in enumerate(angles) if i not in (3, 7)]
        assert any(a > 0 for a in valid)


# ---------------------------------------------------------------------------
# Test _compute_overall_confidence
# ---------------------------------------------------------------------------


class TestComputeOverallConfidence:
    """Test overall confidence aggregation."""

    def test_empty_list(self):
        seg = ElementSegmenter()
        assert seg._compute_overall_confidence([]) == 0.0

    def test_single_segment(self):
        seg = ElementSegmenter()
        s = ElementSegment(element_type="waltz_jump", start=0, end=10, confidence=0.8)
        assert seg._compute_overall_confidence([s]) == 0.8

    def test_multiple_segments_averaged(self):
        seg = ElementSegmenter()
        s1 = ElementSegment(element_type="flip", start=0, end=10, confidence=0.9)
        s2 = ElementSegment(element_type="waltz_jump", start=20, end=30, confidence=0.5)
        assert seg._compute_overall_confidence([s1, s2]) == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Test _detect_segment_phases
# ---------------------------------------------------------------------------


class TestDetectSegmentPhases:
    """Test phase detection integration."""

    def test_adjusts_global_start(self):
        """Phase indices should be offset by global_start."""
        poses = np.random.rand(30, 17, 2).astype(np.float32)
        seg = ElementSegmenter()

        mock_phases = ElementPhase(
            name="waltz_jump", start=0, takeoff=5, peak=10, landing=15, end=20
        )
        mock_result = MagicMock()
        mock_result.phases = mock_phases

        with patch("src.analysis.phase_detector.PhaseDetector") as MockPD:
            MockPD.return_value.detect_phases.return_value = mock_result

            result = seg._detect_segment_phases(poses, 30.0, "waltz_jump", global_start=100)

            assert result is not None
            assert result.start == 100
            assert result.takeoff == 105
            assert result.peak == 110
            assert result.landing == 115
            assert result.end == 120

    def test_zero_takeoff_unchanged(self):
        """If takeoff=0, it should stay 0 (not offset by global_start)."""
        poses = np.random.rand(30, 17, 2).astype(np.float32)
        seg = ElementSegmenter()

        mock_phases = ElementPhase(name="three_turn", start=0, takeoff=0, peak=0, landing=0, end=15)
        mock_result = MagicMock()
        mock_result.phases = mock_phases

        with patch("src.analysis.phase_detector.PhaseDetector") as MockPD:
            MockPD.return_value.detect_phases.return_value = mock_result

            result = seg._detect_segment_phases(poses, 30.0, "three_turn", global_start=50)

            assert result is not None
            assert result.takeoff == 0
            assert result.peak == 0
            assert result.landing == 0
            assert result.start == 50
            assert result.end == 65


# ---------------------------------------------------------------------------
# Test _segment_with_tas
# ---------------------------------------------------------------------------


class TestSegmentWithTas:
    """Test TAS ML segmentation wrapper."""

    def test_wraps_tas_results(self, video_meta):
        poses = np.random.rand(30, 17, 2).astype(np.float32)
        seg = ElementSegmenter()

        mock_tas = MagicMock()
        mock_tas.segment.return_value = [
            {"element_type": "flip", "start": 0, "end": 15, "confidence": 0.85},
            {"element_type": "waltz_jump", "start": 16, "end": 30, "confidence": 0.55},
        ]

        result = seg._segment_with_tas(mock_tas, poses, Path("test.mp4"), video_meta)

        assert isinstance(result, SegmentationResult)
        assert result.method == "tas_ml"
        assert len(result.segments) == 2
        assert result.segments[0].element_type == "flip"
        assert result.segments[1].element_type == "waltz_jump"
        assert result.confidence == pytest.approx(0.7)

    def test_empty_tas_results(self, video_meta):
        poses = np.random.rand(30, 17, 2).astype(np.float32)
        seg = ElementSegmenter()

        mock_tas = MagicMock()
        mock_tas.segment.return_value = []

        result = seg._segment_with_tas(mock_tas, poses, Path("test.mp4"), video_meta)

        assert isinstance(result, SegmentationResult)
        assert result.segments == []
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Test segment() (full pipeline)
# ---------------------------------------------------------------------------


class TestSegment:
    """Test full segmentation pipeline."""

    def test_adaptive_method(self, mixed_poses, video_meta):
        seg = ElementSegmenter(
            stillness_threshold=0.01,
            min_still_duration=0.2,
            min_segment_duration=0.2,
        )
        result = seg.segment(mixed_poses, Path("test.mp4"), video_meta, method="adaptive")
        assert isinstance(result, SegmentationResult)
        assert result.method == "adaptive"
        assert 0 <= result.confidence <= 1

    def test_motion_energy_method(self, mixed_poses, video_meta):
        seg = ElementSegmenter(
            stillness_threshold=0.01,
            min_still_duration=0.2,
            min_segment_duration=0.2,
        )
        result = seg.segment(mixed_poses, Path("test.mp4"), video_meta, method="motion_energy")
        assert isinstance(result, SegmentationResult)
        assert result.method == "motion_energy"

    def test_tas_ml_fallback_when_no_model(self, mixed_poses, video_meta):
        """method='tas_ml' but no model path → falls back to default pipeline."""
        seg = ElementSegmenter()
        result = seg.segment(mixed_poses, Path("test.mp4"), video_meta, method="tas_ml")
        # Should fall through to default pipeline (not crash)
        assert isinstance(result, SegmentationResult)

    def test_tas_ml_with_model(self, mixed_poses, video_meta, tmp_path):
        """method='tas_ml' with model → should call _segment_with_tas."""
        model_path = tmp_path / "model.pt"
        model_path.touch()
        seg = ElementSegmenter(tas_model_path=str(model_path))

        mock_tas = MagicMock()
        mock_tas.segment.return_value = [
            {"element_type": "flip", "start": 0, "end": 45, "confidence": 0.8},
        ]

        with patch.object(seg, "_get_tas_segmenter", return_value=mock_tas):
            result = seg.segment(mixed_poses, Path("test.mp4"), video_meta, method="tas_ml")
            assert isinstance(result, SegmentationResult)
            assert result.method == "tas_ml"
            assert len(result.segments) == 1

    def test_still_video_no_segments(self, still_poses, video_meta):
        seg = ElementSegmenter()
        result = seg.segment(still_poses, Path("test.mp4"), video_meta)
        assert isinstance(result, SegmentationResult)
        assert len(result.segments) == 0
        assert result.confidence == 0.0

    def test_segment_boundaries_valid(self, mixed_poses, video_meta):
        seg = ElementSegmenter(
            stillness_threshold=0.005,
            min_still_duration=0.2,
            min_segment_duration=0.1,
        )
        result = seg.segment(mixed_poses, Path("test.mp4"), video_meta)
        for s in result.segments:
            assert 0 <= s.start < s.end <= len(mixed_poses)
            assert s.confidence >= 0
            assert s.confidence <= 1

    def test_short_segments_filtered(self, video_meta):
        """Very short active bursts should be filtered by min_segment_duration."""
        # 30fps, min_segment_duration=0.5 → need >= 15 frames
        poses = np.zeros((100, 17, 2), dtype=np.float32)
        # 5-frame active burst (too short)
        for i in range(45, 50):
            poses[i, H36Key.LWRIST, 0] = 0.5
        # 30-frame active section (long enough)
        for i in range(60, 90):
            t = (i - 60) / 30
            poses[i, H36Key.LWRIST, 0] = 0.3 * np.sin(2 * np.pi * t * 2)

        seg = ElementSegmenter(
            stillness_threshold=0.01,
            min_still_duration=0.2,
            min_segment_duration=0.5,
        )
        result = seg.segment(poses, Path("test.mp4"), video_meta)
        # The 5-frame burst should be filtered out
        for s in result.segments:
            assert s.duration_frames >= 15


# ---------------------------------------------------------------------------
# Test _classify_segments (integration with _extract_segment_features + _classify_by_rules)
# ---------------------------------------------------------------------------


class TestClassifySegments:
    """Test segment classification pipeline."""

    def test_classifies_jump_segment(self, jump_poses_with_takeoff_landing):
        """Jump-like poses should be classified as a jump type."""
        seg = ElementSegmenter()
        # Use the full jump poses as a single segment
        segments = [(0, len(jump_poses_with_takeoff_landing))]
        result = seg._classify_segments(jump_poses_with_takeoff_landing, segments, fps=30.0)
        assert len(result) == 1
        assert result[0].element_type in ("flip", "toe_loop", "waltz_jump", "unknown")
        assert result[0].metadata is not None

    def test_metadata_populated(self, active_poses):
        seg = ElementSegmenter()
        segments = [(0, 20)]
        result = seg._classify_segments(active_poses, segments, fps=30.0)
        assert len(result) == 1
        assert "duration_sec" in result[0].metadata
        assert "motion_energy_mean" in result[0].metadata
