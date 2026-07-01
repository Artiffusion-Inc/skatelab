"""RED repro: export_3d poses_to_glb_sequence crashes (OSError) on all-NaN frame.

Root cause
----------
``ml/src/visualization/export_3d.py:200-202`` — ``poses_to_glb_sequence``::

    for i in range(len(poses_3d)):
        glb = poses_to_glb(poses_3d, i, bone_radius, joint_radius)
        dst = out_dir / f"frame_{i:04d}.glb"
        Path(glb).rename(dst)

``poses_to_glb`` returns ``""`` (empty string) for all-NaN frames (line 93-94)
or empty scenes (line 168-169). Then ``Path(glb).rename(dst)``:
``Path("")`` normalizes to ``PosixPath('.')`` (= CWD) → ``.rename(dst)`` tries to
rename the current working directory → ``OSError: [Errno 16] Device or resource
busy``. This crashes the entire sequence export on the first all-NaN/empty frame.

LATENT — 0 production callers
-----------------------------
``poses_to_glb_sequence`` has 0 production callers. Only
``ml/tests/visualization/test_export_3d.py`` references it, and there it
``@patch``es ``poses_to_glb`` to always return a real temp file via
``tempfile.mkstemp`` — the empty-path branch is never exercised. Gradio/demo
utilities (``ml/scripts/visualize_with_skeleton.py``) are not wired into the
backend pipeline. Becomes live the moment export_3d is wired into the
pipeline/CLI.

Bug class
---------
empty-input crash / ``Path('')``-normalizes-to-CWD — a Python footgun:
``Path('')`` is ``PosixPath('.')`` (the CWD), so any code that does
``Path(maybe_empty_str).rename(dst)`` will attempt to rename the CWD itself.

Repro
-----
``poses_to_glb_sequence(np.full((3, 17, 3), np.nan), str(tmp_path))`` →
``OSError`` on frame 0.

Fix suggestion (DO NOT apply here — file issue only)
----------------------------------------------------
Guard ``if not glb: continue`` before ``Path(glb).rename(dst)`` to skip
empty/NaN frames instead of crashing the whole sequence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add ml to path for imports (matches test_export_3d.py convention)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.visualization.export_3d import poses_to_glb_sequence


def test_poses_to_glb_sequence_all_nan_no_crash(tmp_path):
    """poses_to_glb_sequence must not crash on an all-NaN frame.

    poses_to_glb returns '' for all-NaN frames; poses_to_glb_sequence then
    does Path('').rename(dst) = Path('.').rename(dst) → tries to rename CWD →
    OSError Errno 16 Device or resource busy. LATENT (0 prod callers).
    """
    poses = np.full((3, 17, 3), np.nan, dtype=np.float32)
    exc: Exception | None = None
    raised = False
    try:
        poses_to_glb_sequence(poses, str(tmp_path))
    except OSError as e:
        raised = True
        exc = e
    assert not raised, (
        f"BUG: poses_to_glb_sequence crashes on all-NaN frame: {exc!r}. "
        "poses_to_glb returns '' for NaN frames → Path('').rename(dst) = "
        "Path('.').rename(dst) → renames CWD → OSError Device busy. "
        "LATENT (0 prod callers, demo/test only)."
    )
