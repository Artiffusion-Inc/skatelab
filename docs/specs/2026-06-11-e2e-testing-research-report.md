# E2E Testing: Research Synthesis Report

> **Date:** 2026-06-11
> **Agents:** 3 specialized researchers (Compose UI, Maestro E2E, Async Pipeline)
> **Sources:** Web search, GitHub projects, Maestro docs, existing codebase analysis

---

## Key Findings

### 1. Compose UI Testing: Robolectric is Required

**Problem:** SkateLab composables use `stringResource(R.string.*)` which is an Android framework call. It fails in plain JVM tests.

**Solution:** Add Robolectric to `testImplementation`. This is the Now in Android (NiA) pattern — Compose UI tests run as JVM tests with `@RunWith(RobolectricTestRunner::class)` and `stringResource()` resolves correctly. Millisecond execution, no emulator.

**Code change:** `build.gradle.kts`:
```kotlin
testImplementation("org.robolectric:robolectric:4.14")
testImplementation("androidx.compose.ui:ui-test-junit4")
```

**Source:** Now in Android wiki — "Testing strategy and how to test"; Android developer docs on Compose testing.

---

### 2. Private → Internal for Testable Composables

**Problem:** `ProcessingContent`, `UploadStatusContent`, `UploadFailedContent` are `private` — JVM tests in `test/` cannot access them.

**Solution:** Change `private` to `internal` (Kotlin convention for "package-private but testable"). NiA uses `internal` for all testable composables.

**Affected files:**
- `ProcessingScreen.kt`: `ProcessingContent`, `UploadStatusContent`, `UploadFailedContent`
- `DashboardScreen.kt`: `DashboardContent` (if exists as separate composable)
- `SessionListScreen.kt`: Extract empty/loaded content into `internal` composables

---

### 3. Progress Bar Testing: `hasProgressBarRangeInfo()`

**Discovery:** Compose `LinearProgressIndicator` exposes `ProgressBarRangeInfo` semantics automatically. You can assert exact progress values:

```kotlin
composeRule.onNode(
    hasProgressBarRangeInfo(ProgressBarRangeInfo(current = 0.5f, range = 0f..1f, steps = 0))
).assertIsDisplayed()
```

This is more robust than `onNodeWithText("50%")` because it verifies the actual semantic progress value. Use BOTH: range info for the widget + text for the user-facing label.

**Source:** Medium article by Adrian Gl; Compose semantics documentation.

---

### 4. Snackbar Testing: `useUnmergedTree = true`

**Problem:** Snackbar merges its children into the parent semantic tree. `onNodeWithText()` may not find it.

**Solution:**
```kotlin
composeRule.onNode(hasText("Unsupported video format"), useUnmergedTree = true)
    .assertIsDisplayed()
```

Also need `waitUntil` because `showSnackbar()` is suspending and renders asynchronously.

---

### 5. Tag-Based Suite Separation (Not Sharding)

