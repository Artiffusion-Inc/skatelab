"""RED repro — `ReferenceBuilder.load_reference` (references/reference_builder.py:122-181)
crashes on corrupt .npz with NaN int fields via `int(float('nan'))` ValueError,
and silently propagates NaN fps into `ReferenceData.fps`.

The 7 `int(data[...])` calls (lines 137-139, 145-149) and 2 `float(data[...])`
calls (lines 136, 162) have no `np.isfinite` / `np.isnan` / `np.nan_to_num`
guard. `int(NaN)` raises `ValueError: cannot convert float NaN to integer`
(Python stdlib, verified). On disk corruption / partial write / out-of-band
save with NaN, the stdlib error escapes — undocumented, no hint of the
corrupt field name. NaN fps silently survives into `ReferenceData.fps`,
poising DTW phase timing and time-derived metrics (airtime, rotation speed,
GOE proxy).

`load_reference` is reached from `ReferenceStore.get` (reference_store.py:120)
and is what `pipeline._load_reference_async` (pipeline.py:973) ultimately calls.
One corrupt .npz crashes the entire pipeline at DTW alignment / phase timing
with an uninformative stdlib stack trace.

Sibling of `test_get_video_meta_nan_metadata_crash_repro.py` (tranche FA) —
same `int(NaN)` family, unguarded. The fix at #1041 broke the upstream
poison chain (VideoMeta.num_frames=NaN), but corrupt-disk / partial-write
still reaches `load_reference` directly with NaN fields in the .npz, so a
guard at the load trust boundary is needed regardless.

Contract: `load_reference` on a corrupt .npz with NaN int / float fields must
NEVER crash with the undocumented stdlib `ValueError("cannot convert float
NaN to integer")`. The path must produce a clean signal (typed RuntimeError
naming the corrupt field) — matching the #1041 `get_video_meta` style:
`RuntimeError("Corrupt reference .npz: non-finite <FIELD>=<value> for
path=...")`. Valid finite .npz must pass through unchanged.
"""

import inspect
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.references.reference_builder import ReferenceBuilder

# --------------------------------------------------------------------------- #
# Test fixture: build a valid in-memory .npz with a chosen set of corrupt
# fields, write to tmp, then exercise load_reference on it.
# --------------------------------------------------------------------------- #


def _make_valid_save_dict() -> dict[str, Any]:
    """Baseline save_dict matching save_reference's contract. All int/float
    fields are finite. The 5 int fields (width, height, num_frames, phases_*)
    and 2 float fields (fps, meta_fps) are the targets."""
    # dummy poses: 10 frames, 17 H3.6M keypoints, normalized [0,1]
    poses = np.zeros((10, 17, 2), dtype=np.float32)
    return {
        "element_type": "waltz_jump",
        "poses": poses,
        "fps": np.float32(30.0),
        "meta_fps": np.float32(30.0),
        "meta_width": np.int64(1920),
        "meta_height": np.int64(1080),
        "meta_num_frames": np.int64(10),
        "meta_path": "/data/refs/waltz.mp4",
        "phases_name": "waltz_jump",
        "phases_start": np.int64(0),
        "phases_takeoff": np.int64(2),
        "phases_peak": np.int64(4),
        "phases_landing": np.int64(6),
        "phases_end": np.int64(9),
        "source": "/data/refs/waltz.mp4",
    }


def _write_corrupt_npz(tmp_path: Path, **corrupt: Any) -> Path:
    """Write a .npz with a chosen subset of NaN fields. Anything not
    specified in `corrupt` uses the valid baseline."""
    save_dict = _make_valid_save_dict()
    save_dict.update(corrupt)
    out = tmp_path / "corrupt.npz"
    np.savez_compressed(out, **save_dict)
    return out


def _load(corrupt: dict[str, Any], tmp_path: Path):
    """Invoke load_reference on a .npz with the chosen corrupt fields. The
    ReferenceBuilder instance is constructed bare — load_reference is pure
    static-ish, no GPU/pose_extractor/normalizer needed for the .npz read."""
    path = _write_corrupt_npz(tmp_path, **corrupt)
    builder = ReferenceBuilder.__new__(ReferenceBuilder)  # bypass __init__
    return builder.load_reference(path)


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded int/float cast sites in
# load_reference. After the fix, the guard MUST appear at the trust
# boundary so int(NaN) / float(NaN) cannot propagate.
# --------------------------------------------------------------------------- #


