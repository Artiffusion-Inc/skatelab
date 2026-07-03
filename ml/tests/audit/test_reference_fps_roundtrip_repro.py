"""RED repro — ReferenceBuilder.save_reference drops ref.fps on save/load.

Bug: ReferenceBuilder.save_reference (reference_builder.py:100-115)
builds `save_dict` with these keys:

  element_type, poses,
  meta_fps, meta_width, meta_height, meta_num_frames, meta_path,
  phases_name, phases_start, phases_takeoff, phases_peak,
  phases_landing, phases_end,
  source,
  (optional poses_3d)

There is NO `"fps"` key in save_dict — `ref.fps` is never persisted.

ReferenceBuilder.load_reference (reference_builder.py:156-165)
reconstructs fps as:

  fps=float(data.get("fps", meta.fps if meta else 30.0))

Since save_reference never writes "fps", `data.get("fps", ...)` always
hits the fallback → `meta.fps` (or 30.0 when meta is None). When
`ref.fps != meta.fps` (the user built a ReferenceData with an fps
override, or with meta=None + fps=60), the save→load round trip
silently replaces the original fps with meta.fps / 30.0.

Scenario:
  ref = ReferenceData(element_type="waltz_jump",
                      poses=..., phases=...,
                      fps=60.0,            # <-- original fps 60
                      meta=VideoMeta(fps=30.0, ...),  # <-- meta.fps 30
                      source="t.mp4")
  path = builder.save_reference(ref, tmp_path)   # writes NO "fps" key
  loaded = builder.load_reference(path)          # data.get("fps", meta.fps)
                                                 # → 30.0 (NOT 60.0)

  loaded.fps == 30.0   ← WRONG (should be 60.0)

Prod-impact (MEDIUM): DTW phase timing and all time-derived metrics
(airtime_sec, phase slicing, rotation speed per second) depend on
`ref.fps`. A 60fps reference loaded as 30fps halves every time-derived
comparison → silently wrong DTW scores / GOE proxy / recommendations.
No error, no warning — the fps is silently rewritten. Reachable when a
ReferenceData is built with meta=None (fps override) or with an fps
that differs from the source video's meta.fps — both are supported by
the ReferenceData dataclass and the public save/load API (used by the
pipeline's _load_reference_async).

Existing tests `test_save_reference_creates_npz` and
`test_load_reference_fallback_fps` both use fps == meta.fps (no
mismatch) or only assert on meta.fps — the round-trip drop is untested.
`test_load_reference_fallback_fps` even documents the gap: "'fps' key
is not written by save_reference; falls back to meta.fps" — but never
tests the case where that fallback is WRONG (ref.fps != meta.fps).

Fix direction (do NOT apply here): add `"fps": ref.fps` to save_dict
(reference_builder.py:100-115). load_reference already reads
`data.get("fps", ...)` so it picks the persisted value up — one line.

This test MUST fail (RED) against the current code. Repro, not a fix.
"""

from pathlib import Path

import numpy as np

from src.references.reference_builder import ReferenceBuilder
from src.types import ElementPhase, ReferenceData, VideoMeta


def test_save_load_reference_preserves_fps_when_differs_from_meta(tmp_path: Path):
    """save_reference must persist ref.fps so load_reference round-trips it.

    When ref.fps != meta.fps, the current code drops ref.fps and load
    falls back to meta.fps → 60fps ref loaded as 30fps.
    """
    # ReferenceBuilder needs pose_extractor + normalizer only for
    # build_from_video; save_reference/load_reference do not use them.
    builder = ReferenceBuilder(pose_extractor=None, normalizer=None)

    poses = np.zeros((5, 17, 2), dtype=np.float32)
    phases = ElementPhase(
        name="waltz_jump",
        start=0,
        takeoff=2,
        peak=3,
        landing=4,
        end=5,
    )
    meta = VideoMeta(
        path=Path("t.mp4"),
        width=1920,
        height=1080,
        fps=30.0,
        num_frames=5,
    )
    # ref.fps=60.0 DIFFERS from meta.fps=30.0 — the mismatch case.
    ref = ReferenceData(
        element_type="waltz_jump",
        name="expert_waltz",
        poses=poses,
        phases=phases,
        fps=60.0,
        meta=meta,
        source="t.mp4",
    )

    out = builder.save_reference(ref, tmp_path)
    loaded = builder.load_reference(out)

    assert loaded.fps == 60.0, (
        "BUG: save_reference drops ref.fps (save_dict at "
        "reference_builder.py:100-115 has no 'fps' key) → load_reference "
        "falls back to meta.fps (data.get('fps', meta.fps)) → 60fps ref "
        "loaded as 30fps → DTW phase timing + time-derived metrics "
        f"(airtime/phase slicing) silently halved. got loaded.fps={loaded.fps}"
    )
