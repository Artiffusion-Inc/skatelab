"""Extended types for skating analyzer multi-dimensional scoring and phase detection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubScore:
    """A single dimension of the multi-dimensional score."""
    name: str
    label_ru: str
    value: float  # 0-10
    confidence: float  # 0-1
    contributing_metrics: list[str] = field(default_factory=list)


@dataclass
class MultiDimensionalScore:
    """Composite score across 5 dimensions."""
    subscores: list[SubScore] = field(default_factory=list)
    overall: float = 0.0
    data_quality: str = "good"  # good | partial | poor
    skeleton_reliability: str = "reliable"  # reliable | uncertain | likely_wrong


@dataclass
class PhaseExtended:
    """A single phase in the extended 5-phase model."""
    name: str  # approach | takeoff | air | landing | glide_out
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    confidence: float  # 0-1
    detection_method: str  # com_parabola | tas_segment | heuristic


@dataclass
class PhaseDetectionResultV2:
    """Result of extended 5-phase detection with confidence."""
    phases: list[PhaseExtended] = field(default_factory=list)
    overall_confidence: float = 0.0
    element_type: str | None = None
    fallback_used: bool = False


@dataclass
class TrainingPlanItem:
    """A single training exercise."""
    id: str
    priority: int
    label_ru: str
    description_ru: str
    completed: bool = False


@dataclass
class TrainingPlan:
    """AI-generated training plan from weakest subscores."""
    items: list[TrainingPlanItem] = field(default_factory=list)
    generated_at: str = ""
    completed: bool = False
    focus_subscore: str | None = None