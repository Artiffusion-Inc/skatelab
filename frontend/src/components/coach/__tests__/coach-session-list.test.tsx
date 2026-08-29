import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { Session } from "@/types"
import { CoachSessionList } from "../coach-session-list"

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: "session-1",
    user_id: "athlete-1",
    element_type: "axel",
    video_url: null,
    processed_video_url: null,
    status: "completed",
    error_message: null,
    phases: null,
    recommendations: [],
    overall_score: 0.8,
    created_at: "2026-06-01T00:00:00Z",
    processed_at: "2026-06-01T00:10:00Z",
    metrics: [],
    segmentation_status: "done",
    ...overrides,
  }
}

describe("CoachSessionList", () => {
  it("links completed, processing, failed, and unavailable sessions to review", () => {
    render(
      <CoachSessionList
        sessions={[
          makeSession({ id: "completed", status: "completed" }),
          makeSession({ id: "processing", status: "queued" }),
          makeSession({ id: "failed", status: "failed", error_message: "decode failed" }),
          makeSession({ id: "unavailable", status: "done", overall_score: null }),
        ]}
      />,
    )

    expect(screen.getByRole("link", { name: /axel.*completed/i }).getAttribute("href")).toBe(
      "/sessions/completed",
    )
    expect(screen.getAllByText(/анализ видео|analyzing/i).length).toBeGreaterThan(1)
    expect(screen.getAllByText(/ошибка анализа|analysis failed/i).length).toBeGreaterThan(1)
    expect(
      screen.getAllByText(/данные анализа недоступны|analysis data unavailable/i).length,
    ).toBeGreaterThan(1)
  })

  it("applies a display-only status filter and loads the next backend page", () => {
    const onLoadMore = vi.fn()
    render(
      <CoachSessionList
        sessions={[
          makeSession({ id: "completed", status: "completed" }),
          makeSession({ id: "processing", status: "processing" }),
        ]}
        hasNextPage
        isFetchingNextPage={false}
        onLoadMore={onLoadMore}
      />,
    )

    fireEvent.change(screen.getByLabelText(/статус|status/i), { target: { value: "processing" } })
    expect(screen.queryByRole("link", { name: /completed/i })).toBeNull()
    expect(screen.getByRole("link", { name: /processing/i })).not.toBeNull()

    fireEvent.click(screen.getByRole("button", { name: /загрузить ещё|load more/i }))
    expect(onLoadMore).toHaveBeenCalledOnce()
  })

  it("shows the empty state when an athlete has no sessions", () => {
    render(<CoachSessionList sessions={[]} />)

    expect(screen.getByText(/нет записей|no sessions/i)).not.toBeNull()
  })
})
