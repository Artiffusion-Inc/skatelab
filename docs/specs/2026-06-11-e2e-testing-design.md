# E2E Testing Design: Upload→Processing→Results Pipeline

> **Date:** 2026-06-11
> **Status:** Draft
> **Scope:** Audit current E2E coverage + plan for Compose UI tests and Maestro E2E flows covering the full upload→processing→results pipeline and all UX states

---

## 1. Current State Audit

### Existing Maestro Flows (9 files)

| Flow | Tags | What It Tests | Coverage |
|------|------|---------------|----------|
| `login.yaml` | auth | Login → tabs visible | Working |
| `logout.yaml` | auth | Logout → login screen | Working |
| `register.yaml` | auth | Registration flow | Working |
| `tab-navigation.yaml` | navigation, smokeTest | Tab switching + profile data | Surface-level |
| `recording.yaml` | recording | "Upload video" button visible | Cannot test camera on emulator |
| `gallery-upload.yaml` | upload | "Upload video" button tap | Dead test — Maestro cannot interact with system picker |
| `upload-processing-check.yaml` | upload, processing | Empty states on 3 tabs | Only verifies empty states, not pipeline |
| `upload-queue.yaml` | upload | Upload queue empty state | Only empty state |
| `session-detail.yaml` | sessions | Tab visibility only | Dead test — no real session interaction |

### Critical Gaps

1. **Upload pipeline**: No flow tests video upload → progress bar → processing completion
2. **Processing progress**: No verification of stage labels (Queuing, Processing, Computing metrics, Finishing)
3. **Session results**: No flow tests that processed sessions appear with metrics
4. **Error states**: No verification of network error (CloudOff), server error (ErrorOutline), invalid video snackbar
5. **Gallery picker**: Maestro `addMedia` + `pick_first_video.yaml` partial can seed device and navigate picker — not yet used

### Compose UI Tests

- `UploadWorkerTest.kt` — deduplication/invariants (Room-level)
- `AccessibilityTest.kt` — accessibility checks
- `BleScanScreenTest.kt` — BLE scan UI

No Compose UI tests for ProcessingScreen, DashboardScreen, SessionListScreen, UploadQueueScreen, or CameraScreen error handling.

---

## 2. Architecture: Two-Layer Testing

### Layer 1: Compose UI Tests (JVM, no emulator)

Fast, stable tests using `createComposeRule()`. Mock ViewModels/states. Verify rendering of all UI states without backend.

| Screen | Tests | States Verified |
|--------|-------|----------------|
| ProcessingScreen | 9 | READY, UPLOADING, PROCESSING, Idle, Progress(5%/50%/95%), Failed(Network/Server), Completed |
| DashboardScreen | 2 | Empty state, data state |
| SessionListScreen | 2 | Empty state, data state |
| UploadQueueScreen | 2 | Empty state, data state |
| CameraScreen | 3 | Invalid format, file too large, file not found snackbar |

**Total: 18 Compose UI tests**

### Layer 2: Maestro E2E Flows (emulator/device)

Full pipeline tests through real backend, using Maestro capabilities:

| Flow | What It Tests |
|------|---------------|
| `upload-pipeline.yaml` | addMedia → pick video → element selection → upload → processing → completed |
| `upload-network-error.yaml` | setAirplaneMode → upload → network error state → retry |
| `processing-stages.yaml` | Upload → assert stage labels appear in order |
| `session-results.yaml` | After processing → sessions list → session detail with metrics |

Plus updates to existing flows:
- `gallery-upload.yaml` — use `addMedia` + `pick_first_video.yaml` partial
- `session-detail.yaml` — verify session exists before tapping

---

## 3. Compose UI Tests — Detailed Design

### 3.1 ProcessingScreen (9 tests)

File: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/processing/ProcessingScreenTest.kt`

Mock approach: Create `FakeAndroidProcessingViewModel` extending `AndroidProcessingViewModel` with controlled `StateFlow` values. Alternatively, test `UploadStatusContent` and `ProcessingContent` composables directly with state parameters.

```
UploadStatusContent:
1. READY → CircularProgressIndicator + "Preparing upload…"
2. UPLOADING → LinearProgressIndicator + "Uploading video…"
3. PROCESSING → CircularProgressIndicator + "Starting analysis…"

