"""RED repro — music_analyzer._compute_energy_peaks crashes on NaN sr.

Bug: backend/app/services/choreography/music_analyzer.py:42
    hop_length = int(sr * 0.5)

If `sr` is NaN (corrupt audio meta / upstream NaN propagation),
`int(NaN) = ValueError: cannot convert float NaN to integer`, aborting
the entire energy peaks computation, then the entire music analysis
pipeline (choreography planner, BPM, segmenter).

Root cause: no `math.isfinite(sr)` guard before the int() conversion.
Fix (per issue #1213): add isfinite guard; if sr is non-finite, return
empty peaks + empty energy_curve so downstream code degrades gracefully.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MUSIC_ANALYZER_PATH = BACKEND_ROOT / "app" / "services" / "choreography" / "music_analyzer.py"


def _load_source() -> str:
    return MUSIC_ANALYZER_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-level guard: root cause must be locked in code.
# ---------------------------------------------------------------------------


def test_source_guards_int_conversion_with_isfinite():
    """`_compute_energy_peaks` must use math.isfinite(sr) before int(sr*0.5)."""
    src = _load_source()
    # Locate the hop_length line
    match = re.search(r"hop_length\s*=\s*int\(sr\s*\*\s*0\.5\)", src)
    assert match is not None, (
        "expected `hop_length = int(sr * 0.5)` in music_analyzer._compute_energy_peaks"
    )

    # Look at the function body surrounding the hop_length line.
    # The text BEFORE this line (within the same function) must reference
    # math.isfinite to ensure non-finite sr (NaN/inf) is filtered out.
    surrounding = src[max(0, match.start() - 800) : match.end() + 200]
    assert "math.isfinite" in surrounding, (
        "music_analyzer._compute_energy_peaks must guard `int(sr * 0.5)` with "
        "math.isfinite(sr); otherwise NaN sr crashes the entire energy peaks "
        "computation (#1213)."
    )


# ---------------------------------------------------------------------------
# Observable behavior: NaN / inf sr must not raise, must yield empty result.
# ---------------------------------------------------------------------------


def _build_mock_msaf() -> MagicMock:
    """Build a mock msaf module that returns empty structure on .process()."""
    mock_msaf = MagicMock()
    mock_msaf.process = MagicMock(side_effect=RuntimeError("not installed"))
    return mock_msaf


def test_nan_sr_does_not_crash():
    """NaN sr must not crash the energy peaks path (#1213).

    We patch librosa.load to return NaN sr, and patch librosa.beat.beat_track
    and msaf.process so the only function actually touching sr is the one we
    are testing: _compute_energy_peaks.
    """
    from app.services.choreography import music_analyzer

    fake_y = np.zeros(22050, dtype=np.float32)
    with (
        patch("librosa.load", return_value=(fake_y, float("nan"))),
        patch("librosa.beat.beat_track", return_value=(120.0, None)),
        patch.dict("sys.modules", {"msaf": _build_mock_msaf()}),
    ):
        result = music_analyzer.analyze_music_sync("/fake/path.wav")

    # Energy peaks must be empty (degraded gracefully) — not missing
    assert result["peaks"] == []
    assert result["energy_curve"] == {"timestamps": [], "values": []}
    # BPM still gets reported (mocked)
    assert result["bpm"] == 120.0


def test_inf_sr_does_not_crash():
    """inf sr must not crash the energy peaks path (#1213)."""
    from app.services.choreography import music_analyzer

    fake_y = np.zeros(22050, dtype=np.float32)
    with (
        patch("librosa.load", return_value=(fake_y, float("inf"))),
        patch("librosa.beat.beat_track", return_value=(120.0, None)),
        patch.dict("sys.modules", {"msaf": _build_mock_msaf()}),
    ):
        result = music_analyzer.analyze_music_sync("/fake/path.wav")

    assert result["peaks"] == []
    assert result["energy_curve"] == {"timestamps": [], "values": []}


def test_nan_via_inf_times_zero_does_not_crash():
    """nan derived from inf*0 (a common NaN source) must not crash."""
    from app.services.choreography import music_analyzer

    fake_y = np.zeros(22050, dtype=np.float32)
    nan_sr = float("inf") * 0.0  # → NaN
    assert math.isnan(nan_sr)
    with (
        patch("librosa.load", return_value=(fake_y, nan_sr)),
        patch("librosa.beat.beat_track", return_value=(120.0, None)),
        patch.dict("sys.modules", {"msaf": _build_mock_msaf()}),
    ):
        result = music_analyzer.analyze_music_sync("/fake/path.wav")

    assert result["peaks"] == []
    assert result["energy_curve"] == {"timestamps": [], "values": []}


# ---------------------------------------------------------------------------
# Regression: valid sr must still produce a positive int hop_length.
# ---------------------------------------------------------------------------


def test_valid_sr_still_produces_int_hop_length():
    """A finite sr must still feed librosa.feature.rms with a positive int hop_length.

    Regression guard: the fix must not break the happy path. We assert the
    source still has `int(sr * 0.5)` as the formula (so the fix wraps it,
    not removes it).
    """
    src = _load_source()
    assert "int(sr * 0.5)" in src, (
        "fix should wrap int(sr * 0.5) with isfinite guard, not remove the formula"
    )
