"""RED repro — score_calculator NaN GOE silently clamps to +5 (#638).

backend/app/services/choreography/score_calculator.py:
    def calculate_element_score(base_value: float, goe: int) -> float:
        clamped = max(-5, min(5, goe))
        return base_value * (1 + clamped * 0.10)

`goe = float('nan')` → `min(5, NaN)` returns `5` (Python's min ignores
NaN in comparison), `max(-5, 5) = 5` → returns base_value * 1.5.

NaN GOE should NOT produce a +5 score. Filter at function entry, return
0.0 for non-finite GOE (or treat as no-bonus; 0 is safest).
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCORE_PATH = BACKEND_ROOT / "app" / "services" / "choreography" / "score_calculator.py"


def _load():
    spec = importlib.util.spec_from_file_location("_score_under_test", SCORE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_source_rejects_nan_goe_at_entry():
    src = SCORE_PATH.read_text(encoding="utf-8")
    assert "import math" in src, "score_calculator.py must `import math` (#638)"
    block_start = src.find("def calculate_element_score(")
    assert block_start != -1, "expected `calculate_element_score` function"
    next_def = src.find("\ndef ", block_start + 1)
    block = src[block_start:next_def] if next_def != -1 else src[block_start:]
    assert "math.isfinite" in block, (
        f"calculate_element_score must guard on math.isfinite(goe) at entry. Block:\n{block}"
    )


def test_score_calculator_nan_goe_does_not_clamps_to_5():
    mod = _load()
    score = mod.calculate_element_score(10.0, float("nan"))
    # Pre-fix: 10.0 * (1 + 5 * 0.10) = 15.0  ← BUG
    # Post-fix: 0.0 (NaN rejected, no bonus)
    assert math.isfinite(score), f"NaN GOE must not produce a +5 score, got {score!r}"
    assert score != pytest.approx(15.0), (
        f"NaN GOE produced +5 score (15.0 for base=10). Must reject NaN at entry. Got {score!r}"
    )


def test_score_calculator_inf_goe_rejected():
    mod = _load()
    score = mod.calculate_element_score(10.0, float("inf"))
    assert math.isfinite(score), f"+inf GOE must not clamp to +5, got {score!r}"
    score_neg = mod.calculate_element_score(10.0, float("-inf"))
    assert math.isfinite(score_neg), f"-inf GOE must not clamp to -5, got {score_neg!r}"


def test_score_calculator_normal_goe_unchanged():
    """Control: finite GOE in [-5, 5] must still produce expected score."""
    mod = _load()
    # GOE 0 → base * 1.0
    assert mod.calculate_element_score(10.0, 0) == pytest.approx(10.0)
    # GOE +3 → base * 1.3
    assert mod.calculate_element_score(10.0, 3) == pytest.approx(13.0)
    # GOE -3 → base * 0.7
    assert mod.calculate_element_score(10.0, -3) == pytest.approx(7.0)
    # GOE +5 → base * 1.5
    assert mod.calculate_element_score(10.0, 5) == pytest.approx(15.0)
    # GOE -5 → base * 0.5
    assert mod.calculate_element_score(10.0, -5) == pytest.approx(5.0)


def test_score_calculator_out_of_range_clamps_normally():
    """GOE > 5 or < -5 must still clamp to ±5 (preserved behavior)."""
    mod = _load()
    assert mod.calculate_element_score(10.0, 7) == pytest.approx(15.0)  # clamp to 5
    assert mod.calculate_element_score(10.0, -7) == pytest.approx(5.0)  # clamp to -5
