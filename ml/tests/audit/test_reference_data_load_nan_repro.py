"""RED repro — `ReferenceData.load` (types.py:725-748) crashes on a
corrupt .npz with NaN phase fields via `int(NaN)` ValueError.

`np.savez` writes the 6-tuple `("phases_name", start, takeoff, peak,
landing, end)` (save() at types.py:705-723). The load() (line 728) does
`phase_name, start, takeoff, peak, landing, end = data["phases"]` and
then `int(start)`, `int(takeoff)`, `int(peak)`, `int(landing)`,
`int(end)` (lines 732-736) with NO `np.isfinite` / `np.isnan` /
`np.nan_to_num` guard. `int(float('nan'))` raises
`ValueError: cannot convert float NaN to integer` (Python stdlib,
verified). On disk corruption / partial write / out-of-band save with
NaN (a float64 phases array written by a buggy producer, or a
mitm-edited .npz where the unicode string "0" was overwritten with a
float NaN), the stdlib error escapes — undocumented, no hint of the
corrupt field name. Reference loader → pipeline → HTTP 500 (broken
session).

Also covers `float(data["fps"])` (line 747) — same family, but the
NaN-fps path is a silent NaN-fps leak (1.0/fps → NaN in DTW phase
timing), not a crash. The fix at the trust boundary must catch both
the int(NaN) crash and the float(NaN) silent leak.

Sibling of `test_load_reference_nan_field_crash_repro.py` (tranche JX,
ReferenceBuilder.load_reference) and `test_types_nan_phase_crash_repro`
(tranche KQ, sibling int(NaN) family in the same types.py module). The
fix (NOT applied — repro only): guard each `int(...)` and `float(...)`
cast site with `np.isfinite` so the loader either raises a typed
`RuntimeError` naming the corrupt field, OR returns ReferenceData with
finite phases/fps. Valid finite .npz must pass through unchanged.

Contract: `ReferenceData.load` on a corrupt .npz with NaN phase fields
must NEVER crash with the undocumented stdlib
`ValueError("cannot convert float NaN to integer")`. The path must
produce a clean signal (typed RuntimeError naming the corrupt field, OR
finite ReferenceData). Valid finite .npz must pass through unchanged.
"""

import inspect
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.types import ElementPhase, ReferenceData, VideoMeta

# --------------------------------------------------------------------------- #
# Test fixture: build a valid in-memory .npz with a chosen set of corrupt
# fields via ReferenceData.save's contract, write to tmp, then exercise
# ReferenceData.load on it.
# --------------------------------------------------------------------------- #


def _make_valid_poses() -> np.ndarray:
    """10 frames, 17 H3.6M keypoints, normalized [0,1]."""
    return np.zeros((10, 17, 2), dtype=np.float32)


def _make_valid_save_dict() -> dict[str, Any]:
    """Baseline save_dict matching ReferenceData.save's contract. All
    phases are finite ints; fps is a finite float. The 5 int phase
    fields (start, takeoff, peak, landing, end) and 1 float field (fps)
    are the targets."""
    return {
        "element_type": "waltz_jump",
        "name": "expert_waltz",
        "poses": _make_valid_poses(),
        "phases": (
            "waltz_jump",  # name (str)
            0,  # start
            2,  # takeoff
            4,  # peak
            6,  # landing
            9,  # end
        ),
        "fps": np.float32(30.0),
    }


def _write_corrupt_npz(tmp_path: Path, **corrupt: Any) -> Path:
    """Write a .npz with a chosen subset of NaN fields. Anything not
    specified in `corrupt` uses the valid baseline. The phases tuple is
    written as a float64 array (6 elements) so that any NaN slot hits
    `int(float('nan'))` → `ValueError: cannot convert float NaN to
    integer` at the trust boundary. The float64 array form is one of
    the realistic corrupt-write shapes (a buggy producer that wrote
    numeric phases instead of the unicode-string default, or a
    mitm-edited .npz where the unicode string '0' was replaced with a
    float NaN). `np.load` reads float64 without allow_pickle."""
    save_dict = _make_valid_save_dict()
    save_dict.update(corrupt)
    # Rebuild phases as a float64 array with NaN at the chosen slots.
    _phase_name, start, takeoff, peak, landing, end = save_dict["phases"]
    phases_arr = np.array(
        [
            float("nan")
            if corrupt.get("name") is _NAN
            else 0.0,  # name slot — NaN OK, str(NaN)="nan"
            float("nan") if corrupt.get("start") is _NAN else float(start),
            float("nan") if corrupt.get("takeoff") is _NAN else float(takeoff),
            float("nan") if corrupt.get("peak") is _NAN else float(peak),
            float("nan") if corrupt.get("landing") is _NAN else float(landing),
            float("nan") if corrupt.get("end") is _NAN else float(end),
        ],
        dtype=np.float64,
    )
    save_dict["phases"] = phases_arr
    if corrupt.get("fps") is _NAN:
        save_dict["fps"] = np.float32(float("nan"))
    out = tmp_path / "corrupt.npz"
    np.savez(out, **save_dict)
    return out