**Key insight:** Maestro `--shards N` distributes flow files across devices, but Android sharding has known bugs (GitHub issue #1853 — gRPC connection errors). For ~13 flows, sharding is premature.

**Recommended:** Tag-based suite separation instead:

| Suite | Tag | Runs on | Timeout |
|-------|-----|---------|---------|
| Smoke | `smokeTest` | Every PR | ~2 min |
| Full E2E | `e2e` | Merge to master / nightly | ~10 min |

```bash
# PR: fast smoke tests
maestro test --include-tags=smokeTest e2e/maestro/

# Merge: full suite
maestro test e2e/maestro/
```

**Source:** Maestro v1.37+ release notes; Doist and Chick-fil-A engineering blog posts on Maestro CI.

---

### 6. `setAirplaneMode` Timing: Enable BEFORE `launchApp`

**Problem:** Race condition — enabling airplane mode takes 1-3 seconds. If upload fires before mode is active, test doesn't trigger error path.

**Solution:**
```yaml
- setAirplaneMode: enabled   # BEFORE launchApp
- addMedia: ["./assets/test_video.mp4"]
- launchApp
```

Always clean up: `setAirplaneMode: disabled` at end + ADB cleanup in CI `always()` step.

---

### 7. Debug Build with FakeProcessApi for Fast E2E

**Architecture insight:** `IProcessApi` interface already exists in shared/commonMain. `FakeProcessApi` already exists in `ProcessingViewModelTest`. 

**New idea:** Create a debug-only Hilt module that injects `FakeProcessApi` with pre-recorded SSE events (`SseScenarios.HAPPY_PATH`). This makes Maestro E2E flows run in <1s instead of 30-120s, because the fake API returns instant responses.

```kotlin
// androidApp/src/debug/java/ru/skatelab/capture/di/FakeApiModule.kt
@Module
@InstallIn(SingletonComponent::class)
object FakeApiModule {
    @Provides @Named("processApi")
    fun provideFakeProcessApi(): IProcessApi =
        FakeProcessApi(streamEvents = SseScenarios.HAPPY_PATH)
}
```

**Trade-off:** This tests UI flow but NOT real backend integration. Keep one real-backend flow (`upload-pipeline.yaml` tagged `e2e`) for CI merge-to-master.

---

### 8. Test Doubles: FakePendingUploadDao + SseScenarios

**Current gap:** No `FakePendingUploadDao` for JVM tests. No `SseScenarios` fixtures.

**Recommended:**
- `FakePendingUploadDao` — in-memory map implementing `PendingUploadDao` interface
- `SseScenarios` — pre-recorded SSE event sequences (happy path, network error, slow progress)
- Extract UploadWorker business logic into a testable function: `suspend fun uploadWorkerLogic(uploadId, dao, uploader, client): Result`

These enable full JVM-level testing of the upload→processing pipeline without Room, S3, or backend.

---

### 9. Contract Testing Per Layer

Each layer has a clear testable contract:

| Contract | Input | Output | Test Double |
|----------|-------|--------|-------------|
| UploadWorker | video file + entity | Room status transitions | FakeDAO + FakeUploader |
| ProcessingViewModel | IProcessApi events | ProcessingUiState transitions | FakeProcessApi |
| AndroidProcessingViewModel | Room flow + IProcessApi | UploadPhase + ProcessingUiState | MockK DAO + FakeProcessApi |
| ProcessingContent composable | ProcessingUiState | Correct UI elements | Direct state params |
| ProcessApi.stream() | HTTP SSE | Flow<ProcessEvent> | Ktor MockEngine |

---

### 10. Parallel JVM Tests

Current `build.gradle.kts` sets `maxParallelForks = 1`. Increase for faster test execution:

```kotlin
tasks.withType<Test>().configureEach {
    maxParallelForks = Runtime.getRuntime().availableProcessors().div(2).coerceAtLeast(2)
}
```

Each test creates its own fakes (no shared state), so parallel execution is safe.

---

### 11. CI Improvements for Maestro

| Improvement | Command / Config | Benefit |
|-------------|----------------|---------|
| HTML reports | `--format html` alongside `--format junit` | Rich visual reports |
| Tag-based filtering | `--include-tags=smokeTest` | Fast PR feedback |
| Startup timeout | `MAESTRO_DRIVER_STARTUP_TIMEOUT=120` | Slow CI emulator tolerance |
| Continue on failure | `continueOnFailure: true` in config.yaml | Don't stop suite on first failure |
| ADB cleanup | `adb shell settings put global airplane_mode_on 0` in `always()` step | Reset state after network error tests |

---

### 12. Test Video Asset: Direct Git Commit

Maestro `addMedia` supports MP4 (H.264, AAC). Commit `test_video.mp4` directly to git — no LFS needed at <5MB. Create from existing session footage:

```bash
ffmpeg -i source.mp4 -ss 0:00 -t 0:08 -c:v libx264 -c:a aac -b:v 1M -s 640x480 \
  mobile/e2e/maestro/assets/test_video.mp4
```

---

## Recommendations for Spec Update

The current spec (`docs/specs/2026-06-11-e2e-testing-design.md`) should be updated with:

1. **Robolectric dependency** — add to Section 6 (Build Dependencies)
2. **`private` → `internal`** visibility change — add to implementation notes
3. **`hasProgressBarRangeInfo()`** pattern — update Compose test descriptions in Section 3
4. **Tag-based suite separation** — update Section 4 (Maestro flows) with `smokeTest` vs `e2e` tags
5. **Debug build with FakeProcessApi** — add new Section for fast E2E variant
6. **Test doubles** (FakePendingUploadDao, SseScenarios) — add new Section
7. **Contract testing per layer** — add architecture note
8. **CI improvements** — update Section 7
9. **`setAirplaneMode: enabled` BEFORE `launchApp`** — fix upload-network-error.yaml
10. **`continueOnFailure: true`** in config.yaml