def test_load_reference_source_has_no_nan_field_guard():
    """Root cause locked: load_reference (references/reference_builder.py:122-181)
    calls `int(data[...])` 7× and `float(data[...])` 2× with NO
    `np.isfinite` / `np.isnan` / `np.nan_to_num` guard. After the fix,
    a finite guard must appear at these trust boundaries so `int(NaN)` /
    `float(NaN)` cannot reach the stdlib calls."""
    builder = ReferenceBuilder.__new__(ReferenceBuilder)
    src = inspect.getsource(builder.load_reference)
    # Acceptable patterns: np.isfinite, np.isnan, math.isfinite, math.isnan,
    # np.nan_to_num — any of these makes int(NaN)/float(NaN) unreachable.
    has_guard = (
        "np.isfinite" in src
        or "np.isnan" in src
        or "math.isfinite" in src
        or "math.isnan" in src
        or "np.nan_to_num" in src
    )
    assert has_guard, (
        "BUG: ReferenceBuilder.load_reference "
        "(ml/src/references/reference_builder.py:122-181) calls int(data[...]) "
        "7× and float(data[...]) 2× on .npz fields with no finite guard. "
        "int(float('nan')) raises ValueError; float(NaN) silently leaks. "
        "Add np.isfinite (or np.isnan / math.isfinite) check around each "
        "cast — mirror #1041 get_video_meta's "
        "RuntimeError('Corrupt video metadata: non-finite <FIELD>=...') style."
    )


# --------------------------------------------------------------------------- #
# Observable 1: locks the crash mechanism — int(NaN) is ValueError.
# --------------------------------------------------------------------------- #


def test_int_nan_raises_valueerror():
    """Locks the crash mechanism independently of load_reference:
    `int(float('nan'))` raises ValueError. This is what propagates out
    of load_reference on a corrupt .npz with a NaN int field — the
    stdlib error, not a typed RuntimeError naming the corrupt field."""
    try:
        int(float("nan"))
    except ValueError:
        pass
    else:
        raise AssertionError(
            "int(float('nan')) did not raise ValueError — Python stdlib "
            "contract changed? Re-check the assertion below."
        )


# --------------------------------------------------------------------------- #
# Observable 2: NaN meta_num_frames → load_reference must NOT crash with
# the undocumented stdlib ValueError. Must raise typed RuntimeError naming
# the corrupt field, mirroring #1041's "Corrupt video metadata: non-finite
# CAP_PROP_FRAME_COUNT" style.
# --------------------------------------------------------------------------- #


def test_nan_meta_num_frames_does_not_crash_with_undocumented_valueerror(
    tmp_path: Path,
):
    """Contract: NaN `meta_num_frames` must NOT crash with the
    undocumented stdlib `ValueError("cannot convert float NaN to
    integer")` that has no hint of the corrupt field. The fix produces
    a clean signal — a typed `RuntimeError` naming the corrupt field.

    RED before fix: stdlib ValueError ("cannot convert float NaN to
    integer") escapes. GREEN after fix: RuntimeError with the corrupt
    field name in the message.
    """
    try:
        _load({"meta_num_frames": np.float32(float("nan"))}, tmp_path)
    except ValueError as e:
        # RED branch: stdlib int(NaN) ValueError leaks. The fix must
        # replace this with a typed RuntimeError — assert the message
        # names the corrupt field, not the generic stdlib text.
        msg = str(e)
        assert "meta_num_frames" in msg or "non-finite" in msg, (
            f"BUG: load_reference raised undocumented stdlib ValueError "
            f"({msg!r}) on NaN meta_num_frames. The fix must raise a "
            f"typed RuntimeError naming the corrupt field — e.g. "
            f"'Corrupt reference .npz: non-finite meta_num_frames=nan "
            f"for path=...'. Stdlib `cannot convert float NaN to "
            f"integer` is a symptom, not a root-cause signal."
        )
    except RuntimeError as e:
        # GREEN branch: fix raises typed RuntimeError naming the field.
        msg = str(e)
        assert "meta_num_frames" in msg or "non-finite" in msg, (
            f"RuntimeError must name the corrupt field (meta_num_frames or non-finite), got: {e!r}"
        )
    else:
        raise AssertionError(
            "load_reference must raise RuntimeError on NaN meta_num_frames, "
            "not silently return ReferenceData with num_frames=NaN."
        )