# Sentinel for "make this field NaN" — distinct from the user passing
# a real value of float("nan") by accident.
_NAN = object()


def _load(tmp_path: Path, **corrupt: Any) -> ReferenceData:
    """Invoke ReferenceData.load on a .npz with the chosen corrupt
    fields. Returns ReferenceData on success; re-raises on crash (the
    test then inspects the exception type/message)."""
    path = _write_corrupt_npz(tmp_path, **corrupt)
    return ReferenceData.load(path)


def _load_valid(tmp_path: Path) -> ReferenceData:
    """Regression path: load a .npz written by ReferenceData.save
    itself (the unicode-string phases format), not the float64-NaN
    test format. This is the canonical round-trip path — must pass
    through ReferenceData.load unchanged."""
    phases = ElementPhase(
        name="waltz_jump",
        start=0,
        takeoff=2,
        peak=4,
        landing=6,
        end=9,
    )
    ref = ReferenceData(
        element_type="waltz_jump",
        name="expert_waltz",
        poses=_make_valid_poses(),
        phases=phases,
        fps=30.0,
    )
    out = tmp_path / "valid.npz"
    ref.save(out)
    return ReferenceData.load(out)


# --------------------------------------------------------------------------- #
# Source check: root cause locked — unguarded int() / float() cast
# sites in ReferenceData.load (types.py:725-748).
# --------------------------------------------------------------------------- #


def test_reference_data_load_source_has_no_nan_field_guard():
    """Root cause locked: `ReferenceData.load` (types.py:725-748)
    calls `int(...)` 5× on phase fields (start, takeoff, peak, landing,
    end — lines 732-736) and `float(...)` 1× on fps (line 747) with NO
    `np.isfinite` / `np.isnan` / `np.nan_to_num` guard. After the fix,
    a finite guard must appear at these trust boundaries so `int(NaN)`
    / `float(NaN)` cannot reach the stdlib calls."""
    src = inspect.getsource(ReferenceData.load)
    has_guard = (
        "np.isfinite" in src
        or "np.isnan" in src
        or "math.isfinite" in src
        or "math.isnan" in src
        or "np.nan_to_num" in src
    )
    assert has_guard, (
        "BUG: ReferenceData.load (ml/src/types.py:725-748) calls int() "
        "5× on phase fields (start, takeoff, peak, landing, end) and "
        "float() 1× on fps with no finite guard. int(float('nan')) "
        "raises ValueError; float(NaN) silently leaks. Add np.isfinite "
        "(or np.isnan / math.isfinite) check around each cast — mirror "
        "the #1041 / #1230 typed RuntimeError style."
    )


# --------------------------------------------------------------------------- #
# Observable 1: locks the crash mechanism — int(NaN) is ValueError.
# --------------------------------------------------------------------------- #


def test_int_nan_raises_valueerror():
    """Locks the crash mechanism independently of ReferenceData.load:
    `int(float('nan'))` raises ValueError. This is what propagates out
    of ReferenceData.load on a corrupt .npz with a NaN phase field —
    the stdlib error, not a typed RuntimeError naming the corrupt
    field. Passes today (Python stdlib contract); exists to document
    the mechanism the fix must interrupt."""
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
# Observable 2: NaN phases.start → ReferenceData.load must NOT crash
# with the undocumented stdlib ValueError. Mirrors the issue's primary
# case (any phase field = NaN → int(NaN) ValueError).
# --------------------------------------------------------------------------- #


def test_nan_phase_start_does_not_crash_with_undocumented_valueerror(
    tmp_path: Path,
):
    """Contract: NaN `phases.start` must NOT crash with the
    undocumented stdlib `ValueError("cannot convert float NaN to
    integer")` that has no hint of the corrupt field. The fix produces
    a clean signal — either a typed RuntimeError naming the corrupt
    field, or a ReferenceData with finite phases.

    RED before fix: stdlib ValueError ("cannot convert float NaN to
    integer") escapes from line 732. GREEN after fix: RuntimeError
    with the corrupt field name in the message, or ReferenceData
    returned with finite phases.
    """
    try:
        ref = _load(tmp_path, start=_NAN)
    except ValueError as e:
        # RED branch: stdlib int(NaN) ValueError leaks. The fix must
        # replace this with a typed RuntimeError — assert the message
        # names the corrupt field, not the generic stdlib text.
        msg = str(e)
        assert "start" in msg or "non-finite" in msg or "phase" in msg, (
            f"BUG: ReferenceData.load raised undocumented stdlib "
            f"ValueError ({msg!r}) on NaN phases.start. The fix must "
            f"raise a typed RuntimeError naming the corrupt field — "
            f"e.g. 'Corrupt reference .npz: non-finite start=nan for "
            f"path=...'. Stdlib `cannot convert float NaN to integer` "
            f"is a symptom, not a root-cause signal."
        )
    except RuntimeError as e:
        # GREEN branch: fix raises typed RuntimeError naming the field.
        msg = str(e)
        assert "start" in msg or "non-finite" in msg or "phase" in msg, (
            f"RuntimeError must name the corrupt field, got: {e!r}"
        )
    else:
        assert math.isfinite(ref.phases.start), (
            f"BUG: ReferenceData.load returned ReferenceData with "
            f"phases.start={ref.phases.start!r} (NaN-poisoned). The "
            f"fix must ensure phases.start is finite even when the "
            f"corrupt .npz has NaN there."
        )


