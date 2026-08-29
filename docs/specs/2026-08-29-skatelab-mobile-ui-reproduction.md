# SkateLab Mobile UI Reproduction

Status: implementation backlog
Date: 2026-08-29
Source: `docs/concepts/mobile-reference/screens/`

## Goal

Reproduce reference mobile screens in native Jetpack Compose while preserving current auth, capture, upload, SSE processing, result, and synthetic multimodal contracts.

Reference screenshots define visual structure and copy direction. They do not define device chrome, production assets, sensor validity, or backend behavior.

## Product boundaries

- Android first. Keep `commonMain` platform-free.
- Russian-first strings; every user-visible string uses resources.
- Keep current `CameraRoute`, upload queue, processing, result, BLE scan, calibration, and recording paths working.
- Mark sensor-fusion output `synthetic/unvalidated` until WT901 hardware acceptance.
- Do not invent API endpoints when an existing contract can cover a screen.
- Do not place reference screenshots in production UI.
- Do not draw status bar, home indicator, permission dialogs, or phone bezel as app content.

## Current implementation map

| Area | Existing code | Gap |
| --- | --- | --- |
| Auth | `ui/auth/*`, `LoginRoute`, `RegisterRoute`, `SplashRoute` | forgot password, new password, email verification, validation/error fidelity |
| Main shell | `ui/tabs/*`, four tabs | reference expects five product areas; notification entry missing |
| Camera | `ui/camera/*`, `CameraRoute` | reference preparation gate, permission state, gallery path fidelity |
| BLE | `presentation/ble/*`, `BleScanRoute` | reference-level no-sensor/one-sensor/both-sensor states |
| Capture | `presentation/calibration/*`, `presentation/recording/*` | reference copy/layout and recovery states |
| Processing | `ui/processing/*`, `ProcessingRoute` | complete error/retry/cancel/restart state matrix |
| Results | `ui/session/*`, `ResultDetailRoute`, `MetricTrendRoute` | completed Axel report layout, provenance and recommendation context |
| Sessions | `SessionListScreen`, `SessionsRoute` | empty/list/filter reference fidelity |
| Programs | none | create details, elements, music/choreography, created, PDF-ready |
| Notifications | none | list, unread state, deep links |
| Profile | `ui/profile/*`, `ProfileRoute` | logout dialog and reference fidelity |

## Screen inventory

### Auth

| Reference | Route/state | Acceptance |
| --- | --- | --- |
| Registration | `RegisterRoute` | email/password/display name, social entry, validation, Russian copy |
| Forgot password | new `ForgotPasswordRoute` | submit email, success, invalid email, network error |
| New password | new `NewPasswordRoute(token)` | password rules, confirmation mismatch, expired token |
| Verify email | new `VerifyEmailRoute` | resend cooldown, success, failure |
| Logout confirmation | modal from `ProfileRoute` | destructive action requires confirmation |

### Analysis

| Reference | Route/state | Acceptance |
| --- | --- | --- |
| Empty | `SessionsRoute` / empty state | first-video CTA opens camera flow |
| List | `SessionsRoute` / loaded | recent analyses, status, element, date, click-through |
| Filters | modal from `SessionsRoute` | element, attempts, status, period, season; apply/reset |
| Camera permission | `CameraRoute` / permission state | explain purpose, request system permission, denied recovery |
| Processing error | `ProcessingRoute` / terminal failure | retry, settings/help, cancel; no duplicate queue |
| Completed Axel | `ResultDetailRoute(sessionId)` | take-off/landing, confidence, diagnostics, provenance, one recommendation |
| Metric trend | `MetricTrendRoute` | metric history, unavailable state, back navigation |

### Capture and processing

| State | Existing path | Required behavior |
| --- | --- | --- |
| Video-only | `CameraRoute` | explicit `video-only` label; no false fusion claim |
| No sensors | BLE preparation | continue video-only or explain requirement |
| One sensor | BLE preparation | show missing side and degraded diagnostics |
| Both sensors | BLE/calibration | proceed to calibration and recording |
| Uploading | worker/queue | durable progress, process task persisted once |
| Offline/upload failure | upload queue | retry, preserve files, visible error |
| Processing | SSE | reconnect/restart recovery without duplicate process queue |
| Cancelled | processing | terminal cancelled state and safe return |

