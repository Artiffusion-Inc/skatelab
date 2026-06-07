"""Load ISU scoring data from JSON files into Python dataclasses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003


@dataclass(frozen=True)
class SOVEntry:
    code: str
    base_value: float
    name: str
    rotations: float = 0.0
    has_toe_pick: bool = False
    modifiers: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class GOEScaleEntry:
    grade: int
    percentage: int
    label_ru: str
    description_ru: str


@dataclass(frozen=True)
class PositiveBullet:
    id: str
    number: int
    text_en: str
    text_ru: str
    required_for_plus4_plus5: bool


@dataclass(frozen=True)
class ErrorReduction:
    id: str
    text_ru: str
    goe_reduction: int | None = None
    goe_reduction_min: int | None = None
    goe_reduction_max: int | None = None
    mandatory: bool = False


@dataclass(frozen=True)
class GOERules:
    goe_scale: list[GOEScaleEntry]
    positive_bullets: list[PositiveBullet]
    error_reductions: list[ErrorReduction]
    rules: dict[str, bool]


@dataclass(frozen=True)
class DeductionDef:
    id: str
    penalty: float
    name_ru: str
    description_ru: str
    detectable: bool


@dataclass(frozen=True)
class PCSComponent:
    id: str
    abbreviation: str
    name_en: str
    name_ru: str
    max_score: float


@dataclass(frozen=True)
class PCSFactors:
    components: list[PCSComponent]
    factors: dict[str, float]


class ISULoader:
    """Load ISU data from JSON files."""

    def __init__(self, data_dir: Path, season: str) -> None:
        self._dir = data_dir
        self._season = season

    def _path(self, prefix: str) -> Path:
        p = self._dir / f"{prefix}_{self._season.replace('/', '_').replace('-', '_')}.json"
        if not p.exists():
            raise FileNotFoundError(f"ISU data not found: {p}")
        return p

    def _read(self, prefix: str) -> dict:
        with self._path(prefix).open() as f:
            return json.load(f)

    def load_sov(self) -> dict[str, SOVEntry]:
        data = self._read("sov")
        entries: dict[str, SOVEntry] = {}
        for section in (
            "jumps",
            "spins",
            "step_sequences",
            "choreo_sequences",
            "pair_throws",
            "pair_twists",
            "pair_lifts",
            "pair_death_spirals",
            "pair_sbs",
            "dance_patterns",
            "dance_twizzles",
            "dance_lifts",
            "dance_choreo",
        ):
            for code, info in data.get(section, {}).items():
                entries[code] = SOVEntry(
                    code=code,
                    base_value=info["base_value"],
                    name=info["name"],
                    rotations=info.get("rotations", 0.0),
                    has_toe_pick=info.get("has_toe_pick", False),
                    modifiers=info.get("modifiers", {}),
                )
        return entries

    def load_goe_rules(self) -> GOERules:
        data = self._read("goe_rules")
        scale = [GOEScaleEntry(**s) for s in data["goe_scale"]]
        bullets = [PositiveBullet(**b) for b in data["positive_bullets"]]
        reductions = [ErrorReduction(**r) for r in data["error_reductions"]]
        return GOERules(
            goe_scale=scale,
            positive_bullets=bullets,
            error_reductions=reductions,
            rules=data["rules"],
        )

    def load_deductions(self) -> list[DeductionDef]:
        data = self._read("deductions")
        return [DeductionDef(**d) for d in data["deductions"]]

    def load_pcs_factors(self) -> PCSFactors:
        data = self._read("pcs_factors")
        components = [PCSComponent(**c) for c in data["components"]]
        return PCSFactors(components=components, factors=data["factors"])