# --------------------------------------------------------------------------- #
# Observable 3: NaN phases.takeoff → must NOT crash with stdlib
# ValueError. Covers the specific field name from the issue body
# (takeoff is the canonical "any phase field" example in #1232).
# --------------------------------------------------------------------------- #


def test_nan_phase_takeoff_does_not_crash_with_undocumented_valueerror(
    tmp_path: Path,
):
    """Contract: NaN `phases.takeoff` must NOT crash with the
    undocumented stdlib `ValueError("cannot convert float NaN to
    integer")` — mirrors issue #1232. The fix raises a typed
    RuntimeError naming the corrupt field, or returns ReferenceData
    with finite phases."""
    try:
        ref = _load(tmp_path, takeoff=_NAN)
    except ValueError as e:
        msg = str(e)
        assert "takeoff" in msg or "non-finite" in msg or "phase" in msg, (
            f"BUG: ReferenceData.load raised undocumented stdlib "
            f"ValueError ({msg!r}) on NaN phases.takeoff. The fix must "
            f"raise a typed RuntimeError naming the corrupt field."
        )
    except RuntimeError as e:
        msg = str(e)
        assert "takeoff" in msg or "non-finite" in msg or "phase" in msg, (
            f"RuntimeError must name the corrupt field, got: {e!r}"
        )
    else:
        assert math.isfinite(ref.phases.takeoff), (
            f"BUG: ReferenceData.load returned ReferenceData with "
            f"phases.takeoff={ref.phases.takeoff!r} (NaN-poisoned). "
            f"DTW phase timing and time-derived metrics (airtime, "
            f"rotation speed, GOE proxy) compute NaN from NaN frames."
        )


# --------------------------------------------------------------------------- #
# Observable 4: NaN fps → ReferenceData.fps must be finite (NOT NaN).
# The silent NaN-fps leak is a separate bug from the int(NaN) crash —
# the fix must guard the float() cast at line 747 so ReferenceData.fps
# is never NaN-poisoned.
# --------------------------------------------------------------------------- #


def test_nan_fps_silently_leaks_to_reference_data_fps_now_fixed(
    tmp_path: Path,
):
    """Contract: NaN `fps` must NOT silently propagate to
    `ReferenceData.fps`. Either the fix raises a typed RuntimeError
    naming the corrupt field, OR ReferenceData.fps is finite (non-NaN).

    RED before fix: float(NaN) silently survives into ReferenceData.fps
    (line 747), poisoning 1.0 / fps in DTW phase timing. GREEN after
    fix: RuntimeError naming the field, OR finite fps on returned data.
    """
    try:
        ref = _load(tmp_path, fps=_NAN)
    except RuntimeError as e:
        # GREEN branch: typed error path. Assert it names the field.
        msg = str(e)
        assert "fps" in msg or "non-finite" in msg, (
            f"RuntimeError must name the corrupt fps field, got: {e!r}"
        )
    except ValueError as e:
        # Acceptable GREEN path: typed error wrapping stdlib ValueError.
        msg = str(e)
        assert "fps" in msg or "non-finite" in msg, (
            f"Error must name the corrupt fps field, got: {e!r}"
        )
    else:
        assert math.isfinite(ref.fps), (
            f"BUG: ReferenceData.load silently leaked NaN fps to "
            f"ReferenceData.fps={ref.fps!r}. Downstream `1.0 / fps` "
            f"produces NaN, poisoning DTW phase timing and time-derived "
            f"metrics (airtime, rotation speed, GOE proxy). The fix "
            f"must guard float(data[...]) with np.isfinite."
        )


# --------------------------------------------------------------------------- #
# Regression guard: valid finite .npz must pass through unchanged — the
# fix must not alter the valid path.
# --------------------------------------------------------------------------- #


def test_valid_npz_returns_finite_reference_data(tmp_path: Path):
    """Regression: clean finite .npz (written by ReferenceData.save
    itself) → ReferenceData with all finite fields, fps=30, phases
    start=0/takeoff=2/peak=4/landing=6/end=9. The fix must not alter
    the valid path."""
    ref = _load_valid(tmp_path)
    assert ref.fps == pytest.approx(30.0)
    assert ref.element_type == "waltz_jump"
    assert ref.name == "expert_waltz"
    assert math.isfinite(ref.fps)
    assert ref.phases.start == 0
    assert ref.phases.takeoff == 2
    assert ref.phases.peak == 4
    assert ref.phases.landing == 6
    assert ref.phases.end == 9
    assert ref.phases.name == "waltz_jump"
    assert ref.poses.shape == (10, 17, 2)
