# E2E Testing Implementation

> **Goal:** Implement the three-layer E2E testing architecture from `docs/specs/2026-06-11-e2e-testing-design.md` — 18 Compose UI tests, 4 new Maestro flows, debug build with FakeProcessApi, test doubles, and tag-based CI separation.

## Intent

Full pipeline video upload → processing → results works without bugs and is covered by automated tests. All UX states are verified. Maestro E2E flows pass on CI. Compose UI tests run in JVM with Robolectric.

## Oracle

All Compose UI tests green (`./gradlew :androidApp:testDebugUnitTest`), Maestro smoke tests pass on CI, and manual walkthrough of upload → progress → results on a real device shows working pipeline.

## Constraints

- Follow existing project patterns (Now in Android for Compose testing, existing Maestro flows for E2E)
- `private` → `internal` for testable composables only
- No WireMock/MockServer for Maestro — real backend for E2E, FakeProcessApi for debug build
- Test video asset committed to git (< 5MB, no LFS)
- No code changes outside test files and build config for Compose UI tests (except visibility changes)
- Maestro `setAirplaneMode` before `launchApp` in network error flow

## Key Decisions

- Three-layer architecture: Compose UI (JVM+Robolectric) → Maestro E2E (tag-based) → Debug build E2E (FakeProcessApi)
- Direct composable testing with state params, no Hilt for rendering tests
- `hasProgressBarRangeInfo()` for progress assertions + `onNodeWithText()` for labels
- `useUnmergedTree = true` for Snackbar assertions
- Tag-based suite separation: `smokeTest` (every PR) vs `e2e` (merge to master)
- Contract testing per layer with clear test doubles

## Sources

- `docs/specs/2026-06-11-e2e-testing-design.md` — full spec
- `docs/specs/2026-06-11-e2e-testing-research-report.md` — research findings
- `docs/goals/mobile-polish-e2e/` — previous goal (upload pipeline bugs, progress UX, empty/error states)