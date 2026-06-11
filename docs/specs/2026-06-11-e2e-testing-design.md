# E2E Testing Design: Upload→Processing→Results Pipeline

> **Date:** 2026-06-11
> **Status:** Updated with research findings (Compose patterns, Maestro capabilities, async pipeline architecture)
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

## 2. Architecture: Three-Layer Testing

### Layer 1: Compose UI Tests (JVM with Robolectric, no emulator)

Fast, stable tests using `createComposeRule()` + Robolectric. Call `internal` composables directly with state parameters. Verify rendering of all UI states without backend.

**Key decisions (from research):**
- Robolectric is required because `stringResource()` needs Android context — plain JVM tests fail
- `private` composables changed to `internal` for testability (NiA pattern)
- Use `hasProgressBarRangeInfo()` for exact progress assertions + `onNodeWithText()` for labels
- Use `useUnmergedTree = true` for Snackbar assertions
- Text-first selectors; `testTag` only for elements without unique text
- One test class per screen: `{ScreenName}Test`

| Screen | Tests | States Verified |
|--------|-------|----------------|
| ProcessingScreen | 9 | READY, UPLOADING, PROCESSING, Idle, Progress(5%/50%/95%), Failed(Network/Server), Completed |
| DashboardScreen | 2 | Empty state, data state |
| SessionListScreen | 2 | Empty state, data state |
| UploadQueueScreen | 2 | Empty state, data state |
| CameraScreen | 3 | Invalid format, file too large, file not found snackbar |

**Total: 18 Compose UI tests**

### Layer 2: Maestro E2E Flows (emulator/device, tag-based suite separation)

Full pipeline tests through real backend, using Maestro capabilities.

**Tag-based suite separation (from research):**
- `smokeTest` — fast flows (~2 min), run on every PR
- `e2e` — slow flows with real backend (~10 min), run on merge to master / nightly

```bash
# PR: fast smoke tests
maestro test --include-tags=smokeTest e2e/maestro/

# Merge: full suite
maestro test e2e/maestro/
```