### Programs and choreography

New routes, initially local/mock-backed until API contract exists:

- `ProgramsRoute` — program list and empty state.
- `ProgramCreateDetailsRoute` — name, season, type, athlete, duration.
- `ProgramElementsRoute(programId)` — catalog, attempts, status.
- `ProgramMusicChoreographyRoute(programId)` — music upload, rink diagram, selected elements.
- `ProgramCreatedRoute(programId)` — success and open-program action.
- `ProgramReportRoute(programId)` — PDF ready/export/share.

Do not add backend persistence until screen behavior and API ownership are agreed.

### Notifications

New routes:

- `NotificationsRoute` — grouped notification list and unread markers.
- typed deep-link destinations for analysis, coach comment, training, and export events.

Unknown or stale deep links open `NotificationsRoute` with an explanatory state.

## Design tokens

Extract once from references, then reuse. Exact values must be checked against screenshots during implementation.

- surface: lavender-white background, white elevated cards
- primary: purple action color
- shape: rounded fields/cards/sheets/dialogs
- density: compact mobile content with large touch targets
- navigation: bottom navigation with product-area labels
- typography: Russian-friendly font with explicit headline/body/label styles
- semantic colors: success, warning, error, disabled, synthetic/unvalidated

Tokens belong under existing Android theme files, not per-screen constants:

- `presentation/theme/SkateLabColors.kt`
- `presentation/theme/Theme.kt`
- `presentation/theme/Type.kt`
- `presentation/theme/SkateLabModifiers.kt`

## Implementation order

1. Add token gaps and shared primitives; do not refactor working capture code.
2. Finish auth recovery and logout state.
3. Finish analysis empty/list/filter and camera permission states.
4. Match BLE preparation and video-only/degraded states.
5. Match processing error/retry/cancel/restart recovery.
6. Match completed Axel result and metric trend with explicit provenance.
7. Add programs/choreography/PDF screens with local state only.
8. Add notifications and typed deep links.
9. Add screenshot/state tests and run emulator visual QA.

## Test matrix

Each implementation slice gets at least one regression test before production code changes.

- Auth: valid, invalid, loading, network failure, resend cooldown, expired reset token.
- Analysis: empty, list, filters apply/reset, permission denied, navigation.
- Capture: video-only, no sensor, one sensor, both sensors, cancel.
- Upload: retry, durable pending item, process task persisted once, restart recovery.
- Processing: progress, terminal success, terminal failure, no retry after terminal payload.
- Result: synthetic label, missing diagnostics, confidence unavailable, recommendation context.
- Programs: empty, form validation, add/remove element, export success/failure.
- Notifications: unread/read, each deep link, stale deep link.

## Visual QA gate

For each reference screen:

1. Capture implementation at matching portrait viewport and state.
2. Compare app content only; exclude system/device chrome.
3. Check layout hierarchy, spacing, typography, color, shape, iconography, copy, and scroll position.
4. Check touch targets and content descriptions.
5. Fix P0/P1/P2 differences.
6. Capture again and record result in `docs/verification/`.

Build success, unit tests, and HTTP health do not count as visual QA.

## Definition of done

- Every non-duplicate reference has a route or documented intentional merge.
- Every route has loading, empty, error, and success behavior where applicable.
- Existing multimodal upload/processing/result flow remains intact.
- Synthetic/unvalidated provenance is visible wherever relevant.
- No hardcoded user-facing strings outside resources.
- Android unit/UI tests cover state transitions and navigation.
- Screenshot comparison passes at reference portrait viewport.
- Debug and release builds pass.

## Deferred

- iOS-native reproduction.
- Real WT901 accuracy claims.
- Production programs/choreography APIs.
- Full coach collaboration model.
- New visual asset generation before asset licensing and art direction are approved.
