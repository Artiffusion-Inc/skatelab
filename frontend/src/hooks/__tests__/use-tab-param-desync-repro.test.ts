import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { renderHook, act } from "@testing-library/react"

// RED repro: use-tab-param.ts tab-switch desync.
//
// useTabParam derives activeTab = urlTab && VALID_TABS.includes(urlTab) ? urlTab : localTab,
// where urlTab = useSearchParams().get("tab"). setTab() updates localTab AND calls
// window.history.replaceState(...) to sync the URL. BUT replaceState does NOT notify
// Next.js useSearchParams — the hook's urlTab value comes from a React state snapshot
// inside Next's router that only updates via router events (router.replace /
// router.push), NOT raw history mutations. So after the FIRST setTab, urlTab stays
// frozen at the initial URL's ?tab= value, and on every subsequent render
// activeTab = stale urlTab, OVERRIDING localTab. The user clicks a tab button,
// localTab changes, but activeTab keeps returning the stale urlTab — the UI does not
// move.
//
// Repro: initial URL has ?tab=overview. User clicks "details" → setLocalTab("details")
// + replaceState. useSearchParams still returns the stale "overview" snapshot →
// activeTab = "overview" (stale urlTab wins) → UI stays on overview despite the click.
//
// Mandate: RED tests only. No production code edits, no fix-PR.

// Stub useSearchParams to return a FROZEN snapshot "tab=overview" that never
// updates — exactly mirroring Next.js behavior after a raw window.history
// .replaceState (which bypasses the router and so does not trigger a useSearchParams
// re-render with the new value). The global setup mock returns an empty
// URLSearchParams(); we override it here with a stale non-empty one.
const staleSearchParams = new URLSearchParams("tab=overview")

vi.mock("next/navigation", () => ({
  useSearchParams: vi.fn(() => staleSearchParams),
}))

import { useTabParam } from "../use-tab-param"

beforeEach(() => {
  // replaceState must be a no-op so the hook's URL sync does not throw in jsdom.
  vi.spyOn(window.history, "replaceState").mockImplementation(() => {})
  // window.location.href is read by `new URL(window.location.href)` inside setTab.
  // Default jsdom URL has no ?tab=, which is fine — the stale urlTab comes from
  // the mocked useSearchParams, not from window.location.
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useTabParam tab-switch desync — stale useSearchParams overrides localTab (RED repro)", () => {
  it("activeTab follows localTab after setTab, not the stale urlTab", () => {
    // Initial render: urlTab = "overview" (from stale useSearchParams), localTab
    // = defaultTab "overview". activeTab = "overview".
    const { result, unmount } = renderHook(() => useTabParam("overview"))
    expect(result.current.activeTab).toBe("overview")

    // User clicks the "details" tab button → setTab("details").
    act(() => {
      result.current.setTab("details")
    })

    // EXPECTED (fixed): activeTab === "details" — localTab was set to "details"
    // and the URL sync via replaceState should not feed back a stale value.
    //
    // RED (bug): useSearchParams is frozen at "tab=overview" because
    // window.history.replaceState does NOT notify Next's router, so urlTab stays
    // "overview" and activeTab = urlTab && VALID_TABS.includes(urlTab) ? urlTab
    // : localTab = "overview" — stale urlTab OVERRIDES the just-set localTab. The
    // UI stays on "overview" even though the user clicked "details".
    expect(
      result.current.activeTab,
      `BUG: use-tab-param.ts:15 activeTab = urlTab && VALID_TABS.includes(urlTab) ? ` +
        `urlTab : localTab. urlTab comes from useSearchParams().get("tab"), which is ` +
        `a frozen React snapshot that window.history.replaceState (used by setTab at ` +
        `:21) does NOT update — only Next's router (router.replace) would. So after ` +
        `setTab("details"), urlTab stays "overview" (stale) and overrides ` +
        `localTab="details" → activeTab="overview". The user clicked "details" but ` +
        `the UI stays on "overview". Deterministic on every session-detail page ` +
        `loaded with ?tab= in the URL (shared links, refreshes, back/forward).`,
    ).toBe("details")

    unmount()
  })
})
