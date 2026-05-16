# Capture Test Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 bugs in CaptureSession model and manifest: (1) `actual_fps_verified` always false, (2) `fps` shows hardcoded 60 instead of actual measured FPS, (3) `first_frame_ns` always 0.

**Architecture:** Update `CaptureSession` data class (replace `videoFps` with `actualFps`, add `fpsVerified` and `firstFrameNs`), propagate through ViewModel → Repository → Export pipeline. Add `firstFrameNs` to `CameraRepository.RecordingStopResult` and `StopRecordingUseCase.StopResult`.

**Tech Stack:** Kotlin, Android, JUnit 5

---

## File Structure

| File | Change |
|------|--------|
| `CaptureSession.kt` | Replace `videoFps` with `actualFps`, add `fpsVerified`, `firstFrameNs` |
| `CameraRepository.kt` | Add `firstFrameNs` to `RecordingStopResult` |
| `CameraXRecorder.kt` | Return `firstFrameNs` from tracker |
| `CameraRepositoryImpl.kt` | Forward `firstFrameNs` |
| `StopRecordingUseCase.kt` | Add `firstFrameNs` to `StopResult` |
| `RecordingViewModel.kt` | Use `actualFps`/`fpsVerified`/`firstFrameNs` from stop result |
| `SessionRepositoryImpl.kt` | Serialize/deserialize new fields, backward compat |
| `ExportSessionUseCase.kt` | Use `session.actualFps`, call `actualFpsVerified()`, `firstFrameNs()` |
| `RecordingViewModelTest.kt` | Update `CaptureSession` construction + `stubStopResult` |
| `StopRecordingUseCaseTest.kt` | Add `firstFrameNs` to `RecordingStopResult` mocks |
| `SessionRepositoryImplTest.kt` | Update fields + backward compat test |
| `ZipExporterTest.kt` | Replace `videoFps` with `actualFps`/`fpsVerified`/`firstFrameNs` |
| `SessionListViewModelTest.kt` | Replace `videoFps` with new fields |
| `ExportViewModelTest.kt` | Replace `videoFps` with new fields |
| `ManifestBuilderTest.kt` | No change — already tests `actualFpsVerified` and `firstFrameNs` |

All paths relative to `mobile/app/src/main/java/ru/skatelab/capture/` for source, `mobile/app/src/test/java/ru/skatelab/capture/` for tests.

---

## Wave 1: Data model + pipeline

### Task 1: Update CaptureSession data model

**Files:**

- Modify: `domain/model/CaptureSession.kt`

- [ ] **Step 1: Replace videoFps with actualFps, add fpsVerified and firstFrameNs**

```kotlin
package ru.skatelab.capture.domain.model

import java.io.File

data class CaptureSession(
    val id: String,
    val videoFile: File,
    val imuLeftFile: File,
    val imuRightFile: File,
    val frameTimestampsFile: File,
    val manifestFile: File,
    val t0Ns: Long,
    val durationMs: Long,
    val actualFps: Int,
    val fpsVerified: Boolean,
    val firstFrameNs: Long,
    val timestampSource: String,
    val videoStartDelayMs: Long,
    val imuStartDelayMs: Map<SensorId, Long>,
    val calibration: Map<SensorId, CalibrationData>,
    val clockOffsetNs: Map<SensorId, Long> = emptyMap(),
    val createdAt: Long,
    val isComplete: Boolean,
)
```

- [ ] **Step 2: Commit**

```bash
git add domain/model/CaptureSession.kt
git commit -m "refactor(session): replace videoFps with actualFps, add fpsVerified and firstFrameNs"
```

---

### Task 2: Propagate firstFrameNs through CameraRepository + StopRecording pipeline

**Files:**

- Modify: `domain/repository/CameraRepository.kt`
- Modify: `data/camera/CameraXRecorder.kt`
- Modify: `data/camera/CameraRepositoryImpl.kt`
- Modify: `domain/usecase/StopRecordingUseCase.kt`

- [ ] **Step 1: Add firstFrameNs to CameraRepository.RecordingStopResult**

In `CameraRepository.kt`:

```kotlin
data class RecordingStopResult(
    val actualFps: Int,
    val fpsVerified: Boolean,
    val firstFrameNs: Long,
)
```

