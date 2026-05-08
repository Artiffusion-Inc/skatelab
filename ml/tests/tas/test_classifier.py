"""Tests for RF segment classifier."""

import numpy as np
import pytest

try:
    from ml.src.tas.classifier import SegmentClassifier, extract_segment_features
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from tas.classifier import SegmentClassifier, extract_segment_features


def test_extract_features():
    poses = np.random.randn(50, 17, 2).astype(np.float32)
    feats = extract_segment_features(poses, fps=30.0)
    assert "duration" in feats
    assert "hip_y_range" in feats
    assert "motion_energy" in feats
    assert "rotation_speed" in feats
    assert "num_frames" in feats
    assert feats["duration"] == 50 / 30.0


def test_classifier_fit_predict():
    segments = [
        {
            "features": {
                "duration": 1.0,
                "hip_y_range": 0.5,
                "motion_energy": 0.1,
                "rotation_speed": 200.0,
                "num_frames": 30,
            },
            "label": "3Flip",
        },
        {
            "features": {
                "duration": 3.0,
                "hip_y_range": 0.1,
                "motion_energy": 0.05,
                "rotation_speed": 50.0,
                "num_frames": 90,
            },
            "label": "ChComboSpin4",
        },
    ]
    clf = SegmentClassifier(n_estimators=10)
    clf.fit(segments)
    label, conf = clf.predict(segments[0]["features"])
    assert label == "3Flip"
    assert 0 <= conf <= 1


if __name__ == "__main__":
    test_extract_features()
    print("✓ extract_features OK")
    test_classifier_fit_predict()
    print("✓ classifier_fit_predict OK")
    print("ALL CLASSIFIER TESTS PASSED")
