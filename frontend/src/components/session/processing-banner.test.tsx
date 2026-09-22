import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { ProcessingBanner } from "./processing-banner"

describe("ProcessingBanner", () => {
  it("shows a recoverable waiting state when the session has no task id", () => {
    render(<ProcessingBanner taskId={null} onCancel={() => {}} onRetry={() => {}} />)

    expect(screen.getByRole("status")).toHaveTextContent(/ожидание/i)
    expect(screen.queryByRole("button", { name: /отменить/i })).not.toBeInTheDocument()
  })
})
