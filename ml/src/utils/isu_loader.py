"""ISU SOV data loader for ML pipeline and GPU server.

Reads data/isu/sov_*.json files. Pure read-only, no dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "isu"


def load_sov_entry(isu_code: str, season: str = "2025-26") -> dict | None:
    """Load SOV entry for an ISU code.

    Returns dict with keys: base_value, name, rotations, has_toe_pick,
    modifiers (dict), level (for spins), etc.
    Returns None if not found or file missing.
    """
    sov_path = _DATA_DIR / f"sov_{season.replace('/', '_')}.json"
    if not sov_path.exists():
        return None
    try:
        with sov_path.open() as f:
            sov = json.load(f)
        for section in ("jumps", "spins", "step_sequences", "choreo_sequences"):
            entry = sov.get(section, {}).get(isu_code)
            if entry:
                result = dict(entry)
                result["section"] = section
                return result
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    return None
