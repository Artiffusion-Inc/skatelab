import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ConsentProvider, useConsent } from "../consent-provider"

vi.mock("@/lib/useMountEffect", () => ({
  useMountEffect: () => undefined,
}))

function PreferencesTrigger() {
  const { openBanner, setConsent, showBanner } = useConsent()
  return (
    <>
      <button
        type="button"
        onClick={() => setConsent({ essential: true, analytics: false, recordings: false })}
      >
        Save choice
      </button>
      <button type="button" onClick={openBanner}>
        Open preferences
      </button>
      <output>{String(showBanner)}</output>
    </>
  )
}

describe("ConsentProvider server-safe shell", () => {
  it("renders its children before client consent storage initializes", () => {
    render(
      <ConsentProvider>
        <p>Landing content</p>
      </ConsentProvider>,
    )

    expect(screen.getByText("Landing content")).toBeInTheDocument()
  })

  it("reopens preferences after a saved choice", () => {
    render(
      <ConsentProvider>
        <PreferencesTrigger />
      </ConsentProvider>,
    )

    fireEvent.click(screen.getByRole("button", { name: "Save choice" }))
    expect(screen.getByText("false")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Open preferences" }))
    expect(screen.getByText("true")).toBeInTheDocument()
  })
})
