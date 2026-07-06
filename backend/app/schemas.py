"""Pydantic schemas for the web API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    value: Any


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict | list[ValidationErrorDetail] | None = None
    path: str = ""


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    bio: str | None
    height_cm: int | None
    weight_kg: float | None
    language: str
    timezone: str
    theme: str
    angular_unit: str = "deg_per_sec"
    onboarding_role: str | None
    is_active: bool
    is_verified: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        # #674: None guard — NULL timestamp must not become "None" string.
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = None
    height_cm: int | None = Field(default=None, ge=50, le=250)
    weight_kg: float | None = Field(default=None, ge=20, le=300)


class UpdateSettingsRequest(BaseModel):
    language: str | None = Field(default=None, max_length=10)
    timezone: str | None = Field(default=None, max_length=50)
    theme: str | None = Field(default=None, pattern=r"^(light|dark|system)$")
    angular_unit: str | None = Field(default=None, pattern=r"^(deg_per_sec|rpm)$")


class UpdateOnboardingRoleRequest(BaseModel):
    onboarding_role: str = Field(pattern=r"^(skater|coach|choreographer)$")


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=1000)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    avatar_url: str | None
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class WorkspaceMemberResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    role: str
    joined_at: str
    invited_by: str | None
    user_name: str | None = None
    user_email: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("joined_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern=r"^(admin|coach|student|parent)$")


class SubscriptionResponse(BaseModel):
    id: str
    workspace_id: str
    plan: str
    status: str
    seats: int | None
    max_seats: int | None
    trial_ends_at: str | None
    current_period_start: str | None
    current_period_end: str | None

    model_config = {"from_attributes": True}

    @field_validator("trial_ends_at", "current_period_start", "current_period_end", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


# ---------------------------------------------------------------------------
# Detect & Process
# ---------------------------------------------------------------------------


class PersonInfo(BaseModel):
    track_id: int
    hits: int
    bbox: list[float]
    mid_hip: list[float]


class PersonClick(BaseModel):
    x: int
    y: int


class DetectResponse(BaseModel):
    persons: list[PersonInfo]
    preview_image: str
    video_key: str
    auto_click: PersonClick | None = None
    status: str


@dataclass
class MLModelFlags:
    """ML model feature flags for video processing."""

    lift_3d: bool = True
    optical_flow: bool = False
    segment: bool = False
    foot_track: bool = False
    matting: bool = False
    inpainting: bool = False


class DetectQueueResponse(BaseModel):
    task_id: str
    video_key: str
    status: str = "pending"


class DetectResultResponse(BaseModel):
    persons: list[PersonInfo]
    preview_image: str
    video_key: str
    auto_click: PersonClick | None = None
    status: str


class ProcessRequest(BaseModel):
    video_key: str
    person_click: PersonClick
    frame_skip: int = 1
    tracking: str = "auto"
    session_id: str | None = None
    lift_3d: bool = Field(default=True, validation_alias="depth")
    optical_flow: bool = False
    segment: bool = False
    foot_track: bool = False
    matting: bool = False
    inpainting: bool = False

    model_config = ConfigDict(populate_by_name=True)


class ProcessStats(BaseModel):
    total_frames: int
    valid_frames: int
    fps: float
    resolution: str


class ProcessResponse(BaseModel):
    video_path: str
    poses_path: str | None
    csv_path: str | None
    stats: ProcessStats
    status: str


class QueueProcessResponse(BaseModel):
    task_id: str
    status: str = "pending"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    message: str
    result: ProcessResponse | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    element_type: str | None = Field(default=None, max_length=50)
    video_key: str | None = Field(default=None, max_length=500)
    imu_left_key: str | None = Field(default=None, max_length=500)
    imu_right_key: str | None = Field(default=None, max_length=500)
    manifest_key: str | None = Field(default=None, max_length=500)
    isu_code: str | None = None


# Status values the system actually writes to Session.status:
#   uploading  — default (session created without video_key)
#   queued     — session created with video_key / retry flow (client-settable)
#   completed  — worker wrote pose data but no metrics (crud.update_session_analysis)
#   done       — worker wrote metrics (canonical terminal for metrics filters)
#   deleted    — soft delete (system only)
# Terminal statuses (completed, done, deleted) are worker/system-only: a client
# must never set them via PATCH — that would bypass the ML pipeline and let a
# never-analyzed session pollute PR/trend/diagnostics filters.
SESSION_STATUS_WHITELIST = frozenset(
    {"uploading", "queued", "completed", "done", "failed", "deleted"}
)
# Statuses a client may set directly via PATCH /sessions/{id}. Terminal/worker-only
# statuses are excluded — only the worker may transition a session to them.
CLIENT_SETTABLE_STATUSES = frozenset({"uploading", "queued"})


class PatchSessionRequest(BaseModel):
    element_type: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=20)
    process_task_id: str | None = Field(default=None, max_length=50)
    isu_code: str | None = None


class SessionMetricResponse(BaseModel):
    id: str
    metric_name: str
    metric_value: float
    is_pr: bool
    prev_best: float | None
    reference_value: float | None
    is_in_range: bool | None

    model_config = {"from_attributes": True}


class ElementSegmentResponse(BaseModel):
    id: str
    element_type: str
    element_name: str | None = None
    start_frame: int
    end_frame: int
    confidence: float
    phases_json: dict | None = None

    model_config = {"from_attributes": True}


class TimelineData(BaseModel):
    segments: list[ElementSegmentResponse]
    segmentation_confidence: float | None = None
    segmentation_status: str = "pending"


# Pose and metrics data types (Task 10, 2026-04-16)


class PoseData(BaseModel):
    """Sampled pose data for frontend visualization.

    Frames are sampled (e.g., every 10th frame) to reduce data transfer.
    poses shape: (N_sampled, 17, 3) where 17 = H3.6M keypoints, 3 = (x, y, conf)
    """

    frames: list[int]  # Sampled frame indices
    poses: list[list[list[float]]]  # [frame][keypoint][x,y,conf]
    fps: float  # Video frame rate


class FrameMetrics(BaseModel):
    """Frame-by-frame biomechanics metrics.

    All arrays are aligned with the frames list in PoseData.
    null values indicate metric could not be computed for that frame.
    """

    knee_angles_r: list[float | None]
    knee_angles_l: list[float | None]
    hip_angles_r: list[float | None]
    hip_angles_l: list[float | None]
    trunk_lean: list[float | None]
    com_height: list[float | None]


class PhasesData(BaseModel):
    """Phase markers for element segmentation.

    Frame indices are relative to the original video, not sampled frames.
    """

    takeoff: int | None = None
    peak: int | None = None
    landing: int | None = None


class SessionResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    element_type: str | None
    video_key: str | None = None
    video_url: str | None
    processed_video_key: str | None = None
    processed_video_url: str | None
    poses_url: str | None  # Deprecated: Replaced by pose_data
    csv_url: str | None  # Deprecated: Replaced by frame_metrics
    pose_data: PoseData | None  # New: Typed pose data storage (JSON)
    frame_metrics: FrameMetrics | None  # New: Typed frame metrics (JSON)
    status: str
    error_message: str | None
    phases: PhasesData | None  # Typed phase markers
    recommendations: list[str] | None
    overall_score: float | None
    process_task_id: str | None
    imu_left_key: str | None = None
    imu_right_key: str | None = None
    manifest_key: str | None = None
    isu_code: str | None = None
    created_at: str
    processed_at: str | None
    timeline: TimelineData | None = None
    segmentation_status: str = "pending"
    metrics: list[SessionMetricResponse] = []
    goe_grade: GOEResponse | None = None

    model_config = {"from_attributes": True}

    @field_validator("created_at", "processed_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class PaginatedResponse(BaseModel):
    """Base for all paginated list responses."""

    total: int
    page: int = 1
    page_size: int = 20
    pages: int = 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int
    next_cursor: str | None = None
    has_more: bool = False


# ---------------------------------------------------------------------------
# Metrics & Progress
# ---------------------------------------------------------------------------


class TrendDataPoint(BaseModel):
    date: str
    value: float
    session_id: str
    is_pr: bool


class TrendResponse(BaseModel):
    metric_name: str
    element_type: str
    data_points: list[TrendDataPoint]
    trend: str  # improving | stable | declining
    current_pr: float | None
    reference_range: dict[str, float] | None


class DiagnosticsFinding(BaseModel):
    severity: str
    element: str
    metric: str
    message: str
    detail: str


class DiagnosticsResponse(BaseModel):
    user_id: str
    findings: list[DiagnosticsFinding]


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    to_user_email: str
    connection_type: str = Field(pattern=r"^(coaching|choreography)$")


class ConnectionResponse(BaseModel):
    id: str
    from_user_id: str
    to_user_id: str
    connection_type: str
    status: str
    initiated_by: str | None
    created_at: str
    ended_at: str | None
    from_user_name: str | None = None
    to_user_name: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("created_at", "ended_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class ConnectionListResponse(PaginatedResponse):
    connections: list[ConnectionResponse]


# ---------------------------------------------------------------------------
# Choreography
# ---------------------------------------------------------------------------


class MusicAnalysisResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    filename: str
    audio_url: str
    duration_sec: float
    bpm: float | None
    meter: str | None
    structure: list[dict] | None
    energy_curve: dict | None
    downbeats: list[float] | None
    peaks: list[float] | None
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class UploadMusicResponse(BaseModel):
    music_id: str
    filename: str


class GenerateRequest(BaseModel):
    music_id: str
    discipline: str = Field(pattern=r"^(mens_singles|womens_singles)$")
    segment: str = Field(pattern=r"^(short_program|free_skate)$")
    inventory: dict


class LayoutElement(BaseModel):
    code: str
    goe: int = 0
    timestamp: float = 0.0
    position: dict | None = None
    is_back_half: bool = False
    is_jump_pass: bool = False
    jump_pass_index: int | None = None


class Layout(BaseModel):
    elements: list[LayoutElement]
    total_tes: float
    back_half_indices: list[int]


class GenerateResponse(BaseModel):
    layouts: list[Layout]


class ValidateRequest(BaseModel):
    discipline: str = Field(pattern=r"^(mens_singles|womens_singles)$")
    segment: str = Field(pattern=r"^(short_program|free_skate)$")
    elements: list[dict]


class ValidateResponse(BaseModel):
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    total_tes: float | None = None


class RenderRinkRequest(BaseModel):
    elements: list[dict]
    width: int = Field(default=1200, ge=400, le=4000)
    height: int = Field(default=600, ge=200, le=2000)
    rink_width: float = Field(default=60.0, ge=20.0, le=80.0)
    rink_height: float = Field(default=30.0, ge=10.0, le=40.0)


class ChoreographyProgramResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    music_analysis_id: str | None
    title: str | None
    discipline: str
    segment: str
    season: str
    layout: dict | None
    total_tes: float | None
    estimated_goe: float | None
    estimated_pcs: float | None
    estimated_total: float | None
    is_valid: bool | None
    validation_errors: list[str] | None
    validation_warnings: list[str] | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class ProgramListResponse(PaginatedResponse):
    programs: list[ChoreographyProgramResponse]


class SaveProgramRequest(BaseModel):
    music_analysis_id: str | None = None
    discipline: str | None = None
    segment: str | None = None
    title: str | None = None
    layout: dict | None = None
    total_tes: float | None = None
    estimated_goe: float | None = None
    estimated_pcs: float | None = None
    estimated_total: float | None = None
    is_valid: bool | None = None
    validation_errors: list[str] | None = None
    validation_warnings: list[str] | None = None


class ExportRequest(BaseModel):
    format: str = Field(pattern=r"^(svg|pdf|json)$")


class ElementDefResponse(BaseModel):
    code: str
    name: str
    type: str  # "jump" | "spin" | "step_sequence" | "choreo_sequence"
    base_value: float
    rotations: float
    has_toe_pick: bool
    entry_edge: str
    exit_edge: str
    combo_eligible: bool
    short_program_eligible: bool


class ElementRegistryResponse(BaseModel):
    elements: list[ElementDefResponse]
    season: str


# ---------------------------------------------------------------------------
# GOE Scoring
# ---------------------------------------------------------------------------


class GOEResponse(BaseModel):
    """ISU GOE grade response for an element."""

    grade: int
    base_value: float
    estimated_score: float
    modifier: str
    positives: list[str]
    negatives: list[str]
    confidence: float
    deductions: list[dict]


# ---------------------------------------------------------------------------
# Skating Analyzer Schemas
# ---------------------------------------------------------------------------


class SubScoreSchema(BaseModel):
    name: str
    label_ru: str
    value: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)
    contributing_metrics: list[str]


class MultiDimensionalScoreSchema(BaseModel):
    subscores: list[SubScoreSchema] = Field(
        min_length=1
    )  # #675: empty subscores silent empty result
    overall: float = Field(ge=0, le=10)
    data_quality: str = "good"
    skeleton_reliability: str = "reliable"


class PhaseExtendedSchema(BaseModel):
    name: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    detection_method: str


class PhaseDetectionResultSchema(BaseModel):
    phases: list[PhaseExtendedSchema]
    overall_confidence: float = Field(ge=0, le=1)
    element_type: str | None = None
    fallback_used: bool = False


class SessionScoreResponse(BaseModel):
    id: str
    session_id: str
    subscores: list[SubScoreSchema]
    overall: float = Field(ge=0, le=10)  # #673: constrain overall to 0-10
    skeleton_reliability: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class SessionPhaseResponse(BaseModel):
    id: str
    session_id: str
    phases: list[PhaseExtendedSchema]
    overall_confidence: float
    element_type: str | None
    fallback_used: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class UserLevelResponse(BaseModel):
    id: str
    user_id: str
    level: int
    total_xp: int
    xp_to_next: int
    title: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class SkillProgressResponse(BaseModel):
    id: str
    user_id: str
    skill_id: str
    category: str
    tier: str
    unlocked: bool
    unlocked_at: str | None
    consecutive_sessions: int
    best_score: float
    xp_reward: int

    model_config = {"from_attributes": True}

    @field_validator("unlocked_at", mode="before")
    @classmethod
    def validate_optional_datetime(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class TrainingPlanItemSchema(BaseModel):
    id: str
    priority: int
    label_ru: str
    description_ru: str
    completed: bool


class TrainingPlanResponse(BaseModel):
    id: str
    user_id: str
    session_id: str | None
    items: list[TrainingPlanItemSchema]
    generated_at: str
    completed: bool
    focus_subscore: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @field_validator("generated_at", "created_at", "updated_at", mode="before")
    @classmethod
    def validate_datetime(cls, v: Any) -> str | None:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class GenerateTrainingPlanRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# ISU element registry
# ---------------------------------------------------------------------------


class ElementResponse(BaseModel):
    """ISU element registry entry — canonical code + localized names."""

    code: str
    name_ru: str
    name_en: str
    type: str
    family: str
    rotations: float
    base_value: float
