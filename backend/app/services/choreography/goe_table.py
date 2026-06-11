"""ISU GOE scale table — loaded from data/isu/goe_rules JSON."""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services.choreography.isu_loader import (
    ErrorReduction,
    GOERules,
    GOEScaleEntry,
    ISULoader,
    PositiveBullet,
)

DATA_DIR = Path(settings.app.data_dir) / "isu"

_loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
GOE_RULES: GOERules = _loader.load_goe_rules()
GOE_SCALE: dict[int, GOEScaleEntry] = {e.grade: e for e in GOE_RULES.goe_scale}
POSITIVE_BULLETS: list[PositiveBullet] = GOE_RULES.positive_bullets
ERROR_REDUCTIONS: list[ErrorReduction] = GOE_RULES.error_reductions
