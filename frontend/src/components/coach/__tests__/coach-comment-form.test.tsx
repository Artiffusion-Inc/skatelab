import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { CoachCommentForm } from "../coach-comment-form"

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  mutation: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null as Error | null,
  },
}))

vi.mock("@/lib/api/comments", () => ({
  useCreateComment: () => mocks.mutation,
}))

describe("CoachCommentForm", () => {
  beforeEach(() => {
    mocks.mutation.mutate = mocks.mutate
    mocks.mutation.isPending = false
    mocks.mutation.isError = false
    mocks.mutation.isSuccess = false
    mocks.mutation.error = null
    mocks.mutate.mockReset()
  })

  it("submits the comment and shows the success state", async () => {
    const user = userEvent.setup()
    render(<CoachCommentForm sessionId="session-1" />)

    const input = screen.getByRole("textbox", { name: "Комментарий тренера" })
    await user.type(input, "Сохраняй колено мягким на приземлении")
    await user.click(screen.getByRole("button", { name: "Отправить комментарий" }))

    expect(mocks.mutate).toHaveBeenCalledWith(
      { sessionId: "session-1", content: "Сохраняй колено мягким на приземлении" },
      expect.any(Object),
    )

    const options = mocks.mutate.mock.calls[0][1] as { onSuccess: () => void }
    await act(async () => options.onSuccess())
    expect(screen.getByRole("status")).toHaveTextContent("Комментарий отправлен")
  })

  it("shows loading and error states", () => {
    mocks.mutation.isPending = true
    const { rerender } = render(<CoachCommentForm sessionId="session-1" />)
    expect(screen.getByRole("button", { name: "Отправка..." })).toBeDisabled()

    mocks.mutation.isPending = false
    mocks.mutation.isError = true
    mocks.mutation.error = new Error("Not authorized")
    rerender(<CoachCommentForm sessionId="session-1" />)
    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось отправить комментарий")
  })
})
