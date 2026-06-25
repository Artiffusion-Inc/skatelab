import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"
import { server } from "@/test/server"
import { render, screen } from "@/test/test-utils"
import { PersonalRecords } from "../personal-records"

const FIXTURE_ELEMENTS = [
  {
    code: "3A",
    name_ru: "Тройной Аксель",
    name_en: "Triple Axel",
    type: "jump",
    family: "A",
    rotations: 3,
    base_value: 8.0,
  },
  {
    code: "1T",
    name_ru: "Одинарный Тулуп",
    name_en: "Single Toe Loop",
    type: "jump",
    family: "T",
    rotations: 1,
    base_value: 0.4,
  },
]

const FIXTURE_REGISTRY = {
  airtime: {
    name: "airtime",
    label_ru: "Время в воздухе",
    unit: "s",
    format: "0.00",
    direction: "higher",
    element_types: ["3A"],
    ideal_range: [0.3, 0.8],
  },
}

function withProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe("PersonalRecords", () => {
  it("groups personal records by ISU element label", async () => {
    server.use(
      http.get("*/metrics/elements", () =>
        HttpResponse.json({
          registry_version: 1,
          elements: FIXTURE_ELEMENTS,
        }),
      ),
      http.get("*/metrics/registry", () => HttpResponse.json(FIXTURE_REGISTRY)),
      http.get("*/metrics/prs*", () =>
        HttpResponse.json({
          prs: [
            {
              element_type: "3A",
              metric_name: "airtime",
              value: 0.85,
              session_id: "s1",
            },
          ],
        }),
      ),
    )

    withProviders(<PersonalRecords />)

    // Wait for react-query to settle and the element label to render.
    const label = await screen.findByText("3A — Triple Axel")
    expect(label).toBeTruthy()
  })

  it("falls back to the code when element is missing from the registry", async () => {
    server.use(
      http.get("*/metrics/elements", () =>
        HttpResponse.json({ registry_version: 1, elements: [] }),
      ),
      http.get("*/metrics/registry", () => HttpResponse.json(FIXTURE_REGISTRY)),
      http.get("*/metrics/prs*", () =>
        HttpResponse.json({
          prs: [
            {
              element_type: "FSp4",
              metric_name: "airtime",
              value: 0.5,
              session_id: "s2",
            },
          ],
        }),
      ),
    )

    withProviders(<PersonalRecords />)
    const label = await screen.findByText("FSp4")
    expect(label).toBeTruthy()
  })
})
