"""RED repro: SubtitleParser._parse_caption IndexError on 'одиночный' (single jump).

subtitles.py:200 — count_patterns первые 3 (одиночн/двойн/тройн) БЕЗ capture group;
elif match.group(1) raises IndexError when 'одиночн' matched and text has no
двойн/тройн. parse_vtt aborts → весь subtitle-phase-extraction crash для любого
caption со словом 'одиночный' (частое Russian skating coaching narration).
"""

from pathlib import Path

from src.utils.subtitles import SubtitleParser


def test_subtitle_single_jump_no_indexerror(tmp_path: Path) -> None:
    vtt = tmp_path / "c.vtt"
    vtt.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nодиночный аксель\n",
        encoding="utf-8",
    )
    parser = SubtitleParser()
    raised = False
    exc: Exception | None = None
    try:
        events = parser.parse_vtt(vtt)
    except IndexError as e:
        raised = True
        exc = e

    assert not raised, (
        f"BUG: subtitles.py _parse_caption IndexError 'no such group' on "
        f"'одиночный аксель' (single jump): {exc}. count_patterns первые 3 "
        f"(одиночн/двойн/тройн) БЕЗ capture group; elif match.group(1) вызывается "
        f"когда одиночн matched + нет двойн/тройн → match.group(1) raises. "
        f"parse_vtt aborts → весь subtitle-phase-extraction crash для любого "
        f"caption со словом 'одиночный' (частое coaching narration)."
    )

    # If it didn't crash, assert single jump parsed with count=1.
    assert events and len(events) >= 1
    assert events[0].count == 1, f"single jump count should be 1, got {events[0].count}"
