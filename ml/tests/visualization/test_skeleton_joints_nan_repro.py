"""Repro tests for #623: skeleton.joints NaN confidence crashes.

Bug: get_joint_radius / get_confidence_radius do `int(base_radius * confidence)`
which raises ValueError for NaN input. get_joint_radius_3d silently produces
a wrong value (NaN propagates through max/min comparison).

Contract: NaN input → 0 (don't draw joint) without raising.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# Stub the parent visualization package to avoid heavy import chain
# (cv2 → PIL → onnxruntime → scipy → numba). We only need joint_radius fns.
_visualization_pkg = types.ModuleType("src.visualization")
_visualization_pkg.__path__ = []  # mark as package
sys.modules.setdefault("src", types.ModuleType("src"))
sys.modules.setdefault("src.visualization", _visualization_pkg)
_skel_pkg = types.ModuleType("src.visualization.skeleton")
_skel_pkg.__path__ = []
sys.modules["src.visualization.skeleton"] = _skel_pkg

# Stub config module that joints.py imports from
_config_stub = types.ModuleType("src.visualization.config")
_config_stub.confidence_threshold = 0.3
_config_stub.joint_radius = 5
_config_stub.color_joint = (255, 255, 255)
_config_stub.color_center = (200, 200, 200)
_config_stub.color_left_side = (255, 100, 100)
_config_stub.color_right_side = (100, 100, 255)
sys.modules["src.visualization.config"] = _config_stub

# Stub src.types with a minimal H36Key enum
_types_stub = types.ModuleType("src.types")


class _H36Key:
    HIP_CENTER = 0
    RHIP = 1
    RKNEE = 2
    RFOOT = 3
    LHIP = 4
    LKNEE = 5
    LFOOT = 6
    SPINE = 7
    THORAX = 8
    NECK = 9
    HEAD = 10
    LSHOULDER = 11
    LELBOW = 12
    LWRIST = 13
    RSHOULDER = 14
    RELBOW = 15
    RWRIST = 16
    LEFT_HIP = LHIP
    RIGHT_HIP = RHIP
    LEFT_KNEE = LKNEE
    RIGHT_KNEE = RKNEE
    LEFT_FOOT = LFOOT
    RIGHT_FOOT = RFOOT
    LEFT_SHOULDER = LSHOULDER
    RIGHT_SHOULDER = RSHOULDER
    LEFT_ELBOW = LELBOW
    RIGHT_ELBOW = RELBOW
    LEFT_WRIST = LWRIST
    RIGHT_WRIST = RWRIST
    LEFT_EYE = HEAD


_types_stub.H36Key = _H36Key
sys.modules["src.types"] = _types_stub

_HERE = Path(__file__).resolve()
_SRC_FILE = _HERE.parents[2] / "src" / "visualization" / "skeleton" / "joints.py"
_SPEC = importlib.util.spec_from_file_location("joints_under_test", _SRC_FILE)
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["joints_under_test"] = _mod
_SPEC.loader.exec_module(_mod)
get_joint_radius = _mod.get_joint_radius
get_joint_radius_3d = _mod.get_joint_radius_3d
get_confidence_radius = _mod.get_confidence_radius


def test_get_joint_radius_nan_returns_zero():
    """NaN confidence must not crash; treat as invalid → radius 0."""
    out = get_joint_radius(float("nan"))
    assert out == 0


def test_get_joint_radius_inf_returns_zero():
    """Inf confidence must not crash; treat as invalid → radius 0."""
    out = get_joint_radius(float("inf"))
    assert out == 0


def test_get_joint_radius_below_threshold_returns_zero():
    """Sanity: low confidence still returns 0 (existing behavior)."""
    out = get_joint_radius(0.1, threshold=0.3)
    assert out == 0


def test_get_joint_radius_valid_returns_scaled():
    """Sanity: valid confidence returns scaled radius."""
    out = get_joint_radius(0.8)
    assert out > 0


def test_get_confidence_radius_nan_returns_zero():
    """get_confidence_radius (line 277) must handle NaN."""
    out = get_confidence_radius(float("nan"))
    assert out == 0


def test_get_joint_radius_3d_nan_returns_zero_or_min():
    """3D depth NaN must not crash. Acceptable: return min radius (2)."""
    out = get_joint_radius_3d(float("nan"))
    assert out >= 0  # not raise; return some valid int