- [ ] **Step 2: Return firstFrameNs from CameraXRecorder.stopRecording()**

In `CameraXRecorder.kt`, update the `stopRecording()` method. Replace:

```kotlin
val actualFps = timestampTracker?.computeFps() ?: 0
val frameCount = timestampTracker?.getFrameCount() ?: 0

CameraRepository.RecordingStopResult(
    actualFps = actualFps,
    fpsVerified = frameCount > 10 && actualFps > 0,
)
```

With:

```kotlin
val actualFps = timestampTracker?.computeFps() ?: 0
val frameCount = timestampTracker?.getFrameCount() ?: 0
val firstFrameNs = timestampTracker?.getFirstFrameNs() ?: 0L

CameraRepository.RecordingStopResult(
    actualFps = actualFps,
    fpsVerified = frameCount > 10 && actualFps > 0,
    firstFrameNs = firstFrameNs,
)
```

- [ ] **Step 3: Pass firstFrameNs through CameraRepositoryImpl**

In `CameraRepositoryImpl.kt`, if `stopRecording()` maps `RecordingStopResult`, add `firstFrameNs` mapping. If it passes through directly, no change needed. Check the file and update accordingly.

- [ ] **Step 4: Add firstFrameNs to StopRecordingUseCase.StopResult**

In `StopRecordingUseCase.kt`:

```kotlin
data class StopResult(
    val actualFps: Int,
    val fpsVerified: Boolean,
    val firstFrameNs: Long,
)
```

And in the `invoke()` method, replace:

```kotlin
return Result.success(StopResult(actualFps = stopResult.actualFps, fpsVerified = stopResult.fpsVerified))
```

With:

```kotlin
return Result.success(StopResult(actualFps = stopResult.actualFps, fpsVerified = stopResult.fpsVerified, firstFrameNs = stopResult.firstFrameNs))
```

- [ ] **Step 5: Update StopRecordingUseCaseTest**

In `StopRecordingUseCaseTest.kt`, add `firstFrameNs` to all `RecordingStopResult` constructions:

```kotlin
CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true, firstFrameNs = 1_000_050_000_000L)
```

There are 3 occurrences (lines 32, 65, 84). Update all.

- [ ] **Step 6: Run StopRecordingUseCaseTest**

Run: `cd mobile && ./gradlew test --tests "ru.skatelab.capture.domain.usecase.StopRecordingUseCaseTest" -x lint`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add domain/repository/CameraRepository.kt data/camera/CameraXRecorder.kt data/camera/CameraRepositoryImpl.kt domain/usecase/StopRecordingUseCase.kt domain/usecase/StopRecordingUseCaseTest.kt
git commit -m "feat(camera): propagate firstFrameNs through RecordingStopResult pipeline"
```

---

### Task 3: Update RecordingViewModel + its test

**Files:**

- Modify: `presentation/recording/RecordingViewModel.kt`
- Modify: `presentation/recording/RecordingViewModelTest.kt`

- [ ] **Step 1: Update ViewModel fields and CaptureSession construction**

In `RecordingViewModel.kt`:

Replace `private var actualVideoFps: Int = 60` with:

```kotlin
private var actualVideoFps: Int = 0
private var fpsVerified: Boolean = false
private var firstFrameNs: Long = 0L
```

In `stopRecording()` success handler, replace:

```kotlin
stopRecordingUseCase()
    .onSuccess { stopResult ->
        actualVideoFps = stopResult.actualFps
        appLogger.i(TAG, "Stopped: actualFps=${stopResult.actualFps} verified=${stopResult.fpsVerified}")
    }
```

With:

```kotlin
stopRecordingUseCase()
    .onSuccess { stopResult ->
        actualVideoFps = stopResult.actualFps
        fpsVerified = stopResult.fpsVerified
        firstFrameNs = stopResult.firstFrameNs
        appLogger.i(TAG, "Stopped: actualFps=${stopResult.actualFps} verified=${stopResult.fpsVerified} firstFrameNs=${stopResult.firstFrameNs}")
    }
