"""Tests for COCO-style HALPE26 dataset builder utilities."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.datasets.coco_builder import (
    DEFAULT_CATEGORY,
    HALPE26_KEYPOINT_NAMES,
    HALPE26_SKELETON,
    build_coco_json,
    format_keypoints,
    merge_coco_foot_keypoints,
    save_coco_json,
)


class TestMergeCocoFootKeypoints:
    """Tests for merge_coco_foot_keypoints function."""

    def test_valid_merge_shapes(self):
        """Should return correct shapes for valid inputs."""
        coco_2d = np.ones((17, 2), dtype=np.float64)
        foot_2d = np.ones((6, 2), dtype=np.float32)

        pts, vis = merge_coco_foot_keypoints(coco_2d, foot_2d)

        assert pts.shape == (26, 2)
        assert vis.shape == (26,)
        assert pts.dtype == np.float32
        assert vis.dtype == np.float32

    def test_valid_merge_values(self):
        """Should copy COCO and foot keypoints correctly."""
        coco_2d = np.arange(34, dtype=np.float64).reshape(17, 2)
        foot_2d = np.arange(12, dtype=np.float32).reshape(6, 2) + 100

        pts, vis = merge_coco_foot_keypoints(coco_2d, foot_2d)

        # COCO 17kp indices 0-16
        np.testing.assert_array_equal(pts[:17], coco_2d.astype(np.float32))
        assert np.all(vis[:17] == 2.0)

        # Foot 6kp indices 17-22
        np.testing.assert_array_equal(pts[17:23], foot_2d)
        assert np.all(vis[17:23] == 2.0)

    def test_nan_handling(self):
        """Should set visibility to 0.0 for NaN keypoints."""
        coco_2d = np.ones((17, 2), dtype=np.float64)
        coco_2d[5] = np.nan  # One NaN COCO keypoint

        foot_2d = np.ones((6, 2), dtype=np.float32)
        foot_2d[2] = np.nan  # One NaN foot keypoint

        pts, vis = merge_coco_foot_keypoints(coco_2d, foot_2d)

        assert vis[5] == 0.0
        assert np.all(pts[5] == 0.0)  # Should remain zero-initialized

        assert vis[17 + 2] == 0.0
        assert np.all(pts[17 + 2] == 0.0)

        # All other visibilities should be 2.0
        assert np.all(vis[:5] == 2.0)
        assert np.all(vis[6:17] == 2.0)
        assert np.all(vis[17:19] == 2.0)
        assert np.all(vis[20:23] == 2.0)

    def test_face_duplicates_from_visible_source(self):
        """Face duplicates copy coords from visible source but are UNLABELED.

        #806: vis=0.0 (COCO unlabeled), NOT 0.3 (non-standard — mmpose treats
        v>0 as labeled, supervising the face keypoint with a copied eye/nose
        coord). Coord is kept for HALPE26 shape; supervision is dropped.
        """
        coco_2d = np.ones((17, 2), dtype=np.float64)
        foot_2d = np.ones((6, 2), dtype=np.float32)

        pts, vis = merge_coco_foot_keypoints(coco_2d, foot_2d)

        # Face duplicates: 23<-1, 24<-2, 25<-0 — coord still copied
        np.testing.assert_array_equal(pts[23], pts[1])
        np.testing.assert_array_equal(pts[24], pts[2])
        np.testing.assert_array_equal(pts[25], pts[0])

        # #806: unlabeled (0.0), not the non-standard 0.3
        assert vis[23] == 0.0
        assert vis[24] == 0.0
        assert vis[25] == 0.0

    def test_face_duplicates_from_nan_source_raises(self):
        """#1069: NaN source keypoint must raise — silent zeroing was
        INDISTINGUISHABLE from a dupe whose source is genuinely missing
        (the `isnan` branch above already zero-initializes local
        `pts[src_idx]`). Surface corrupted upstream data instead.
        """
        coco_2d = np.ones((17, 2), dtype=np.float64)
        coco_2d[0] = np.nan  # Source for index 25
        foot_2d = np.ones((6, 2), dtype=np.float32)

        with pytest.raises(ValueError, match=r"finite"):
            merge_coco_foot_keypoints(coco_2d, foot_2d)

    def test_face_duplicates_visible_source_unlabeled(self):
        """Face duplicates are 0.0 visibility when source is visible
        (see #806: dupes are always unlabeled, regardless of src vis).
        """
        coco_2d = np.ones((17, 2), dtype=np.float64)
        foot_2d = np.ones((6, 2), dtype=np.float32)

        _, vis = merge_coco_foot_keypoints(coco_2d, foot_2d)

        # #806: dupe vis is always 0.0 (unlabeled).
        assert vis[23] == 0.0
        assert vis[24] == 0.0
        assert vis[25] == 0.0


class TestFormatKeypoints:
    """Tests for format_keypoints function."""

    def test_format_keypoints_length(self):
        """Should return 78 values (26 keypoints * 3 coordinates)."""
        pts = np.ones((26, 2), dtype=np.float32)
        vis = np.ones(26, dtype=np.float32) * 2.0

        kp = format_keypoints(pts, vis)

        assert len(kp) == 26 * 3
        assert isinstance(kp, list)
        assert all(isinstance(v, float) for v in kp)

    def test_format_keypoints_values(self):
        """Should interleave x, y, visibility correctly."""
        pts = np.arange(52, dtype=np.float32).reshape(26, 2)
        vis = np.arange(26, dtype=np.float32)

        kp = format_keypoints(pts, vis)

        for i in range(26):
            assert kp[i * 3 + 0] == float(pts[i, 0])
            assert kp[i * 3 + 1] == float(pts[i, 1])
            assert kp[i * 3 + 2] == float(vis[i])


class TestBuildCocoJson:
    """Tests for build_coco_json function."""

    def test_empty_dataset(self):
        """Should build empty COCO JSON with default category."""
        data = build_coco_json([], [])

        assert data["images"] == []
        assert data["annotations"] == []
        assert data["categories"] == [DEFAULT_CATEGORY]

    def test_with_images_and_annotations(self):
        """Should build COCO JSON with provided entries."""
        images = [{"id": 1, "file_name": "img1.jpg", "width": 640, "height": 480}]
        annotations = [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "bbox": [10, 20, 30, 40],
                "keypoints": [0.0] * 78,
                "num_keypoints": 26,
            }
        ]

        data = build_coco_json(images, annotations)

        assert data["images"] == images
        assert data["annotations"] == annotations
        assert data["categories"] == [DEFAULT_CATEGORY]
        assert data["categories"][0]["keypoint_names"] == HALPE26_KEYPOINT_NAMES
        assert data["categories"][0]["skeleton"] == HALPE26_SKELETON


class TestSaveCocoJson:
    """Tests for save_coco_json function."""

    def test_saves_to_file(self):
        """Should write JSON to the specified path."""
        data = build_coco_json([], [])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "coco.json"
            save_coco_json(data, str(path))

            assert path.exists()
            content = path.read_text()
            loaded = json.loads(content)
            assert loaded == data

    def test_creates_parent_directories(self):
        """Should create parent directories if they don't exist."""
        data = build_coco_json([], [])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sub" / "dir" / "coco.json"
            save_coco_json(data, str(path))

            assert path.exists()
            loaded = json.loads(path.read_text())
            assert loaded == data

    def test_round_trip(self):
        """Exported JSON should match original data when loaded back."""
        images = [
            {"id": 1, "file_name": "frame_001.jpg", "width": 1920, "height": 1080},
            {"id": 2, "file_name": "frame_002.jpg", "width": 1920, "height": 1080},
        ]
        annotations = [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "bbox": [100.5, 200.5, 50.0, 80.0],
                "keypoints": [1.0, 2.0, 2.0] * 26,
                "num_keypoints": 26,
                "area": 4000.0,
                "iscrowd": 0,
            }
        ]
        data = build_coco_json(images, annotations)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "annotations.json"
            save_coco_json(data, str(path))

            with path.open("r") as f:
                loaded = json.load(f)

            assert loaded["images"] == images
            assert loaded["annotations"] == annotations
            assert loaded["categories"][0]["name"] == "person"
            assert loaded["categories"][0]["supercategory"] == "person"
            assert loaded["categories"][0]["id"] == 1


class TestConstants:
    """Tests for module-level constants."""

    def test_halpe26_keypoint_count(self):
        """Should have exactly 26 keypoint names."""
        assert len(HALPE26_KEYPOINT_NAMES) == 26
        assert all(isinstance(name, str) for name in HALPE26_KEYPOINT_NAMES)

    def test_halpe26_skeleton_pairs(self):
        """Skeleton connections should reference valid keypoint indices."""
        for a, b in HALPE26_SKELETON:
            assert 0 <= a < 26
            assert 0 <= b < 26

    def test_default_category_structure(self):
        """Default category should have required COCO fields."""
        assert DEFAULT_CATEGORY["id"] == 1
        assert DEFAULT_CATEGORY["name"] == "person"
        assert DEFAULT_CATEGORY["supercategory"] == "person"
        assert DEFAULT_CATEGORY["keypoint_names"] == HALPE26_KEYPOINT_NAMES
        assert DEFAULT_CATEGORY["skeleton"] == HALPE26_SKELETON
