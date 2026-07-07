"""ISU deduction definitions with auto-detection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.choreography.isu_loader import DeductionDef, ISULoader

DATA_DIR = Path(settings.app.data_dir) / "isu"

_loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
ALL_DEDUCTIONS: list[DeductionDef] = _loader.load_deductions()
DETECTABLE_DEDUCTIONS: list[DeductionDef] = [d for d in ALL_DEDUCTIONS if d.detectable]


@dataclass
class DetectedDeduction:
    deduction: DeductionDef
    confidence: float
    evidence: str


def detect_deductions(metrics: dict[str, float]) -> list[DetectedDeduction]:
    """Detect applicable deductions from biomechanical metrics."""
    results: list[DetectedDeduction] = []

    # Fall detection: hard impact + unstable landing. compute_hard_landing scale
    # is 1.0 = soft, 0.0 = very hard (metrics.py:990), so a fall is LOW hard_landing
    # (hard impact) + LOW landing_smoothness — not a soft landing. See #421.
    smoothness = metrics.get("landing_smoothness", 1.0)
    hard_landing = metrics.get("hard_landing", 1.0)
    # NaN/inf on either metric must NOT silently skip the fall branch via
    # `NaN < X == False` — that's a safety miss (real fall hidden as no
    # fall). #1230: guard both with math.isfinite before the threshold.
    if (
        math.isfinite(smoothness)
        and math.isfinite(hard_landing)
        and smoothness < 0.05
        and hard_landing < 0.1
    ):
        fall_def = next((d for d in DETECTABLE_DEDUCTIONS if d.id == "fall"), None)
        if fall_def:
            results.append(
                DetectedDeduction(
                    deduction=fall_def,
                    confidence=0.9 if hard_landing < 0.05 else 0.7,
                    evidence=f"landing_smoothness={smoothness:.2f}, hard_landing={hard_landing:.2f}",
                )
            )

    return results