```

In `CaptureSession(...)` constructor, replace `videoFps = actualVideoFps,` with:

```kotlin
actualFps = actualVideoFps,
fpsVerified = fpsVerified,
firstFrameNs = if (startInfo.t0Ns > 0 && firstFrameNs > 0) firstFrameNs - startInfo.t0Ns else 0L,
```

- [ ] **Step 2: Update RecordingViewModelTest**

In `RecordingViewModelTest.kt`, update `stubStopResult`:

```kotlin
private val stubStopResult =
    StopRecordingUseCase.StopResult(
        actualFps = 30,
        fpsVerified = true,
        firstFrameNs = 1_000_050_000_000L,
    )
```

- [ ] **Step 3: Run RecordingViewModelTest**

Run: `cd mobile && ./gradlew test --tests "ru.skatelab.capture.presentation.recording.RecordingViewModelTest" -x lint`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add presentation/recording/RecordingViewModel.kt presentation/recording/RecordingViewModelTest.kt
git commit -m "fix(viewmodel): use actualFps, fpsVerified, firstFrameNs in CaptureSession"
```

---

### Task 4: Update SessionRepositoryImpl + tests with backward compat

**Files:**

- Modify: `data/repository/SessionRepositoryImpl.kt`
- Modify: `data/repository/SessionRepositoryImplTest.kt`

- [ ] **Step 1: Update sessionToJson**

In `SessionRepositoryImpl.kt`, replace `appendLine("  \"videoFps\": ${s.videoFps},")` with:

```kotlin
appendLine("  \"actualFps\": ${s.actualFps},")
appendLine("  \"fpsVerified\": ${s.fpsVerified},")
appendLine("  \"firstFrameNs\": ${s.firstFrameNs},")
```

- [ ] **Step 2: Update jsonToSession with backward compat**

In `jsonToSession()`, replace:

```kotlin
videoFps = o.getInt("videoFps"),
```

With:

```kotlin
actualFps = o.optInt("actualFps", o.optInt("videoFps", 0)),
fpsVerified = o.optBoolean("fpsVerified", false),
firstFrameNs = o.optLong("firstFrameNs", 0L),
```

Backward compat: `actualFps` falls back to `videoFps` from old JSON, `fpsVerified` defaults `false`, `firstFrameNs` defaults `0L`.

- [ ] **Step 3: Update test helper createSession()**

In `SessionRepositoryImplTest.kt`, update `createSession()`. Replace:

```kotlin
videoFps = 60,
```

With:

```kotlin
actualFps = 30,
fpsVerified = true,
firstFrameNs = 50_000_000L,
```

- [ ] **Step 4: Update round-trip assertions**

In `SessionRepositoryImplTest.kt`, replace `assertEquals(session.videoFps, s.videoFps)` with:

```kotlin
assertEquals(session.actualFps, s.actualFps)
assertEquals(session.fpsVerified, s.fpsVerified)
assertEquals(session.firstFrameNs, s.firstFrameNs)
```

- [ ] **Step 5: Add backward compat test**

Add to `SessionRepositoryImplTest.kt`:

```kotlin
@Test
fun getSession_backwardCompat_loadsOldFormatJson() =
    runTest {
        val sessionDir = File(tempDir, "sessions/old-session")
        sessionDir.mkdirs()
        val videoPath = File(sessionDir, "video.mp4").absolutePath
        val leftPath = File(sessionDir, "imu_left.binpb").absolutePath
        val rightPath = File(sessionDir, "imu_right.binpb").absolutePath
        val framesPath = File(sessionDir, "frames.csv").absolutePath
        val manifestPath = File(sessionDir, "manifest.json").absolutePath
        val oldJson = """
        {
          "id": "old-session",
          "videoPath": "$videoPath",
          "imuLeftPath": "$leftPath",
          "imuRightPath": "$rightPath",
          "frameTimestampsPath": "$framesPath",
          "manifestPath": "$manifestPath",
          "t0Ns": 1000000000,
          "durationMs": 5000,
          "videoFps": 60,
          "timestampSource": "REALTIME",
          "videoStartDelayMs": 120,
          "imuStartDelayMs": {"LEFT": 480, "RIGHT": 490},
          "calibration": {"LEFT": {"quatRef": [1.0,0.0,0.0,0.0],"calibratedAt": 1000}, "RIGHT": {"quatRef": [0.0,1.0,0.0,0.0],"calibratedAt": 2000}},
          "clockOffsetNs": {"LEFT": 12345, "RIGHT": 67890},
          "createdAt": 1700000000000,
          "isComplete": true
        }
        """.trimIndent()
        File(sessionDir, "meta.json").writeText(oldJson)

        val loaded = repository.getSession("old-session")
        assertNotNull("Old-format session should load", loaded)
        loaded!!.let { s ->
            assertEquals("actualFps should fall back to videoFps", 60, s.actualFps)
            assertEquals("fpsVerified should default to false", false, s.fpsVerified)
            assertEquals("firstFrameNs should default to 0", 0L, s.firstFrameNs)
        }
    }
```

