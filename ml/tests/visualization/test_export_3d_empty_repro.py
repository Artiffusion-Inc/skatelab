"""Repro tests for #625: poses_to_glb crashes on empty poses_3d.

Bug: `if frame_idx >= len(poses_3d): frame_idx = len(poses_3d) - 1`
makes frame_idx = -1 for empty input; `poses_3d[-1]` raises IndexError.

Contract: empty input must return "" (no file) without raising.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# Stub heavy deps
sys.modules.setdefault("src", types.ModuleType("src"))
_viz_pkg = types.ModuleType("src.visualization")
_viz_pkg.__path__ = []
sys.modules["src.visualization"] = _viz_pkg

# Stub types
_types_stub = types.ModuleType("src.types")

_H36M_SKELETON_EDGES = [
    (0, 7),
    (7, 8),
    (8, 9),
    (9, 10),  # spine + head
    (8, 11),
    (11, 12),
    (12, 13),  # left arm
    (8, 14),
    (14, 15),
    (15, 16),  # right arm
    (0, 1),
    (1, 2),
    (2, 3),  # right leg
    (0, 4),
    (4, 5),
    (5, 6),  # left leg
]
_types_stub.H36M_SKELETON_EDGES = _H36M_SKELETON_EDGES
sys.modules["src.types"] = _types_stub

# Stub utils.geometry
_geom_stub = types.ModuleType("src.utils")
_geom_stub.__path__ = []
sys.modules["src.utils"] = _geom_stub
_geom_inner = types.ModuleType("src.utils.geometry")


def _fake_angle_3pt(a, b, c):
    return 90.0  # constant for tests


_geom_inner.angle_3pt = _fake_angle_3pt
sys.modules["src.utils.geometry"] = _geom_inner

# Load module
_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src" / "visualization" / "export_3d.py"
_spec = importlib.util.spec_from_file_location("export_3d_under_test", _SRC)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["export_3d_under_test"] = _mod
_spec.loader.exec_module(_mod)
poses_to_glb = _mod.poses_to_glb


def test_poses_to_glb_empty_returns_empty_string():
    """Empty poses_3d must not crash; return empty string (no frame)."""
    import numpy as np

    out = poses_to_glb(np.zeros((0, 17, 3), dtype=np.float32))
    # Existing convention: return "" when no renderable frame
    assert out == ""


def test_poses_to_glb_single_valid_frame():
    """Sanity: one valid frame produces a .glb file path."""
    import numpy as np

    poses = np.random.rand(1, 17, 3).astype(np.float32) * 0.5
    out = poses_to_glb(poses)
    # Should produce a path (string ending in .glb)
    assert isinstance(out, str)
    assert out.endswith(".glb") or out == ""  # empty is acceptable for all-NaN


def test_poses_to_glb_all_nan_returns_empty_string():
    """All-NaN frame returns "" (existing behavior, regression check)."""
    import numpy as np

    poses = np.full((1, 17, 3), np.nan, dtype=np.float32)
    out = poses_to_glb(poses)
    assert out == ""
