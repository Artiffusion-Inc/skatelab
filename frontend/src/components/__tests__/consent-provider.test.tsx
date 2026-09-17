import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConsentProvider } from "../consent-provider"

vi.mock("@/lib/useMountEffect", () => ({
  useMountEffect: () => undefined,
}))

describe("ConsentProvider server-safe shell", () => {
  it("renders its children before client consent storage initializes", () => {
    render(
      <ConsentProvider>
        <p>Landing content</p>
      </ConsentProvider>,
    )

    expect(screen.getByText("Landing content")).toBeInTheDocument()
  })
})