- [ ] **Step 6: Run SessionRepositoryImplTest**

Run: `cd mobile && ./gradlew test --tests "ru.skatelab.capture.data.repository.SessionRepositoryImplTest" -x lint`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add data/repository/SessionRepositoryImpl.kt data/repository/SessionRepositoryImplTest.kt
git commit -m "fix(session): serialize actualFps/fpsVerified/firstFrameNs with backward compat"
```

---

## Wave 2: Export pipeline + remaining test fixes

### Task 5: Update ExportSessionUseCase

**Files:**

- Modify: `domain/usecase/ExportSessionUseCase.kt`

- [ ] **Step 1: Update buildManifest() video block**

Replace:

```kotlin
video {
    filename(session.videoFile.name)
    fps(session.videoFps)
    timestampSource(session.timestampSource)
    videoStartDelayMs(session.videoStartDelayMs)
    frameTimestampsFile(session.frameTimestampsFile.name)
}
```

With:

```kotlin
video {
    filename(session.videoFile.name)
    fps(session.actualFps)
    actualFpsVerified(session.fpsVerified)
    timestampSource(session.timestampSource)
    videoStartDelayMs(session.videoStartDelayMs)
    frameTimestampsFile(session.frameTimestampsFile.name)
    firstFrameNs(session.firstFrameNs)
}
```

- [ ] **Step 2: Commit**

```bash
git add domain/usecase/ExportSessionUseCase.kt
git commit -m "fix(export): use actualFps, fpsVerified, firstFrameNs in manifest"
```

---

### Task 6: Update remaining test files that reference videoFps

**Files:**

- Modify: `data/export/ZipExporterTest.kt`
- Modify: `presentation/session/SessionListViewModelTest.kt`
- Modify: `presentation/export/ExportViewModelTest.kt`

- [ ] **Step 1: Update ZipExporterTest.kt**

In `createSessionWithFiles()`, replace `videoFps = 60,` with:

```kotlin
actualFps = 30,
fpsVerified = true,
firstFrameNs = 50_000_000L,
```

- [ ] **Step 2: Update SessionListViewModelTest.kt**

In `stubSession`, replace `videoFps = 60,` with:

```kotlin
actualFps = 30,
fpsVerified = true,
firstFrameNs = 50_000_000L,
```

- [ ] **Step 3: Update ExportViewModelTest.kt**

In the test session construction, replace `videoFps = 60,` with:

```kotlin
actualFps = 30,
fpsVerified = true,
firstFrameNs = 50_000_000L,
```

- [ ] **Step 4: Run full test suite**

Run: `cd mobile && ./gradlew test -x lint`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add data/export/ZipExporterTest.kt presentation/session/SessionListViewModelTest.kt presentation/export/ExportViewModelTest.kt
git commit -m "test: update CaptureSession constructions for actualFps/fpsVerified/firstFrameNs"
```

---

### Task 7: Build + device verification

- [ ] **Step 1: Build debug APK**

Run: `cd mobile && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 2: Install on device**

Run: `adb install -r mobile/app/build/outputs/apk/debug/app-debug.apk`

- [ ] **Step 3: Record 5-10 second session, export, verify manifest**

```bash
adb shell ls -lt /sdcard/Android/data/ru.skatelab.capture/files/Download/skatelab_exports/ | head -3
adb pull /sdcard/Android/data/ru.skatelab.capture/files/Download/skatelab_exports/<latest>.zip /tmp/verify.zip
unzip -p /tmp/verify.zip manifest.json | python3 -m json.tool
```

Expected:
- `"fps": ~30` (actual measured, not 60)
- `"actual_fps_verified": true`
- `"first_frame_ns": <non-zero value>`