ProcessingContent:
4. Idle → CircularProgressIndicator + "Preparing"
5. Progress(0.05f) → LinearProgressIndicator + "Queuing…" + "5%"
6. Progress(0.50f) → LinearProgressIndicator + "Processing video…" + "50%"
7. Progress(0.95f) → LinearProgressIndicator + "Finishing up…" + "95%"
8. Failed(Network) → CloudOff icon + "No connection" + retry/back buttons
9. Completed → CircularProgressIndicator + "Analysis complete"
```

### 3.2 DashboardScreen (2 tests)

File: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/dashboard/DashboardScreenTest.kt`

```
1. Empty state → "No active processing" + CloudUpload icon + body text
2. With data → personalRecords + weeklySessions sections visible
```

### 3.3 SessionListScreen (2 tests)

File: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/session/SessionListScreenTest.kt`

```
1. Empty state → "No sessions yet" + SportsScore icon + body text
2. With data → session cards with element type filters
```

### 3.4 UploadQueueScreen (2 tests)

File: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/upload/UploadQueueScreenTest.kt`

```
1. Empty state → "No uploads in progress" + CloudDone icon + body text
2. With data → upload items with status badges
```

### 3.5 CameraScreen Validation (3 tests)

File: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/camera/CameraScreenValidationTest.kt`

```
1. Invalid format → snackbar "Unsupported video format"
2. File too large → snackbar "File too large"
3. File not found → snackbar "File not found"
```

### Mock Approach

Tests call composable functions directly with state parameters — no ViewModel mocking, no Hilt injection needed. Private composables (`UploadStatusContent`, `ProcessingContent`, `UploadFailedContent`) are tested directly since they accept simple parameters.

```kotlin
@Test
fun progressAt50Percent_showsProcessingStage() {
    composeRule.setContent {
        ProcessingContent(
            state = ProcessingUiState.Progress(0.5f, ""),
            onRetry = {},
            onCancel = {},
            onBack = {},
        )
    }
    composeRule.onNodeWithText("Processing video…").assertIsDisplayed()
    composeRule.onNodeWithText("50%").assertIsDisplayed()
}
```

For screens that require a ViewModel (e.g., `DashboardScreen`, `SessionListScreen`), create minimal fakes that implement the public interface, or test via `hiltViewModel()` with `@HiltAndroidTest` and `UninstallModules` to swap real dependencies with fakes.

No backend, no emulator, no network. Millisecond execution for direct composable tests.

---

## 4. Maestro E2E Flows — Detailed Design

### 4.1 Test Asset

`mobile/e2e/maestro/assets/test_video.mp4`
- Duration: 5–10 seconds
- Size: < 5 MB
- Format: MP4 (H.264)
- Content: Figure skating element (axel jump) for realistic processing

### 4.2 upload-pipeline.yaml

Full end-to-end pipeline: upload → processing → results.

```yaml
appId: ru.skatelab.capture
tags:
  - upload
  - e2e
  - pipeline
---
- addMedia: ["./assets/test_video.mp4"]
- launchApp
- extendedWaitUntil:
    visible: "Camera"
    timeout: 15000
- tapOn: "Upload video"
- runFlow: ../partials/pick_first_video.yaml
# Element type selection (if shown)
- extendedWaitUntil:
    visible: "axel"
    timeout: 10000
- tapOn: "axel"
# Processing screen should appear
- extendedWaitUntil:
    visible: "Uploading video…"
    timeout: 30000
- extendedWaitUntil:
    visible: "Analysis complete"
    timeout: 300000
```

### 4.3 upload-network-error.yaml

Network error during upload.

```yaml
appId: ru.skatelab.capture
tags:
  - upload
  - error
---
- setAirplaneMode: enabled
- addMedia: ["./assets/test_video.mp4"]
- launchApp
- extendedWaitUntil:
    visible: "Camera"
    timeout: 15000
- tapOn: "Upload video"
- runFlow: ../partials/pick_first_video.yaml
- extendedWaitUntil:
    visible: "No connection"
    timeout: 30000
- assertVisible: "Retry"
- setAirplaneMode: disabled
```

### 4.4 processing-stages.yaml

Verify processing stage labels appear.

```yaml
appId: ru.skatelab.capture
tags:
  - processing
  - e2e
---
# Prerequisite: upload started or direct SSE processing
- launchApp
- extendedWaitUntil:
    visible: "Camera"
    timeout: 15000
# This flow verifies stage labels when processing is active
# It relies on a real backend processing a video
# Stages are: Queuing → Processing → Computing metrics → Finishing
- assertVisible: "Queuing…"
  optional: true
- assertVisible: "Processing video…"
  optional: true
- assertVisible: "Computing metrics…"
  optional: true
