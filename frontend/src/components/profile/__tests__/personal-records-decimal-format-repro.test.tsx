import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import { HttpResponse, http } from "msw"
import { describe, expect, it } from "vitest"
import { server } from "@/test/server"
import { render, screen } from "@/test/test-utils"
import { PersonalRecords } from "../personal-records"

// RED repro: PersonalRecords drops ALL decimals because the decimal-precision
// parser at personal-records.tsx:44-45 does `mdef.format?.replace(".", "")`
// which mangles Python format-specs emitted by backend/app/metrics_registry.py
// (e.g. ".2f", ".1f", ".0f") into NaN, coercing toFixed(NaN) → toFixed(0).

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
    code: "StSq1",
    name_ru: "Шаги 1",
    name_en: "Step Sequence 1",
    type: "step",
    family: "St",
    rotations: 0,
    base_value: 1.0,
  },
]

// Use the REAL backend format strings (backend/app/metrics_registry.py):
// airtime → ".2f", trunk_lean → ".1f". The existing test uses "0.00" (never
// emitted by the backend) which masks the bug.
const FIXTURE_REGISTRY = {
  airtime: {
    name: "airtime",
    label_ru: "Время полёта",
    unit: "s",
    format: ".2f",
    direction: "higher",
    element_types: ["3A"],
    ideal_range: [0.3, 0.7],
  },
  trunk_lean: {
    name: "trunk_lean",
    label_ru: "Наклон корпуса",
    unit: "deg",
    format: ".1f",
    direction: "lower",
    element_types: ["StSq1"],
    ideal_range: [-15, 20],
  },
}

function withProviders(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe("PersonalRecords decimal-precision (RED repro)", () => {
  it("preserves decimal places for Python format-spec '.2f' (airtime 0.85s)", async () => {
    server.use(
      http.get("*/metrics/elements", () =>
        HttpResponse.json({ registry_version: 1, elements: FIXTURE_ELEMENTS }),
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

    // Contract: an airtime PR of 0.85 with format ".2f" must render "0.85",
    // NOT "1" (toFixed(0) rounding from the broken NaN parse).
    const value = await screen.findByText(/0\.85/)
    expect(value).toBeTruthy()
  })

  it("preserves one decimal place for Python format-spec '.1f' (trunk_lean 125.3)", async () => {
    server.use(
      http.get("*/metrics/elements", () =>
        HttpResponse.json({ registry_version: 1, elements: FIXTURE_ELEMENTS }),
      ),
      http.get("*/metrics/registry", () => HttpResponse.json(FIXTURE_REGISTRY)),
      http.get("*/metrics/prs*", () =>
        HttpResponse.json({
          prs: [
            {
              element_type: "StSq1",
              metric_name: "trunk_lean",
              value: 125.3,
              session_id: "s2",
            },
          ],
        }),
      ),
    )

    withProviders(<PersonalRecords />)

    // Contract: a trunk_lean PR of 125.3 with format ".1f" must render "125.3",
    // NOT "125" (decimals dropped via toFixed(0)).
    const value = await screen.findByText(/125\.3/)
    expect(value).toBeTruthy()
  })
})
