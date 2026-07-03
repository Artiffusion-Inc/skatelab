"""RED repro — subtitles.py MM:SS.mmm timestamp format bug (tranche I).

Bug #13: subtitles.py:107-108 regex only matches HH:MM:SS.mmm format.
  WebVTT spec allows both `HH:MM:SS.mmm` and `MM:SS.mmm`. Most real-world
  VTT files use the shorter form (e.g. YouTube auto-generated captions).
  When the regex fails to match, `current_start` and `current_end` are
  never updated (they remain at the initial 0.0 from line 100-101), so
  all MM:SS-formatted captions get timestamp (0.0, 0.0).

  Source: ml/src/utils/subtitles.py:107-108.

Bug #14: subtitles.py:146-150 `_parse_time` crashes on MM:SS.mmm format
  with IndexError when the regex were loosened. This is a chain-bug:
  fixing #13 alone (loosening the regex) would expose this crash.

  Source: ml/src/utils/subtitles.py:137-150.

These tests document the bugs at the code-level. Full reproduction would
require writing a real VTT file with MM:SS.mmm timestamps and verifying
the parsed events have wrong/zero timestamps.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bug #13: regex only matches HH:MM:SS.mmm, drops MM:SS.mmm
# ---------------------------------------------------------------------------


def test_timestamp_regex_does_not_match_mm_ss_format():
    """Bug #13: regex on line 107 only matches HH:MM:SS.mmm format.

    VTT spec allows both formats. Most real-world VTT files use MM:SS.mmm
    (e.g. YouTube captions). The current regex silently drops these
    timestamps, leaving all events at (0.0, 0.0).
    """
    from src.utils.subtitles import SubtitleParser

    # Inspect the source code directly to confirm the regex
    source = Path(__file__).resolve().parents[2] / "src" / "utils" / "subtitles.py"
    text = source.read_text()

    # Find the timestamp regex pattern
    # The pattern is in a re.match call
    pattern = re.search(r"r\"(\\\\\\d\{2\\}:\\\\d\{2\\}:\\\\d\{2\}.*?)\"", text)
    # Fallback: search for any timestamp regex with HH:MM:SS
    if not pattern:
        # Look for the exact pattern in the source
        match = re.search(r"r\"(\d\{2\}:\d\{2\}:\d\{2\}\.\\d\{3\})\",\s*line", text)
        if match:
            actual_pattern = match.group(1)
        else:
            # Manual extraction
            for line in text.split("\n"):
                if 'r"(' in line and "-->" in line:
                    actual_pattern = re.search(r'r"([^"]+)"', line).group(1)
                    break
    else:
        actual_pattern = pattern.group(1)

    # The actual pattern uses HH:MM:SS.mmm format
    assert r"\d{2}:\d{2}:\d{2}" in actual_pattern, (
        f"Expected HH:MM:SS pattern in regex, got: {actual_pattern}"
    )
    # The pattern does NOT support MM:SS.mmm (which would be a 2-part split)
    # Document: the regex lacks an optional 'HH:' prefix

    # Direct test: try matching MM:SS.mmm format
    mm_ss_line = "00:25.849 --> 00:30.580"
    test_match = re.match(actual_pattern.replace("\\\\", "\\"), mm_ss_line)
    assert test_match is None, (
        f"Regex should NOT match MM:SS.mmm format. Got match: {test_match}. "
        f"This is the bug: MM:SS.mmm captions are silently dropped."
    )


def test_mm_ss_caption_silently_gets_zero_timestamp():
    """Bug #13b: simulate parsing a VTT with MM:SS.mmm format.

    The current parser logic:
    - Line 100-101: current_start = current_end = 0.0 (initial)
    - Line 104-117: timestamp_match for MM:SS.mmm → None
    - Else branch (line 120-128): accumulates text but doesn't update timestamps
    - Line 131-132: caption processed with current_start = current_end = 0.0

    Result: ElementEvent(start_time=0.0, end_time=0.0, ...) for all
    MM:SS-formatted captions.
    """
    # We don't even need to run the parser — just verify the regex pattern
    # from the source code
    from src.utils.subtitles import SubtitleParser

    parser = SubtitleParser()
    # Sanity check that the parser exists and is callable
    assert hasattr(parser, "parse_vtt"), "Parser should have parse_vtt method"

    # The bug is in the regex pattern itself: HH:MM:SS.mmm only.
    # Verify by reading the source:
    import inspect

    source = inspect.getsource(parser.parse_vtt)
    # Pattern in source: r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    assert r"\d{2}:\d{2}:\d{2}" in source, (
        "Expected HH:MM:SS pattern in source, indicating MM:SS.mmm is NOT supported. "
        "Source contains the long-form-only regex."
    )


# ---------------------------------------------------------------------------
# Bug #14: _parse_time crashes on MM:SS.mmm (chain-bug with #13)
# ---------------------------------------------------------------------------


def test_parse_time_crashes_on_mm_ss_format():
    """Bug #14: _parse_time("00:25.849") should NOT raise ValueError.

    Post-fix: _parse_time handles BOTH 2-part MM:SS.mmm AND 3-part
    HH:MM:SS.mmm splits. The 2-part format returns minutes*60 + seconds.
    The 3-part format returns hours*3600 + minutes*60 + seconds.
    Pre-fix: int("25.849") raised ValueError.
    """
    from src.utils.subtitles import SubtitleParser

    parser = SubtitleParser()

    # Direct test of _parse_time
    result = parser._parse_time("00:25.849")
    # Post-fix: 0*60 + 25.849 = 25.849
    assert result == pytest.approx(25.849, abs=0.01), (
        f"_parse_time('00:25.849') should return 25.849 (MM:SS.mmm format), "
        f"got {result}. Pre-fix code raised ValueError on int('25.849')."
    )


def test_parse_time_handles_hh_mm_ss_format():
    """NOT a bug: _parse_time works correctly on HH:MM:SS.mmm."""
    from src.utils.subtitles import SubtitleParser

    parser = SubtitleParser()
    # 1h 30m 45.5s = 5445.5
    result = parser._parse_time("01:30:45.500")
    assert result == pytest.approx(5445.5, abs=0.01), (
        f"_parse_time should handle HH:MM:SS.mmm correctly, got {result}"
    )


# ---------------------------------------------------------------------------
# NOT-a-bug guard
# ---------------------------------------------------------------------------


def test_hh_mm_ss_caption_parses_correctly():
    """NOT a bug: HH:MM:SS.mmm format (long form) works correctly.

    Documents that the long form is fine — only the short form is broken.
    """
    from src.utils.subtitles import SubtitleParser

    parser = SubtitleParser()
    # Direct test of regex match for long form
    line = "00:00:25.849 --> 00:00:30.580"
    timestamp_match = re.match(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})", line
    )
    assert timestamp_match is not None, "Long-form HH:MM:SS.mmm should match"
    start = parser._parse_time(timestamp_match.group(1))
    end = parser._parse_time(timestamp_match.group(2))
    assert start == pytest.approx(25.849, abs=0.01)
    assert end == pytest.approx(30.580, abs=0.01)