# --------------------------------------------------------------------------- #
# Observable 3: NaN meta_fps → ReferenceData.fps must be finite (NOT NaN).
# The silent NaN-fps leak is a separate bug from the int(NaN) crash —
# the fix must guard the float() cast sites at lines 136/162 so Reference-
# Data.fps is never NaN-poisoned.
# --------------------------------------------------------------------------- #


def test_nan_meta_fps_silently_leaks_to_reference_data_fps_now_fixed(
    tmp_path: Path,
):
    """Contract: NaN `meta_fps` must NOT silently propagate to
    `ReferenceData.fps`. Either the fix raises a typed RuntimeError
    naming the corrupt field, OR ReferenceData.fps is finite (non-NaN).

    RED before fix: float(NaN) silently survives into ReferenceData.fps
    (line 136), poisoning 1.0 / fps in DTW phase timing. GREEN after
    fix: RuntimeError naming the field, OR finite fps on returned data.
    """
    try:
        ref = _load({"meta_fps": np.float32(float("nan"))}, tmp_path)
    except RuntimeError as e:
        # GREEN branch: typed error path. Assert it names the field.
        msg = str(e)
        assert "meta_fps" in msg or "fps" in msg or "non-finite" in msg, (
            f"RuntimeError must name the corrupt fps field, got: {e!r}"
        )
    except ValueError as e:
        # Acceptable GREEN path: typed error wrapping stdlib ValueError.
        msg = str(e)
        assert "meta_fps" in msg or "fps" in msg or "non-finite" in msg, (
            f"Error must name the corrupt fps field, got: {e!r}"
        )
    else:
        assert math.isfinite(ref.fps), (
            f"BUG: load_reference silently leaked NaN meta_fps to "
            f"ReferenceData.fps={ref.fps!r}. Downstream `1.0 / fps` "
            f"produces NaN, poisoning DTW phase timing and time-derived "
            f"metrics (airtime, rotation speed, GOE proxy). The fix "
            f"must guard float(data[...]) with np.isfinite."
        )


# --------------------------------------------------------------------------- #
# Observable 4: NaN phases_takeoff → load_reference must NOT crash with
# the undocumented stdlib ValueError. Mirrors test 2 for a phases int
# field, covering one of the 5 phases_* int casts (lines 145-149).
# --------------------------------------------------------------------------- #


def test_nan_phases_takeoff_does_not_crash_with_undocumented_valueerror(
    tmp_path: Path,
):
    """Contract: NaN `phases_takeoff` must NOT crash with the undocumented
    stdlib `ValueError("cannot convert float NaN to integer")`. The fix
    raises a typed RuntimeError naming the corrupt field, or returns
    ReferenceData with finite phases."""
    try:
        _load({"phases_takeoff": np.float32(float("nan"))}, tmp_path)
    except ValueError as e:
        msg = str(e)
        assert "phases_takeoff" in msg or "non-finite" in msg, (
            f"BUG: load_reference raised undocumented stdlib ValueError "
            f"({msg!r}) on NaN phases_takeoff. The fix must raise a typed "
            f"RuntimeError naming the corrupt field."
        )
    except RuntimeError as e:
        msg = str(e)
        assert "phases_takeoff" in msg or "non-finite" in msg, (
            f"RuntimeError must name the corrupt field, got: {e!r}"
        )
    else:
        raise AssertionError(
            "load_reference must raise RuntimeError on NaN phases_takeoff, "
            "not silently return ReferenceData with phases_takeoff=NaN."
        )


# --------------------------------------------------------------------------- #
# Regression guard: valid finite .npz must pass through unchanged — the
# fix must not alter the valid path.
# --------------------------------------------------------------------------- #


def test_valid_npz_returns_finite_reference_data(tmp_path: Path):
    """Regression: clean finite .npz → ReferenceData with all finite
    fields, fps=30, width=1920, height=1080, num_frames=10, phases
    start=0/takeoff=2/peak=4/landing=6/end=9. The fix must not alter
    the valid path."""
    ref = _load({}, tmp_path)
    assert ref.fps == pytest.approx(30.0)
    assert ref.meta.width == 1920
    assert ref.meta.height == 1080
    assert ref.meta.num_frames == 10
    assert math.isfinite(ref.fps)
    assert math.isfinite(ref.meta.fps)
    assert ref.phases.start == 0
    assert ref.phases.takeoff == 2
    assert ref.phases.peak == 4
    assert ref.phases.landing == 6
    assert ref.phases.end == 9
