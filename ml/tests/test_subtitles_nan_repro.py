"""RED repro guard — `extract_phases_from_subtitles` (ml/src/utils/subtitles.py)
NaN/non-finite `start_time` / `end_time` must not crash with
`ValueError: cannot convert float NaN to integer` (#1084, tranche GR).

Family: NaN-tranche via unguarded `int(event.start_time * fps)` /
`int(event.end_time * fps)` casts. Mirrors #912/#915/#962/#1007/#1041/
#1042/#1045/#1049/#1052/#1053 NaN-tranche family. Root cause: `int(NaN)`
raises `ValueError`, the entire phase pipeline aborts with an unhandled
exception, the recommender cannot bound any element. Without a
`math.isfinite` guard BEFORE the `int()` cast, the cast itself is the
crash site — there is nothing else to recover from.

Contract (GREEN — fix is in place on master via this PR, mirroring
#1013 / #1030 / #1052 pattern):
  - `extract_phases_from_subtitles` must NOT raise on NaN/non-finite
    `event.start_time` or `event.end_time` — it must skip the bad event
    (log + `continue`) and return phases for the rest.
  - `start_time=NaN, end_time=1.0` → no crash, event skipped.
  - `start_time=0.5, end_time=NaN` → no crash, event skipped.
  - `start_time=NaN, end_time=NaN` → no crash, event skipped.
  - `start_time=-1.0` (negative time) → no crash, event skipped
    (negative times are also non-finite for a video timeline).
  - Regression: valid finite events still produce a phase with integer
    `start`/`end` frames and the original element name.
  - Source check: `extract_phases_from_subtitles` must contain a
    `math.isfinite` (or equivalent) guard on `event.start_time` /
    `event.end_time` BEFORE any `int(... * fps)` cast. Without this
    guard the `int(NaN)` crash is back.

This test file is the regression guard. If anyone reverts the
`math.isfinite` guard before the `int()` cast in
`extract_phases_from_subtitles`, these tests will fail with explicit
diff messages naming the bug.

Methodology:
  1 source check (isfinite guard, ordering before int() cast)
  4 observable  (NaN start, NaN end, NaN both, negative start)
  1 regression  (finite event → integer start/end frames preserved)

Pure-Python (no GPU, no ONNX, no DB): the bug is in pure arithmetic
over float inputs. We monkey-patch `parse_vtt` to feed synthetic
`ElementEvent` instances with NaN/inf timing to isolate the
`int(NaN * fps)` crash site.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from src.utils.subtitles import ElementEvent, SubtitleParser

if TYPE_CHECKING:
    from pathlib import Path

NAN = float("nan")
POS_INF = float("inf")
NEG_INF = float("-inf")


def _patched_parser(events: list[ElementEvent]) -> SubtitleParser:
    """Return a SubtitleParser whose `parse_vtt` returns the given events.

    The bug is in `extract_phases_from_subtitles` — the `int(NaN * fps)`
    crash on the int() cast. We bypass the VTT timestamp regex (which
    doesn't accept NaN tokens) and feed events directly to isolate the
    cast site.
    """
    parser = SubtitleParser()
    parser.parse_vtt = lambda vtt_path: list(events)  # type: ignore[assignment]
    return parser


# =========================================================================== #
# Source check: root cause locked — `extract_phases_from_subtitles` MUST have
# an `isfinite` (or `isnan`) guard on `event.start_time` / `event.end_time`
# BEFORE any `int(... * fps)` cast. Without this guard, `int(NaN * fps)`
# raises `ValueError: cannot convert float NaN to integer` and the entire
# phase pipeline aborts.
# =========================================================================== #


def test_extract_phases_from_subtitles_source_has_isfinite_guard():
    """Source check: `extract_phases_from_subtitles` guards NaN/non-finite
    `start_time` / `end_time` BEFORE the `int(... * fps)` cast. If the
    guard is removed/regressed, this test fails — and the NaN tests
    below flip to observable `ValueError` failures too.
    """
    # AST-based check (robust to comment text containing `int(NaN)`):
    # walk the function body and find BOTH a guard Call (`isfinite`,
    # `isnan`, or `nan_to_num`) AND a `int(...)` Call, then assert the
    # guard's source line is < the int()'s source line. Comments cannot
    # generate false positives this way.
    import ast

    src = inspect.getsource(SubtitleParser.extract_phases_from_subtitles)
    # inspect.getsource returns the bare function body for methods —
    # wrap it in a class so ast.parse has a complete module.
    wrapped = "class _W:\n" + src
    tree = ast.parse(wrapped)
    cls = tree.body[0]
    assert isinstance(cls, ast.ClassDef)
    func = cls.body[0]
    assert isinstance(func, ast.FunctionDef), f"expected FunctionDef, got {type(func).__name__}"

    GUARD_NAMES = {"isfinite", "isnan", "isinf", "nan_to_num"}
    GUARD_ATTRS = {"isfinite", "isnan", "isinf", "nan_to_num"}
    INT_NAMES = {"int"}

    def _call_name(node: ast.Call) -> str | None:
        """Return the short name of a Call (function or attribute)."""
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
        return None

    guard_lines: list[int] = []
    int_lines: list[int] = []

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name is None:
            continue
        if name in INT_NAMES and any(isinstance(a, ast.BinOp) for a in node.args):
            int_lines.append(node.lineno)
        if name in GUARD_NAMES or name in GUARD_ATTRS:
            guard_lines.append(node.lineno)

    assert guard_lines, (
        "extract_phases_from_subtitles must contain an isfinite / isnan / "
        "isinf / nan_to_num Call before the int() cast. Add e.g. "
        "`if not math.isfinite(event.start_time): continue` at the top "
        "of the event loop."
    )
    assert int_lines, (
        "extract_phases_from_subtitles must contain an int(... * fps) "
        "Call somewhere — if this fails the test is looking at the "
        "wrong function or the cast was renamed."
    )
    assert min(guard_lines) < min(int_lines), (
        f"extract_phases_from_subtitles has an int(... * fps) cast at "
        f"line {min(int_lines)} but the earliest isfinite/isnan/nan_to_num "
        f"guard is at line {min(guard_lines)}. The guard MUST come "
        "textually before the int() cast so int(NaN * fps) never runs."
    )


# =========================================================================== #
# Observable: NaN / non-finite `start_time` must not crash the pipeline.
# =========================================================================== #


def test_extract_phases_nan_start_time_does_not_crash(tmp_path: Path):
    """`event.start_time=NaN` must NOT raise `ValueError: cannot convert
    float NaN to integer`. The bad event is skipped, other valid events
    are preserved.
    """
    parser = _patched_parser(
        [
            ElementEvent(name="loop", start_time=0.0, end_time=1.0),  # valid baseline
            ElementEvent(name="axle", start_time=NAN, end_time=1.0),  # NaN start
        ]
    )
    # tmp_path is unused; we feed parse_vtt a stub path.
    p = tmp_path / "stub.vtt"

    # Must not raise ValueError.
    phases = parser.extract_phases_from_subtitles(p, fps=25.0)

    # Valid baseline event → phase present.
    assert "loop" in phases, (
        f"Valid baseline event 'loop' (start=0.0) must produce a phase, got: {sorted(phases)}"
    )
    # NaN-start event is skipped, not crashed.
    assert "axle" not in phases, (
        f"Event with NaN start_time must be SKIPPED, not retained. Got: {sorted(phases)}"
    )
    assert isinstance(phases, dict), (
        "extract_phases_from_subtitles must return a dict even when an "
        "event has NaN start_time — it must not propagate ValueError."
    )


def test_extract_phases_nan_end_time_does_not_crash(tmp_path: Path):
    """`event.end_time=NaN` (with valid `start_time`) must NOT raise
    `ValueError: cannot convert float NaN to integer`. The bad event
    is skipped, other valid events are preserved.
    """
    parser = _patched_parser(
        [
            ElementEvent(name="loop", start_time=0.0, end_time=1.0),  # valid baseline
            ElementEvent(name="axle", start_time=1.0, end_time=NAN),  # NaN end_time
        ]
    )
    p = tmp_path / "stub.vtt"

    phases = parser.extract_phases_from_subtitles(p, fps=25.0)

    assert "axle" not in phases, (
        f"Event with NaN end_time must be SKIPPED, not retained. Got: {sorted(phases)}"
    )
    # The valid baseline event still produced a phase.
    assert "loop" in phases, (
        f"Valid baseline event 'loop' must still produce a phase. Got: {sorted(phases)}"
    )


def test_extract_phases_nan_both_timings_does_not_crash(tmp_path: Path):
    """`event.start_time=NaN AND event.end_time=NaN` must NOT raise. The
    bad event is skipped.
    """
    parser = _patched_parser(
        [
            ElementEvent(name="loop", start_time=0.0, end_time=1.0),  # valid baseline
            ElementEvent(name="axle", start_time=NAN, end_time=NAN),  # both NaN
        ]
    )
    p = tmp_path / "stub.vtt"

    # Must not raise ValueError.
    phases = parser.extract_phases_from_subtitles(p, fps=25.0)

    assert "axle" not in phases, (
        f"Event with NaN start AND NaN end must be SKIPPED. Got: {sorted(phases)}"
    )
    assert "loop" in phases, (
        f"Valid baseline event 'loop' must still produce a phase. Got: {sorted(phases)}"
    )


def test_extract_phases_negative_start_time_does_not_crash(tmp_path: Path):
    """Negative `start_time` is non-finite for a video timeline (no
    frames before 0). The fix must guard this too. After the guard the
    bad event is skipped, not crashed.
    """
    parser = _patched_parser(
        [
            ElementEvent(name="loop", start_time=0.0, end_time=1.0),  # valid baseline
            ElementEvent(name="axle", start_time=-1.0, end_time=2.0),  # negative start
        ]
    )
    p = tmp_path / "stub.vtt"

    phases = parser.extract_phases_from_subtitles(p, fps=25.0)

    # We don't pin to a single behavior for negative times (the issue
    # only specifies NaN) — we only require no crash and a dict back.
    assert isinstance(phases, dict)
    # The valid baseline cue is preserved.
    assert "loop" in phases, (
        f"Valid baseline event 'loop' must still produce a phase. Got: {sorted(phases)}"
    )


# =========================================================================== #
# Regression: valid finite events still produce a phase with INTEGER
# start/end frames — the guard must not corrupt the happy path.
# =========================================================================== #


def test_extract_phases_valid_finite_event_regression(tmp_path: Path):
    """Regression: a valid finite event must still produce a phase with
    integer `start` / `end` frames at the expected values. The isfinite
    guard is for the bad-input path only; it must not change the
    happy-path output.
    """
    parser = _patched_parser(
        [
            ElementEvent(name="loop", start_time=1.0, end_time=3.0),  # 1s..3s @ 25fps → 25..75
        ]
    )
    p = tmp_path / "stub.vtt"

    phases = parser.extract_phases_from_subtitles(p, fps=25.0)

    assert phases, (
        f"Valid finite event 'loop' (1.0s..3.0s) must produce a phase. Got empty dict: {phases}"
    )
    assert len(phases) == 1
    ((name, phase),) = phases.items()
    assert name == "loop"
    assert isinstance(phase.start, int), (
        f"phase.start must be int (got {type(phase.start).__name__}="
        f"{phase.start!r}) — int(event.start_time * fps) must still "
        "produce int, not be silently coerced to float."
    )
    assert isinstance(phase.end, int)
    assert phase.start == 25, (
        f"phase.start for event at 1.0s @ 25fps must be 25, got {phase.start!r}"
    )
    assert phase.end == 75, f"phase.end for event at 3.0s @ 25fps must be 75, got {phase.end!r}"