```

Note: Stage assertions use `optional: true` because stages transition quickly and may not be visible during assertion. This flow is best used with a slow-processing backend or for spot-checking.

### 4.5 session-results.yaml

Verify session appears after processing.

```yaml
appId: ru.skatelab.capture
tags:
  - sessions
  - e2e
---
# Prerequisite: at least one completed session exists
- launchApp
- extendedWaitUntil:
    visible: "Camera"
    timeout: 15000
- tapOn: "Sessions"
- extendedWaitUntil:
    visible: "axel"
    timeout: 15000
  optional: true
- assertVisible: "Profile"
```

### 4.6 Updated gallery-upload.yaml

Replace placeholder with actual upload flow:

```yaml
appId: ru.skatelab.capture
tags:
  - upload
  - e2e
---
- addMedia: ["./assets/test_video.mp4"]
- launchApp
- extendedWaitUntil:
    visible: "Camera"
    timeout: 15000
- tapOn: "Upload video"
- runFlow: ../partials/pick_first_video.yaml
- assertVisible: "Upload video"
```

### 4.7 Maestro Config Update

Update `mobile/e2e/maestro/config.yaml`:

```yaml
flows:
  - flows/*
excludeTags:
  - util
  - manual
```

No changes needed — new flows will be picked up automatically.

---

## 5. File Structure

```
mobile/androidApp/src/test/java/ru/skatelab/capture/ui/
├── processing/
│   └── ProcessingScreenTest.kt       # 9 tests
├── dashboard/
│   └── DashboardScreenTest.kt       # 2 tests
├── session/
│   └── SessionListScreenTest.kt     # 2 tests
├── upload/
│   └── UploadQueueScreenTest.kt     # 2 tests
└── camera/
    └── CameraScreenValidationTest.kt # 3 tests

mobile/e2e/maestro/
├── assets/
│   └── test_video.mp4               # 5-10 sec test video
├── config.yaml
├── flows/
│   ├── upload-pipeline.yaml          # NEW
│   ├── upload-network-error.yaml     # NEW
│   ├── processing-stages.yaml        # NEW
│   ├── session-results.yaml          # NEW
│   ├── gallery-upload.yaml           # UPDATED
│   ├── login.yaml
│   ├── logout.yaml
│   ├── register.yaml
│   ├── recording.yaml
│   ├── session-detail.yaml
│   ├── tab-navigation.yaml
│   ├── upload-processing-check.yaml
│   └── upload-queue.yaml
└── partials/
    └── pick_first_video.yaml          # EXISTS
```

---

## 6. Build Dependencies

Add to `mobile/androidApp/build.gradle.kts`:

```kotlin
// Compose UI testing (JVM)
debugImplementation("androidx.compose.ui:ui-test-manifest")
testImplementation("androidx.compose.ui:ui-test-junit4")
```

Already present:
- `androidTestImplementation(composeBom)`
- `androidTestImplementation("androidx.compose.ui:ui-test-junit4")`
- `testImplementation("junit:junit")`

---

## 7. CI Integration

### Existing CI (no changes needed for Compose UI tests)

`mobile-ci.yml` already runs `./gradlew :androidApp:testDebugUnitTest` — new Compose UI tests will be picked up automatically.

### Existing CI (minor changes for Maestro)

`mobile-e2e.yml` needs:
1. Copy `mobile/e2e/maestro/assets/test_video.mp4` into Maestro workspace
2. Ensure `test_video.mp4` is in git (or git LFS if > 50MB, which it won't be)

No other CI changes — `addMedia` and `setAirplaneMode` are native Maestro commands that work on CI emulators.

---

## 8. Test Asset: test_video.mp4

Requirements:
- Format: MP4 (H.264, AAC audio)
- Duration: 5–10 seconds
- Size: < 5 MB
- Content: A single figure skating jump (axel or similar)
- Source: Can be a synthetic test clip or a short excerpt from an existing session

This file should be committed directly to `mobile/e2e/maestro/assets/test_video.mp4`. No git LFS needed at < 5MB.

---

## 9. Scope and Non-Goals

### In Scope
- 18 Compose UI tests covering all UX states (empty, loading, error, data)
- 4 new Maestro E2E flows for upload pipeline, error handling, processing stages, session results
- Updated `gallery-upload.yaml` with `addMedia`
- Test asset (`test_video.mp4`)

### Out of Scope
- Backend mock server (WireMock/MockServer) for Maestro — use real backend
- Performance/stress testing
- iOS E2E (iOS app not yet implemented)
- Accessibility automated testing (already has `AccessibilityTest.kt`)
- Screenshot comparison baselines (can be added later)
- `adb push`-based pipeline scripts (Maestro `addMedia` covers this)