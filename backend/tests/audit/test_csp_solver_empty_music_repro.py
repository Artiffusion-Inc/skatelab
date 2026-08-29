"""Regression test for #639 — csp_solver empty/short music collapses timestamps to 0.

Bug: when `duration = 0.0` (empty audio) or `duration < 5.0` (short clip),
`min(target_time, duration - 5.0)` produces a negative value, the rescue
clamp at line 308 forces everything to 0.0. Every element in every layout
ends up at timestamp=0.0.

Fix: guard at the top of `solve_layout`. When `duration` is missing,
non-positive, or below a sane minimum (5s), raise ValueError so the
caller surfaces a 400 to the user instead of persisting a degenerate
layout.
"""

import pytest
from app.services.choreography.csp_solver import solve_layout

_INVENTORY = {
    "jumps": ["3A", "3F", "3Lo", "2A", "2T"],
    "spins": ["CSp4", "LSp4"],
    "combinations": ["3A+2T"],
}


def _all_timestamps(layouts):
    """Flatten element timestamps across all returned layouts."""
    out = []
    for layout in layouts:
        for el in layout["elements"]:
            out.append(el["timestamp"])
    return out


def test_solve_layout_rejects_zero_duration():
    """duration=0.0 must raise, not collapse all timestamps to 0.0."""
    music_features = {"duration": 0.0, "peaks": [], "structure": []}
    with pytest.raises(ValueError, match="duration"):
        solve_layout(
            inventory=_INVENTORY,
            music_features=music_features,
            discipline="mens_singles",
            segment="free_skate",
        )


def test_solve_layout_rejects_missing_duration():
    """Missing duration key (None) must raise."""
    music_features = {"duration": None, "peaks": [], "structure": []}
    with pytest.raises(ValueError, match="duration"):
        solve_layout(
            inventory=_INVENTORY,
            music_features=music_features,
            discipline="mens_singles",
            segment="free_skate",
        )


def test_solve_layout_rejects_short_duration():
    """duration < 5s (the existing #465 lower-bound threshold) must raise."""
    music_features = {"duration": 3.0, "peaks": [], "structure": []}
    with pytest.raises(ValueError, match="duration"):
        solve_layout(
            inventory=_INVENTORY,
            music_features=music_features,
            discipline="mens_singles",
            segment="free_skate",
        )


def test_solve_layout_accepts_valid_short_program():
    """duration = 160s (short program) still works — no regression on the
    lower end after we add the floor."""
    music_features = {
        "duration": 160.0,
        "peaks": [10.0, 30.0, 60.0, 100.0],
        "structure": [],
    }
    layouts = solve_layout(
        inventory=_INVENTORY,
        music_features=music_features,
        discipline="mens_singles",
        segment="short_program",
    )
    assert len(layouts) >= 1
    timestamps = _all_timestamps(layouts)
    assert all(t >= 0.0 for t in timestamps), f"Negative timestamps leaked: {timestamps}"


def test_solve_layout_rejects_empty_music_dict():
    """An entirely-empty music_features dict uses the default duration=180.0
    and produces real layouts (not all-zero). Explicit duration=0 is the
    bug surface and must raise."""
    music_features = {}
    layouts = solve_layout(
        inventory=_INVENTORY,
        music_features=music_features,
        discipline="mens_singles",
        segment="free_skate",
    )
    assert len(layouts) >= 1
    timestamps = _all_timestamps(layouts)
    distinct = set(timestamps)
    assert len(distinct) > 1 or all(t > 0.0 for t in timestamps), (
        f"All elements collapsed to single timestamp: {timestamps}"
    )
