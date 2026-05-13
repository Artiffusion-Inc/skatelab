export interface PersonInfo {
  track_id: number
  hits: number
  bbox: number[] // [x1, y1, x2, y2] normalized
  mid_hip: number[] // [x, y] normalized
}

export interface PersonClick {
  x: number
  y: number
}

export interface DetectResponse {
  persons: PersonInfo[]
  preview_image: string // base64 PNG
  video_key: string
  auto_click: PersonClick | null
  status: string
}

export interface ProcessRequest {
  video_key: string
  person_click: PersonClick
  frame_skip: number
  layer: number
  tracking: string
  export: boolean
}

export interface ProcessStats {
  total_frames: number
  valid_frames: number
  fps: number
  resolution: string
}

export interface ProcessResponse {
  video_path: string
  poses_path: string | null
  csv_path: string | null
  stats: ProcessStats
  status: string
}

// ---------------------------------------------------------------------------
// Analysis Data Types (Task 4, 2026-04-16)
// ---------------------------------------------------------------------------

export interface PoseData {
  frames: number[] // Sampled frame indices (e.g., [0, 10, 20, ...])
  poses: number[][][] // [frame][keypoint][x,y,conf] - (N_sampled, 17, 3)
  fps: number // Video frame rate
}

export interface FrameMetrics {
  knee_angles_r: (number | null)[] // Right knee angle per frame
  knee_angles_l: (number | null)[] // Left knee angle per frame
  hip_angles_r: (number | null)[] // Right hip angle per frame
  hip_angles_l: (number | null)[] // Left hip angle per frame
  trunk_lean: (number | null)[] // Spine lean from vertical per frame
  com_height: (number | null)[] // Center of mass height per frame
}

export interface PhaseFrame {
  frame: number
  timestamp?: number
}

export interface PhasesData {
  takeoff: PhaseFrame
  peak: PhaseFrame
  landing: PhaseFrame
}

export interface ElementSegment {
  id: string
  element_type: string
  element_name?: string | null
  start_frame: number
  end_frame: number
  confidence: number
  phases_json?: PhasesData | null
}

export interface TimelineData {
  segments: ElementSegment[]
  segmentation_confidence?: number | null
  segmentation_status: string
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export interface SessionMetric {
  id: string
  metric_name: string
  metric_value: number
  is_pr: boolean
  prev_best: number | null
  reference_value: number | null
  is_in_range: boolean | null
}

export interface Session {
  id: string
  user_id: string
  element_type: string
  video_key?: string | null
  video_url: string | null
  processed_video_key?: string | null
  processed_video_url: string | null
  poses_url?: string | null // Deprecated: Replaced by pose_data
  csv_url?: string | null // Deprecated: Replaced by frame_metrics
  pose_data?: PoseData | null // New: Direct pose data storage (JSON)
  frame_metrics?: FrameMetrics | null // New: Frame-by-frame metrics (JSON)
  status: string
  error_message: string | null
  phases?: PhasesData | null // Typed phase markers
  timeline?: TimelineData | null
  segmentation_status: string
  recommendations: string[] | null
  overall_score: number | null
  created_at: string
  processed_at: string | null
  metrics: SessionMetric[]
}

export interface SessionListResponse {
  sessions: Session[]
  total: number
}

// ---------------------------------------------------------------------------
// Metrics & Progress
// ---------------------------------------------------------------------------

export interface TrendDataPoint {
  date: string
  value: number
  session_id: string
  is_pr: boolean
}

export interface TrendResponse {
  metric_name: string
  element_type: string
  data_points: TrendDataPoint[]
  trend: "improving" | "stable" | "declining"
  current_pr: number | null
  reference_range: { min: number; max: number } | null
}

export interface DiagnosticsFinding {
  severity: "warning" | "info"
  element: string
  metric: string
  message: string
  detail: string
}

export interface DiagnosticsResponse {
  user_id: string
  findings: DiagnosticsFinding[]
}

export interface MetricDef {
  name: string
  label_ru: string
  unit: string
  format: string
  direction: "higher" | "lower"
  element_types: string[]
  ideal_range: [number, number]
}

// ---------------------------------------------------------------------------
// Connections
// ---------------------------------------------------------------------------

export type ConnectionType = "coaching" | "choreography"

export interface Connection {
  id: string
  from_user_id: string
  to_user_id: string
  connection_type: ConnectionType
  status: "invited" | "active" | "ended"
  initiated_by: string | null
  created_at: string
  ended_at: string | null
  from_user_name: string | null
  to_user_name: string | null
}

export interface ConnectionListResponse {
  connections: Connection[]
}