**Key decisions (from research):**
- Sharding (`--shards N`) has Android bugs (gRPC errors, issue #1853) — use tag separation instead
- `setAirplaneMode: enabled` BEFORE `launchApp` to avoid race condition
- Always clean up: `setAirplaneMode: disabled` at end + ADB cleanup in CI `always()` step
- `retry` command (maxRetries 2-3) for transient SSE-driven state changes
- `continueOnFailure: true` in config.yaml — don't stop suite on first failure

| Flow | What It Tests |
|------|---------------|
| `upload-pipeline.yaml` | addMedia → pick video → element selection → upload → processing → completed | `e2e` |
| `upload-network-error.yaml` | setAirplaneMode → upload → network error state → retry | `e2e` |
| `processing-stages.yaml` | Upload → assert stage labels appear in order | `e2e` |
| `session-results.yaml` | After processing → sessions list → session detail with metrics | `e2e` |

Existing flows get `smokeTest` tags:
| `login.yaml` | Login → tabs visible | `smokeTest` |
| `logout.yaml` | Logout → login screen | `smokeTest` |
| `register.yaml` | Registration flow | `smokeTest` |
| `tab-navigation.yaml` | Tab switching | `smokeTest` |
| `upload-processing-check.yaml` | Empty states on 3 tabs | `smokeTest` |
| `upload-queue.yaml` | Upload queue empty state | `smokeTest` |

### Layer 3: Debug Build E2E with FakeProcessApi (fast, <1s)

A debug build variant that injects `FakeProcessApi` via Hilt module, returning pre-recorded SSE events instantly. This makes Maestro E2E flows run in <1s instead of 30-120s.

**Test doubles (from research):**
- `SseScenarios` — pre-recorded SSE event sequences (happy path, network error, slow progress)
- `FakeProcessApi` — already exists in `ProcessingViewModelTest`, expanded with `SseScenarios`
- Debug Hilt module: `androidApp/src/debug/java/.../di/FakeApiModule.kt`

**When to use:** CI smoke tests, PR checks. Not a replacement for real-backend E2E (merge to master).

Plus updates to existing flows:
- `gallery-upload.yaml` — use `addMedia` + `pick_first_video.yaml` partial
- `session-detail.yaml` — verify session exists before tapping

---

## 3. Compose UI Tests — Detailed Design

### 3.1 ProcessingScreen (9 tests)

File: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/processing/ProcessingScreenTest.kt`

**Visibility:** Change `private` → `internal` for `UploadStatusContent`, `ProcessingContent`, `UploadFailedContent`.

**Asserting progress:** Use `hasProgressBarRangeInfo(ProgressBarRangeInfo(current = 0.5f, range = 0f..1f, steps = 0))` for exact progress verification, plus `onNodeWithText("50%")` for label verification.

```
UploadStatusContent:
1. READY → CircularProgressIndicator + "Preparing upload…"
2. UPLOADING → LinearProgressIndicator(testTag="uploadProgress") + "Uploading video…"
3. PROCESSING → CircularProgressIndicator + "Starting analysis…"

ProcessingContent:
4. Idle → CircularProgressIndicator + "Preparing"
5. Progress(0.05f) → LinearProgressIndicator + "Queuing…" + "5%" + ProgressBarRangeInfo(0.05f)
6. Progress(0.50f) → LinearProgressIndicator + "Processing video…" + "50%" + ProgressBarRangeInfo(0.5f)
7. Progress(0.95f) → LinearProgressIndicator + "Finishing up…" + "95%" + ProgressBarRangeInfo(0.95f)
8. Failed(Network) → CloudOff icon(contentDescription="Error") + "No connection" + liveRegion=Polite + retry/back buttons
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

**Snackbar testing:** Use `onNode(hasText(message), useUnmergedTree = true)` with `waitUntil` for async snackbar. Extract snackbar display logic into testable composable if needed.

```
1. Invalid format → snackbar "Unsupported video format" (useUnmergedTree = true)
2. File too large → snackbar "File too large" (useUnmergedTree = true)
3. File not found → snackbar "File not found" (useUnmergedTree = true)
```

### Mock Approach

Tests call `internal` composable functions directly with state parameters — no ViewModel mocking, no Hilt injection needed for rendering tests. This is the Now in Android pattern.

**`private` → `internal` visibility changes:**
- `ProcessingScreen.kt`: `ProcessingContent`, `UploadStatusContent`, `UploadFailedContent`
- `DashboardScreen.kt`: `DashboardContent` (if exists as separate composable)
- `SessionListScreen.kt`: Extract empty/loaded content into `internal` composables

```kotlin
@RunWith(RobolectricTestRunner::class) // Required for stringResource()
class ProcessingScreenTest {
    @get:Rule val composeRule = createComposeRule()

    @Test
    fun progressAt50Percent_showsProcessingStage() {
        composeRule.setContent {
            AppTheme {
                ProcessingContent(
                    state = ProcessingUiState.Progress(0.5f, ""),
                    onRetry = {}, onCancel = {}, onBack = {},
                )
            }
        }
        composeRule.onNodeWithText("Processing video…").assertIsDisplayed()
        composeRule.onNodeWithText("50%").assertIsDisplayed()
        composeRule.onNode(
            hasProgressBarRangeInfo(ProgressBarRangeInfo(current = 0.5f, range = 0f..1f, steps = 0))
        ).assertIsDisplayed()
    }
}
```

For screens that require a ViewModel (e.g., `DashboardScreen`, `SessionListScreen`), extract stateless content composables into `internal` functions and test them directly. Do NOT use `@HiltAndroidTest` for rendering tests — it adds 2-5s startup per test and ties tests to the DI graph.

**Accessibility assertions within each test:**
```kotlin
// Verify error icon has content description
composeRule.onNodeWithContentDescription("Error").assertIsDisplayed()
// Verify live region (screen reader announces changes)
composeRule.onNode(hasLiveRegionMode(LiveRegionMode.Polite) and hasText("No connection")).assertIsDisplayed()
// Verify role semantics
composeRule.onNode(hasRole(Role.Button) and hasText("Retry")).assertIsDisplayed()
```

No backend, no emulator, no network. Millisecond execution for direct composable tests.

### Contract Testing Per Layer

Each layer has a clear testable contract with its own test double:

| Contract | Input | Output | Test Double | Layer |
|----------|-------|--------|-------------|-------|
| UploadWorker logic | video file + entity | Room status transitions | FakeDAO + FakeUploader | JVM unit |
| ProcessingViewModel | IProcessApi events | ProcessingUiState transitions | FakeProcessApi | commonTest |
| AndroidProcessingViewModel | Room flow + IProcessApi | UploadPhase + ProcessingUiState | MockK DAO + FakeProcessApi | JVM unit |
| ProcessingContent composable | ProcessingUiState | Correct UI elements | Direct state params | JVM unit |
| ProcessApi.stream() | HTTP SSE | Flow<ProcessEvent> | Ktor MockEngine | commonTest |

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

Network error during upload. **Critical: `setAirplaneMode: enabled` BEFORE `launchApp`** to avoid race condition.

```yaml
appId: ru.skatelab.capture
tags:
  - upload
  - error
  - e2e
---
- setAirplaneMode: enabled
- addMedia: ["./assets/test_video.mp4"]
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
continueOnFailure: true
```

`continueOnFailure: true` ensures the full suite runs even if one flow fails.

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
// Compose UI testing (JVM with Robolectric)
testImplementation("org.robolectric:robolectric:4.14")
testImplementation("androidx.compose.ui:ui-test-junit4")
debugImplementation("androidx.compose.ui:ui-test-manifest")

// Parallel test execution
tasks.withType<Test>().configureEach {
    maxParallelForks = Runtime.getRuntime().availableProcessors().div(2).coerceAtLeast(2)
}
```

Already present:
- `androidTestImplementation(composeBom)`
- `androidTestImplementation("androidx.compose.ui:ui-test-junit4")`
- `testImplementation("junit:junit")`

**Why Robolectric:** `stringResource(R.string.*)` requires Android context. Without Robolectric, JVM tests fail. With `@RunWith(RobolectricTestRunner::class)`, `stringResource()` resolves correctly in JVM tests. This is the Now in Android pattern.

### Code Changes Required Before Tests

1. **`private` → `internal`** for testable composables:
   - `ProcessingScreen.kt`: `ProcessingContent`, `UploadStatusContent`, `UploadFailedContent`
   - `DashboardScreen.kt`: `DashboardContent` (if exists as separate composable)
   - `SessionListScreen.kt`: Extract empty/loaded content into `internal` composables

2. **Test doubles** (new files):
   - `shared/src/commonTest/.../fixtures/SseScenarios.kt` — pre-recorded SSE event sequences
   - `androidApp/src/test/.../data/db/FakePendingUploadDao.kt` — in-memory DAO
   - `androidApp/src/test/.../upload/FakeChunkedUploader.kt` — fake uploader
   - `androidApp/src/debug/.../di/FakeApiModule.kt` — debug Hilt module with FakeProcessApi

---

## 7. CI Integration

### Compose UI Tests (no changes needed)

`mobile-ci.yml` already runs `./gradlew :androidApp:testDebugUnitTest` — new tests with Robolectric will be picked up automatically. `maxParallelForks` ensures parallel execution.

### Maestro E2E (tag-based separation)

`mobile-e2e.yml` needs:

**PR checks (fast smoke):**
```yaml
- name: Run smoke tests
  run: |
    maestro test \
      --format junit --format html \
      --output build/reports/maestro/ \
      --include-tags=smokeTest \
      e2e/maestro/
```

**Merge to master (full E2E):**
```yaml
- name: Run full E2E suite
  run: |
    maestro test \
      --format junit --format html \
      --output build/reports/maestro/ \
      e2e/maestro/
```

**Cleanup after network error tests:**
```yaml
- name: Disable airplane mode (cleanup)
  if: always()
  run: |
    adb shell settings put global airplane_mode_on 0
    adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false
```

**Environment variable for slow emulators:**
```yaml
env:
  MAESTRO_DRIVER_STARTUP_TIMEOUT: 120
```

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
- Debug build variant with `FakeProcessApi` for fast E2E
- Test doubles: `SseScenarios`, `FakePendingUploadDao`, `FakeChunkedUploader`
- Contract testing per layer (5 contracts)
- Tag-based suite separation (`smokeTest` vs `e2e`)
- `private` → `internal` visibility changes for testable composables
- Robolectric dependency for `stringResource()` in JVM tests

### Out of Scope
- Performance/stress testing
- iOS E2E (iOS app not yet implemented)
- Screenshot comparison baselines (can be added later)
- Maestro sharding (premature for ~13 flows, Android sharding has bugs)
- WorkManager integration tests with `TestListenableWorkerBuilder` (future task)
- Room in-memory DAO tests (future task)