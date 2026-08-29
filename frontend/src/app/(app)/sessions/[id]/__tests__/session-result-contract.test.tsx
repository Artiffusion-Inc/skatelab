import { describe, expect, it, beforeEach, vi } from "vitest"
import "@testing-library/jest-dom/vitest"
import { render, screen } from "@testing-library/react"

const mocks = vi.hoisted(() => ({
  activeTab: "overview" as "overview" | "details",
  useSession: vi.fn(),
  useDiagnostics: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "session-result-1" }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("next/link", () => ({
  default: ({ children, ...props }: { children: React.ReactNode }) => <a {...props}>{children}</a>,
}))

vi.mock("@/lib/api/sessions", () => ({
  SESSION_POLLING_STATUSES: new Set(),
  useSession: mocks.useSession,
  useDeleteSession: () => ({ mutate: vi.fn() }),
  useRetrySession: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock("@/lib/api/process", () => ({
  useCancelProcess: () => ({ mutate: vi.fn() }),
}))

vi.mock("@/lib/api/metrics", () => ({
  useDiagnostics: mocks.useDiagnostics,
}))

vi.mock("@/hooks/use-metric-registry", () => ({
  useElementLabel: () => (code: string) => code,
  useMetricRegistry: () => ({ data: undefined }),
}))

vi.mock("@/hooks/use-tab-param", () => ({
  useTabParam: () => ({ activeTab: mocks.activeTab, setTab: vi.fn() }),
}))

vi.mock("@/components/analysis/phase-timeline", () => ({
  PhaseTimeline: () => null,
}))
vi.mock("@/components/analysis/video-with-skeleton", () => ({
  VideoWithSkeleton: () => null,
}))
vi.mock("@/components/analysis/frame-metrics-chart", () => ({
  FrameMetricsChart: () => null,
}))
vi.mock("@/components/analysis/analyzer-tab", () => ({
  AnalyzerTab: () => null,
}))
vi.mock("@/components/session/metric-row", () => ({
  MetricRow: () => null,
}))
vi.mock("@/components/session/processing-banner", () => ({
  ProcessingBanner: () => null,
}))
vi.mock("@/components/session/session-action-menu", () => ({
  SessionActionMenu: () => null,
}))
vi.mock("@/components/session/session-downloads", () => ({
  SessionDownloads: () => null,
}))

import SessionDetailPage from "../page"

const baseSession = {
  id: "session-result-1",
  user_id: "user-1",
  element_type: "3A",
  video_key: null,
  video_url: null,
  processed_video_key: null,
  processed_video_url: null,
  poses_url: null,
  csv_url: null,
  pose_data: null,
  frame_metrics: null,
  status: "done",
  error_message: null,
  phases: { takeoff: null, peak: null, landing: null },
  recommendations: null,
  overall_score: null,
  process_task_id: null,
  imu_left_key: null,
  imu_right_key: null,
  manifest_key: null,
  created_at: "2026-08-30T10:00:00Z",
  processed_at: null,
  metrics: [],
  timeline: null,
  segmentation_status: "done",
}

beforeEach(() => {
  mocks.activeTab = "overview"
  mocks.useSession.mockReturnValue({ data: baseSession, isLoading: false })
  mocks.useDiagnostics.mockReturnValue({
    data: { user_id: "user-1", findings: [] },
    isLoading: false,
  })
})

describe("completed session result rendering", () => {
  it("shows unavailable provenance when sensor keys are absent", () => {
    render(<SessionDetailPage />)

    expect(screen.getByRole("status")).toHaveTextContent("Sensor fusion: unavailable")
  })

  it("renders a nullable score and recommendation without changing result state", () => {
    mocks.useSession.mockReturnValue({
      data: {
        ...baseSession,
        overall_score: 0.75,
        recommendations: ["Keep the landing knee bent"],
      },
      isLoading: false,
    })

    render(<SessionDetailPage />)

    expect(screen.getByText(/7\.5.*из 10/)).toBeInTheDocument()
    expect(screen.getByText("Keep the landing knee bent")).toBeInTheDocument()
  })

  it("shows diagnostics even when the result has no pose data", () => {
    mocks.activeTab = "details"
    mocks.useDiagnostics.mockReturnValue({
      data: {
        user_id: "user-1",
        findings: [
          {
            severity: "warning",
            element: "3A",
            metric: "landing_knee_angle",
            message: "Landing needs work",
            detail: "Bend more on landing",
          },
        ],
      },
      isLoading: false,
    })

    render(<SessionDetailPage />)

    expect(screen.getByText("Landing needs work")).toBeInTheDocument()
    expect(screen.getByText("Bend more on landing")).toBeInTheDocument()
  })
})
