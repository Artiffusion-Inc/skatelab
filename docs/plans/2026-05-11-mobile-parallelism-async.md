# Mobile Parallelism & Async Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical concurrency bugs, eliminate UI jank/ANR, and improve BLE/IMU pipeline reliability in the mobile app.

**Architecture:** 5 execution phases optimized for parallelism. Phase 1 runs 9 independent tasks concurrently. Each phase must pass full unit test suite before next phase starts. Critical path: T2→T8→T9→T11→T14→T15 (BleManager→ImuCollector→ImuStreamWriter).

**Tech Stack:** Kotlin, coroutines, Android BLE API, Camera2 API, Protobuf, Hilt DI

**Spec:** `docs/specs/2026-05-11-mobile-parallelism-async-design.md`
**Review Round 1:** `docs/specs/2026-05-11-plan-review-design.md`
**Review Round 2:** `docs/specs/2026-05-11-plan-review-round2-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt` | Modify | Store ScanCallback, fix connect leak, increase buffer, overflow logging, GATT write queue, thread-safe recordingSensors, atomic state updates, writeQueue cleanup |
| `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt` | Modify | Replace mutableMapOf with ConcurrentHashMap |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt` | Modify | Reorder stop calls, add onCleared cleanup, use applicationContext, try/catch around imuCollector.stop() |
| `mobile/app/src/main/java/ru/skatelab/capture/data/recording/ImuCollector.kt` | Modify | Per-sensor collectors on Dispatchers.IO, AtomicInteger counts, inject ioDispatcher, ConcurrentHashMap for shared maps, cancel all jobs on start, clear lastSampleNs on stop |
| `mobile/app/src/main/java/ru/skatelab/capture/di/AppModule.kt` | Modify | Remove ImuIo single-thread executor |
| `mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt` | Modify | Replace Thread.sleep with suspendCancellableCoroutine, UNKNOWN timestamp fallback, guard against double startRecording() |
| `mobile/app/src/main/java/ru/skatelab/capture/data/camera/FrameTimestampTracker.kt` | Modify | Bounded LinkedBlockingQueue instead of unbounded list |
| `mobile/app/src/main/java/ru/skatelab/capture/data/repository/SessionRepositoryImpl.kt` | Modify | Add withContext(Dispatchers.IO), re-throw CancellationException |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/export/ExportViewModel.kt` | Modify | Wrap entire export in withContext(Dispatchers.IO), try/finally for _isExporting |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModel.kt` | Modify | Throttle preview quaternion updates |
| `mobile/app/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt` | Modify | Add flush(), keep @Synchronized for defense-in-depth |
| `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt` | Modify | Add warmedUp flags |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/SessionState.kt` | Modify | Thread-safe calibration via MutableStateFlow |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt` | Modify | Move mkdirs out of Composable |

---

## Phase 1: Independent fixes, max parallelism (9 tasks)

9 tasks with no file conflicts. Run concurrently.

---

### Task 1: P2 — Reorder imuCollector.stop() before stopForegroundService(), add try/catch

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt:243-246`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt`

**Review fix R2-5:** `imuCollector.stop()` exception kills `stopRecording()` — if `ImuStreamWriter.close()` throws, entire coroutine cancels, UI stuck in "recording". Wrap in try/catch.

- [ ] **Step 1: Write failing test**

Add to `RecordingViewModelTest.kt`:

```kotlin
@Test
fun stopRecording_flushesImuBeforeStoppingService() = testScope.runTest {
    coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
    coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
        Result.success(stubStartInfo)
    coEvery { stopRecordingUseCase() } returns Result.success(Unit)
    coEvery { sessionRepository.saveSession(any()) } returns Result.success(Unit)

    val stopOrder = mutableListOf<String>()
    every { imuCollector.stop() } answers {
        stopOrder.add("imu")
        emptyMap<SensorId, Int>()
    }
    every { context.startService(any()) } answers {
        stopOrder.add("service")
        true
    }

    viewModel.prepareCamera(outputDir)
    runCurrent()

    viewModel.startRecording(outputDir, emptyMap(), context)
    runCurrent()

    viewModel.stopRecording(context)
    runCurrent()

    assertEquals("IMU flush must happen before service stop", listOf("imu", "service"), stopOrder)
}

@Test
fun stopRecording_imuCollectorExceptionDoesNotKillStopRecording() = testScope.runTest {
    coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
    coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
        Result.success(stubStartInfo)
    coEvery { stopRecordingUseCase() } returns Result.success(Unit)

    every { imuCollector.stop() } throws RuntimeException("flush failed")

    viewModel.prepareCamera(outputDir)
    runCurrent()

    viewModel.startRecording(outputDir, emptyMap(), context)
    runCurrent()

    // Should NOT throw — exception is caught
    viewModel.stopRecording(context)
    runCurrent()

    // UI state is still updated even if IMU flush failed
    assertEquals(false, viewModel.isRecording.value)
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "RecordingViewModelTest.stopRecording_flushesImuBeforeStoppingService"`
Expected: FAIL — current code calls stopForegroundService before imuCollector.stop

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "RecordingViewModelTest.stopRecording_imuCollectorExceptionDoesNotKillStopRecording"`
Expected: FAIL — exception propagates uncaught

- [ ] **Step 3: Fix RecordingViewModel.kt**

In `RecordingViewModel.kt`, in `stopRecording()` method, change lines 243-246 from:

```kotlin
_isRecording.value = false
stopForegroundService(context)

val imuCounts = withContext(Dispatchers.IO) { imuCollector.stop() }
```

to:

```kotlin
// R2-5: Wrap IMU stop in try/catch so exception doesn't kill the coroutine
val imuCounts = try {
    withContext(Dispatchers.IO) { imuCollector.stop() }
} catch (e: Exception) {
    appLogger.e(TAG, "IMU flush failed: ${e.message}")
    emptyMap<SensorId, Int>()
}
appLogger.i(TAG, "IMU samples: $imuCounts")

_isRecording.value = false
stopForegroundService(context)
```

Also remove the duplicate log line at 247 (`appLogger.i(TAG, "IMU samples: $imuCounts")`) since we moved it up.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "RecordingViewModelTest.stopRecording_flushesImuBeforeStoppingService" --tests "RecordingViewModelTest.stopRecording_imuCollectorExceptionDoesNotKillStopRecording"`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 6: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt
git commit -m "fix(recording): flush IMU data before stopping foreground service, add try/catch"
```

---

### Task 2: P4 — Fix BLE stopScan callback mismatch + @Volatile + try-catch

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt:99-136`

**Review fix I2:** Set `activeScanCallback` BEFORE `scanner.startScan()` to prevent race where stopScan is called before startScan completes.
**Review fix R2-13:** `activeScanCallback` not cleaned if `startScan()` throws (SecurityException on Android 12+).
**Review fix R2-14:** `activeScanCallback` not `@Volatile` — TOCTOU race if stopScan called off-Main.

- [ ] **Step 1: Add @Volatile field for ScanCallback reference**

In `BleManager.kt`, add field after `recordingSensors` (line ~86):

```kotlin
@Volatile
private var activeScanCallback: android.bluetooth.le.ScanCallback? = null
```

- [ ] **Step 2: Store callback in startScan() — set BEFORE startScan call, with try-catch**

In `startScan()`, replace lines 115-128:

```kotlin
val callback = object : android.bluetooth.le.ScanCallback() {
    override fun onScanResult(callbackType: Int, result: android.bluetooth.le.ScanResult) {
        val device = result.device
        logi("Scan result: ${device.name} @ ${device.address} RSSI=${result.rssi}")
        val name = device.name ?: "WT901"
        val address = device.address
        foundDevices[address] = ScanResult(name, address, result.rssi)
        _scanResults.value = foundDevices.values.toList()
    }

    override fun onScanFailed(errorCode: Int) {
        loge("BLE scan failed: errorCode=$errorCode")
        activeScanCallback = null
    }
}
// Store BEFORE startScan to prevent stopScan/startScan race (I2)
activeScanCallback = callback
try {
    scanner.startScan(listOf(filter), settings, callback)
} catch (e: SecurityException) {
    loge("startScan failed: ${e.message}")
    activeScanCallback = null
}
```

- [ ] **Step 3: Use stored callback in stopScan()**

Replace `stopScan()` (lines 131-136) with:

```kotlin
@SuppressLint("MissingPermission")
fun stopScan() {
    val callback = activeScanCallback ?: run {
        logw("stopScan called but no active scan callback")
        return
    }
    bluetoothAdapter?.bluetoothLeScanner?.stopScan(callback)
    activeScanCallback = null
}
```

- [ ] **Step 4: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt
git commit -m "fix(ble): store ScanCallback before startScan, add @Volatile, catch SecurityException"
```

---

### Task 3: P7 — Add Dispatchers.IO to SessionRepositoryImpl + Export, fix cancellation handling

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/repository/SessionRepositoryImpl.kt:42-63`
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/export/ExportViewModel.kt:36-58`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/data/repository/SessionRepositoryImplTest.kt`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/presentation/export/ExportViewModelTest.kt`

**Review fix I8:** Wrap ENTIRE export body in `withContext(IO)`, not just `getSession()`. The heavy operation is `exportSessionUseCase.invoke()` (JSON + zip + file copy), which was still on Main.
**Review fix R2-7:** `_isExporting` stuck on cancellation — `_isExporting.value = false` after `withContext(IO)` block; `CancellationException` skips it.
**Review fix R2-16:** `runCatching` swallows `CancellationException` in `deleteSession` — prevents proper coroutine cancellation.

- [ ] **Step 1: Wrap SessionRepositoryImpl I/O methods, re-throw CancellationException**

In `SessionRepositoryImpl.kt`, wrap `getSessions()`, `getSession()`, `deleteSession()` with `withContext(Dispatchers.IO)`:

```kotlin
override suspend fun getSessions(): List<CaptureSession> = withContext(Dispatchers.IO) {
    if (!sessionsDir.exists()) return@withContext emptyList()
    sessionsDir.listFiles()
        ?.filter { it.isDirectory }
        ?.mapNotNull { dir ->
            val metaFile = File(dir, META_FILE)
            if (metaFile.exists()) jsonToSession(metaFile.readText(), dir) else null
        }
        ?: emptyList()
}

override suspend fun getSession(id: String): CaptureSession? = withContext(Dispatchers.IO) {
    val dir = File(sessionsDir, id)
    val metaFile = File(dir, META_FILE)
    if (!metaFile.exists()) return@withContext null
    jsonToSession(metaFile.readText(), dir)
}

override suspend fun deleteSession(id: String): Result<Unit> = try {
    withContext(Dispatchers.IO) {
        val dir = File(sessionsDir, id)
        if (dir.exists()) dir.deleteRecursively()
    }
    Result.success(Unit)
} catch (e: kotlinx.coroutines.CancellationException) {
    throw e // R2-16: never swallow CancellationException
} catch (e: Exception) {
    Result.failure(e)
}
```

- [ ] **Step 2: Wrap ENTIRE export body in withContext(IO), add try/finally**

In `ExportViewModel.kt`, replace `export()` method:

```kotlin
fun export(sessionId: String, outputDir: File) {
    viewModelScope.launch {
        _isExporting.value = true
        _error.value = null

        try {
            withContext(kotlinx.coroutines.Dispatchers.IO) {
                val session = sessionRepository.getSession(sessionId)
                if (session == null) {
                    _error.value = "Session not found: $sessionId"
                    return@withContext
                }

                val outputZip = File(outputDir, "${session.id}.zip")
                exportSessionUseCase.invoke(session, outputZip)
                    .onSuccess {
                        _exportPath.value = it.absolutePath
                        _exportFile.value = it
                    }
                    .onFailure { _error.value = it.message }
            }
        } finally {
            // R2-7: always reset _isExporting even if coroutine cancelled
            _isExporting.value = false
        }
    }
}
```

Add import: `import kotlinx.coroutines.withContext`

- [ ] **Step 3: Fix ExportViewModelTest constructor mismatch (R2-20)**

In `ExportViewModelTest.kt`, verify constructor matches actual signature. If test passes 3 args but constructor takes 2, fix the test to match.

- [ ] **Step 4: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/repository/SessionRepositoryImpl.kt mobile/app/src/main/java/ru/skatelab/capture/presentation/export/ExportViewModel.kt mobile/app/src/test/java/ru/skatelab/capture/presentation/export/ExportViewModelTest.kt
git commit -m "fix(io): wrap entire export in Dispatchers.IO, fix CancellationException handling, try/finally for _isExporting"
```

---

### Task 4: P12 — Fix _addressMap race condition

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt:21`

- [ ] **Step 1: Replace mutableMapOf with ConcurrentHashMap**

In `BleRepositoryImpl.kt:21`, change:

```kotlin
private val _addressMap = mutableMapOf<SensorId, String>()
```

to:

```kotlin
private val _addressMap = java.util.concurrent.ConcurrentHashMap<SensorId, String>()
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt
git commit -m "fix(ble): use ConcurrentHashMap for addressMap thread safety"
```

---

### Task 5: P13 — Throttle preview quaternion updates

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModel.kt:66-74`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModelTest.kt`

- [ ] **Step 1: Add sample operator to preview collection**

In `CalibrationViewModel.kt`, add import:

```kotlin
import kotlinx.coroutines.flow.sample
```

In `startPreview()`, change the collection block (lines 66-74):

```kotlin
if (previewJob?.isActive != true) {
    previewJob = viewModelScope.launch {
        bleRepository.imuSamples
            .sample(100) // 10Hz preview updates instead of ~100Hz
            .collect { (id, sample) ->
                when (id) {
                    SensorId.LEFT -> _leftQuat.value = sample.toQuaternionPreview()
                    SensorId.RIGHT -> _rightQuat.value = sample.toQuaternionPreview()
                }
            }
    }
}
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModel.kt
git commit -m "perf(calibration): throttle preview to 10Hz to reduce recompositions"
```

---

### Task 6: P17 — Add warmup state to CalibrateSensorUseCase

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:80-137`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Add warmedUp flags**

In `CalibrateSensorUseCase.collectStillSamplesBoth()`, add warmedUp flags after line 87:

```kotlin
var leftWarmedUp = false
var rightWarmedUp = false
```

In the collector lambda, change the warmup check to use stateful flags:

```kotlin
bleRepository.imuSamples.collect { (sensorId, sample) ->
    // Skip warm-up zeros: check acc magnitude only until first real sample
    val isWarmedUp = when (sensorId) {
        SensorId.LEFT -> leftWarmedUp
        SensorId.RIGHT -> rightWarmedUp
    }
    if (!isWarmedUp) {
        val accMag = sqrt(
            (sample.accX * sample.accX +
                sample.accY * sample.accY +
                sample.accZ * sample.accZ).toDouble()
        ).toFloat()
        if (accMag < WARMUP_MIN_ACC_MAGNITUDE) return@collect
        when (sensorId) {
            SensorId.LEFT -> leftWarmedUp = true
            SensorId.RIGHT -> rightWarmedUp = true
        }
    }
    val gyroMagDegS = sqrt(
        (sample.gyroX * sample.gyroX +
            sample.gyroY * sample.gyroY +
            sample.gyroZ * sample.gyroZ).toDouble()
    )
    val isStill = gyroMagDegS <= ANGULAR_VELOCITY_THRESHOLD_DEG_S
    when (sensorId) {
        SensorId.LEFT -> {
            leftReceived++
            if (isStill) leftSamples.add(sample)
        }
        SensorId.RIGHT -> {
            rightReceived++
            if (isStill) rightSamples.add(sample)
        }
    }
}
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt
git commit -m "refactor(calibration): skip acc magnitude check after warmup"
```

---

### Task 10 (moved to Phase 1): P15 — FrameTimestampTracker bounded LinkedBlockingQueue

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/FrameTimestampTracker.kt`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/data/camera/FrameTimestampTrackerTest.kt`

**Review fix R2-8:** `FrameTimestampTracker` scope injection chain incomplete — plan requires `CoroutineScope` but never specifies how `Camera2Recorder`/`CameraRepositoryImpl` obtain it; no scope cancellation; no test for new constructor. Use simpler `LinkedBlockingQueue` bounded approach instead of full coroutine rewrite; avoids DI chain change.

- [ ] **Step 1: Rewrite FrameTimestampTracker with LinkedBlockingQueue**

Replace `FrameTimestampTracker.kt`:

```kotlin
package ru.skatelab.capture.data.camera

import java.io.File
import java.io.FileWriter
import java.util.concurrent.LinkedBlockingQueue
import kotlin.math.roundToInt

class FrameTimestampTracker {

    private var writer: FileWriter? = null
    private var frameCount = 0
    private var firstFrameNs: Long = 0L
    private var lastFrameNs: Long = 0L
    private var writerThread: Thread? = null

    // R2-8: Bounded queue instead of unbounded mutableList or coroutine Channel
    private val queue = LinkedBlockingQueue<FrameEvent>(1000)
    @Volatile
    private var running = false

    private data class FrameEvent(val index: Int, val timestampNs: Long)

    fun open(file: File) {
        writer = FileWriter(file).apply {
            write("frame_index,timestamp_ns\n")
            flush()
        }
        running = true
        writerThread = Thread({
            var framesSinceFlush = 0
            while (running || queue.isNotEmpty()) {
                val event = queue.poll(100, java.util.concurrent.TimeUnit.MILLISECONDS)
                if (event != null) {
                    val w = writer ?: break
                    w.write("${event.index},${event.timestampNs}\n")
                    framesSinceFlush++
                    if (framesSinceFlush >= 30) {
                        w.flush()
                        framesSinceFlush = 0
                    }
                }
            }
            try {
                writer?.flush()
            } catch (_: Exception) {}
        }, "FrameTimestampWriter").apply { isDaemon = true; start() }
    }

    fun onFrame(timestampNs: Long) {
        val index = frameCount
        if (frameCount == 0) {
            firstFrameNs = timestampNs
        }
        lastFrameNs = timestampNs
        frameCount++
        queue.offer(FrameEvent(index, timestampNs))
    }

    fun close() {
        running = false
        writerThread?.join(500L)
        writerThread = null
        writer?.close()
        writer = null
    }

    fun getFrameCount(): Int = frameCount

    fun computeFps(): Int {
        if (frameCount < 2) return 0
        val elapsedSec = (lastFrameNs - firstFrameNs) / 1_000_000_000.0
        if (elapsedSec <= 0.0) return 0
        val intervals = frameCount - 1
        return (intervals / elapsedSec).roundToInt()
    }

    fun getFirstFrameNs(): Long = firstFrameNs
    fun getLastFrameNs(): Long = lastFrameNs
}
```

- [ ] **Step 2: Verify no instantiation site changes needed**

Since `FrameTimestampTracker()` now takes no constructor arguments, all existing instantiation sites (`Camera2Recorder.kt`, tests) work without changes. Verify by compiling.

- [ ] **Step 3: Update FrameTimestampTrackerTest**

Update test (no constructor arg needed):

```kotlin
@Test
fun `write 2 frames and read back CSV`() {
    val tempFile = File.createTempFile("frame_timestamps", ".csv")
    tempFile.deleteOnExit()

    val tracker = FrameTimestampTracker()
    tracker.open(tempFile)

    tracker.onFrame(1_000_000_000L)
    tracker.onFrame(1_016_666_667L)

    // Give writer thread time to drain queue
    Thread.sleep(150)
    tracker.close()

    val lines = tempFile.readLines()
    assertTrue("CSV should have at least 3 lines (header + 2 data)", lines.size >= 3)
    assertEquals("frame_index,timestamp_ns", lines[0].trim())

    val frame0 = lines[1].trim().split(",")
    assertEquals(2, frame0.size)
    assertEquals("0", frame0[0])
    assertEquals("1000000000", frame0[1])

    val frame1 = lines[2].trim().split(",")
    assertEquals(2, frame1.size)
    assertEquals("1", frame1[0])
    assertEquals("1016666667", frame1[1])
}
```

- [ ] **Step 4: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/camera/FrameTimestampTracker.kt mobile/app/src/test/java/ru/skatelab/capture/data/camera/FrameTimestampTrackerTest.kt
git commit -m "refactor(camera): bounded LinkedBlockingQueue for frame timestamps, no DI change"
```

---

### Task 12 (moved to Phase 1): P8 — Replace Thread.sleep busy-wait with suspend callback + double-start guard

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt:156-182`

**Review fix R2-9:** `Camera2Recorder` no guard against double `startRecording()` — calling twice leaks old capture session + `FrameTimestampTracker`.

- [ ] **Step 1: Add double-start guard**

At the top of `Camera2Recorder.startRecording()`, add:

```kotlin
if (captureSession != null) {
    throw IllegalStateException("Already recording — stop first before starting again")
}
```

- [ ] **Step 2: Replace busy-wait with suspendCancellableCoroutine**

In `Camera2Recorder.startRecording()`, replace lines 156-182 (the `firstFrameCaptured` flag + while loop) with:

```kotlin
var firstFrameCont: kotlinx.coroutines.CancellableContinuation<Long>? = null

captureSession!!.setRepeatingRequest(builder.build(), object : CameraCaptureSession.CaptureCallback() {
    override fun onCaptureStarted(
        session: CameraCaptureSession,
        request: CaptureRequest,
        timestamp: Long,
        frameNumber: Long,
    ) {
        timestampTracker?.onFrame(timestamp)
        // Resume the suspended coroutine on first frame
        firstFrameCont?.let { cont ->
            firstFrameCont = null
            cont.resume(timestamp)
        }
    }
}, callbackHandler)

// Suspend until first frame or timeout
val tFirstFrameNs = try {
    kotlinx.coroutines.withTimeout(2_000L) {
        suspendCancellableCoroutine { cont ->
            firstFrameCont = cont
            cont.invokeOnCancellation {
                firstFrameCont = null
            }
        }
    }
} catch (_: kotlinx.coroutines.TimeoutCancellationException) {
    throw IllegalStateException("No first frame received within 2s")
}
```

Add import: `import kotlinx.coroutines.withTimeout`

- [ ] **Step 3: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 4: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt
git commit -m "refactor(camera): replace Thread.sleep busy-wait with suspendCancellableCoroutine, guard double start"
```

---

### Task 14 (moved to Phase 1): P11 — Add flush() method to ImuStreamWriter

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt`

**Review fix R2-1:** T14 must precede T11 — `ImuCollector` rewrite calls `writer.flush()` but `flush()` method doesn't exist until T14 adds it. Compilation error. Move T14 to Phase 1.

- [ ] **Step 1: Add flush() method to ImuStreamWriter**

In `ImuStreamWriter.kt`, add after `close()`:

```kotlin
/** Flush the buffer without closing. Periodic call reduces data loss on crash. */
@Synchronized
fun flush() {
    stream?.flush()
}
```

Note: `@Synchronized` is kept because `flush()` will be called from the periodic flush coroutine (`Dispatchers.IO`) while `write()` runs on per-sensor coroutines and `close()` on the calling thread. Defense-in-depth (I11).

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt
git commit -m "feat(imu): add flush() method to ImuStreamWriter for periodic flush"
```

---

### Phase 1 Verification

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
All tests must pass before proceeding to Phase 2.

---

## Phase 2: Sequential within file groups

Tasks 7-9 conflict on BleManager.kt (must be sequential). Task 7 conflicts with Phase 1's Task 1 (same file: RecordingViewModel.kt).

---

### Task 7: P3 — Add cleanup in RecordingViewModel.onCleared()

**Depends on:** Task 1 (P2 — same file: RecordingViewModel.kt)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt:308-323`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt`

**Review fix I5:** Use `context.applicationContext` instead of raw context to prevent Activity leak when ViewModel outlives Activity.

- [ ] **Step 1: Write failing test**

Add to `RecordingViewModelTest.kt`:

```kotlin
@Test
fun onCleared_stopsImuCollectorAndService() = testScope.runTest {
    coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
    coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
        Result.success(stubStartInfo)

    viewModel.prepareCamera(outputDir)
    runCurrent()

    viewModel.startRecording(outputDir, emptyMap(), context)
    runCurrent()

    viewModel.onCleared()

    verify { imuCollector.stop() }
    verify { context.startService(match { it.action == "ru.skatelab.capture.RECORDING_STOP" }) }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "RecordingViewModelTest.onCleared_stopsImuCollectorAndService"`
Expected: FAIL — onCleared doesn't call imuCollector.stop() or stopForegroundService()

- [ ] **Step 3: Fix onCleared() with applicationContext**

Add at class level in `RecordingViewModel.kt`:

```kotlin
private var appContext: android.content.Context? = null
```

In `startRecording()`, add at the top:

```kotlin
appContext = context.applicationContext // Use applicationContext to prevent Activity leak (I5)
```

In `stopRecording()`, add:

```kotlin
appContext = context.applicationContext
```

Replace `RecordingViewModel.kt:308-323` with:

```kotlin
override fun onCleared() {
    super.onCleared()
    periodicTimeSync.stop()
    // R2-19: runBlocking(IO) safe — stop() is synchronous, no Main dispatcher needed
    runBlocking(Dispatchers.IO) {
        // Stop IMU collector first (flush/fsync data)
        if (_isRecording.value) {
            imuCollector.stop()
        }
        // Clean up incomplete capture dir
        currentOutputDir?.let { dir ->
            val hasVideo = dir.listFiles()?.any { it.extension == "mp4" } ?: false
            if (!hasVideo && dir.exists()) {
                dir.deleteRecursively()
                appLogger.i(TAG, "Cleaned up incomplete capture dir on clear: ${dir.name}")
            }
        }
        cameraRepository.release()
    }
    // Stop foreground service after data is flushed
    appContext?.let { stopForegroundService(it) }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "RecordingViewModelTest.onCleared_stopsImuCollectorAndService"`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 6: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt
git commit -m "fix(recording): add IMU flush and service stop in onCleared, use applicationContext"
```

---

### Task 8: P5 — Fix HandlerThread leak on connect failure + try-catch around connectGatt

**Depends on:** Task 2 (P4 — same file: BleManager.kt)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt:148-171`

**Review fix R2-13 pattern:** Also add try-catch around `device.connectGatt()` defensively.

- [ ] **Step 1: Fix connect() failure path + wrap connectGatt in try-catch**

In `BleManager.connect()`, after line 164 (`val state = _connectionState.value[sensorId]`), in the `else` branch (connection failed), add cleanup:

Replace lines 165-171:

```kotlin
val state = _connectionState.value[sensorId]
return if (state == ConnectionState.CONNECTED) {
    logi("Sensor $sensorId connected and ready")
    Result.success(Unit)
} else {
    loge("Sensor $sensorId connection failed or timeout, state=$state")
    Result.failure(IllegalStateException("Connection failed for $sensorId, state=$state"))
}
```

with:

```kotlin
val state = _connectionState.value[sensorId]
return if (state == ConnectionState.CONNECTED) {
    logi("Sensor $sensorId connected and ready")
    Result.success(Unit)
} else {
    loge("Sensor $sensorId connection failed or timeout, state=$state")
    // Clean up leaked HandlerThread on failure
    handlerThreads.remove(address)?.quitSafely()
    addressToSensorId.remove(address)
    Result.failure(IllegalStateException("Connection failed for $sensorId, state=$state"))
}
```

Also wrap `device.connectGatt()` call in try-catch:

```kotlin
val gatt = try {
    device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
} catch (e: SecurityException) {
    loge("connectGatt failed for $address: ${e.message}")
    handlerThreads.remove(address)?.quitSafely()
    addressToSensorId.remove(address)
    return Result.failure(e)
}
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt
git commit -m "fix(ble): clean up HandlerThread on connect failure, catch SecurityException"
```

---

### Task 9: P10 — Increase SharedFlow buffer to 1024 + overflow logging

**Depends on:** Task 2 (P4 — same file: BleManager.kt) and Task 8 (P5 — same file)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt:74,290`

- [ ] **Step 1: Increase buffer capacity**

In `BleManager.kt:74`, change:

```kotlin
private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 256)
```

to:

```kotlin
private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 1024)
```

- [ ] **Step 2: Add overflow logging**

In `BleManager.kt:290`, change:

```kotlin
_imuSamples.tryEmit(id to sample)
```

to:

```kotlin
if (!_imuSamples.tryEmit(id to sample)) {
    logw("imuSamples buffer overflow — sample dropped for $id")
}
```

- [ ] **Step 3: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 4: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt
git commit -m "fix(ble): increase SharedFlow buffer to 1024 and log overflow"
```

---

### Phase 2 Verification

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
All tests must pass before proceeding to Phase 3.

---

## Phase 3: Depends on Phase 2

Task 11 depends on Task 9 (P10 buffer increase prerequisite). Task 11 also depends on Task 14 (P11 — flush() must exist).

---

### Task 11: P6 — Per-sensor IMU collectors with AtomicInteger, injectable ioDispatcher, full cleanup

**Depends on:** Task 9 (P10 — buffer already increased to 1024), Task 14 (P11 — flush() already added)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/recording/ImuCollector.kt`
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/di/AppModule.kt:44-45`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/data/recording/ImuCollectorTest.kt`

**Review fix I13:** After P6 refactor, `counts`, `lastSampleNs`, `pendingGaps`, `warmedUp` are `MutableMap` accessed from multiple Dispatchers.IO coroutines (LEFT, RIGHT, reconnect). Use `ConcurrentHashMap` for thread safety.
**Review fix I7:** `flushJob` not cancelled on re-start. Cancel all previous jobs at beginning of `start()`.
**Review fix R2-3:** `counts[id] = counts.getOrDefault(id, 0) + 1` is non-atomic on `ConcurrentHashMap` — read-modify-write race. Use `AtomicInteger` per sensor.
**Review fix R2-4:** `ImuCollectorTest` flaky after P6 — `Dispatchers.IO` not controlled by `TestScope`, `advanceUntilIdle()` won't advance real IO threads. Inject `ioDispatcher: CoroutineDispatcher = Dispatchers.IO` into `ImuCollector` for testability.
**Review fix R2-10:** `start()` only cancels `flushJob`, not `collectJobs`/`reconnectJob`/`streamingJob` from previous session — double-start creates duplicate writers.
**Review fix R2-11:** `stop()` doesn't clear `lastSampleNs` — stale values on re-start cause wrong gap computation.
**Review fix R2-12:** `collectJobs` uses `mutableMapOf` — `stop()` from `runBlocking(IO)` in `onCleared` races with `start()` on Main. Use `ConcurrentHashMap<SensorId, Job>()`.

- [ ] **Step 1: Remove ImuIo single-thread executor from AppModule**

In `AppModule.kt`, remove the `provideImuIoDispatcher()` method (lines 41-45):

```kotlin
@dagger.Provides
@Named("ImuIo")
@Singleton
fun provideImuIoDispatcher(): CoroutineDispatcher =
    Executors.newSingleThreadExecutor().asCoroutineDispatcher()
```

Also remove the now-unused import `kotlinx.coroutines.asCoroutineDispatcher` if it becomes unused.

- [ ] **Step 2: Rewrite ImuCollector with per-sensor coroutines + AtomicInteger + injectable ioDispatcher**

Replace `ImuCollector.kt`:

```kotlin
package ru.skatelab.capture.data.recording

import ru.skatelab.capture.AppLogger
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.export.ImuStreamWriter
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ImuCollector @Inject constructor(
    private val bleRepository: BleRepository,
    private val appLogger: AppLogger,
    // R2-4: injectable dispatcher for testability (TestDispatcher in tests)
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
) {
    companion object {
        private const val TAG = "ImuCollector"
        private const val WARMUP_MIN_ACC_MAGNITUDE = 1.0f
    }

    // ConcurrentHashMap for thread safety: accessed from per-sensor coroutines + reconnect + stop (I13)
    private val writers = ConcurrentHashMap<SensorId, ImuStreamWriter>()
    // R2-3: AtomicInteger per sensor for atomic increment
    private val counts = ConcurrentHashMap<SensorId, AtomicInteger>()
    private val lastSampleNs = ConcurrentHashMap<SensorId, Long>()
    private val pendingGaps = ConcurrentHashMap<SensorId, PendingGap>()
    private val warmedUp = ConcurrentHashMap<SensorId, Boolean>()
    private var reconnectSeq = 0
    // R2-12: ConcurrentHashMap instead of mutableMapOf for thread-safe stop/start race
    private val collectJobs = ConcurrentHashMap<SensorId, Job>()
    private var reconnectJob: Job? = null
    private var streamingJob: Job? = null
    private var flushJob: Job? = null

    private data class PendingGap(val lastSampleNs: Long, val seq: Int)

    fun start(scope: CoroutineScope, files: Map<SensorId, File>) {
        // R2-10: Cancel ALL previous jobs defensively — prevents double-start leak
        flushJob?.cancel(); flushJob = null
        collectJobs.values.forEach { it.cancel() }; collectJobs.clear()
        reconnectJob?.cancel(); reconnectJob = null
        streamingJob?.cancel(); streamingJob = null
        writers.clear(); counts.clear(); warmedUp.clear()
        lastSampleNs.clear() // R2-11: clear stale values on re-start
        pendingGaps.clear()

        files.forEach { (sensorId, file) ->
            file.parentFile?.mkdirs()
            val writer = ImuStreamWriter()
            writer.open(file)
            writers[sensorId] = writer
            counts[sensorId] = AtomicInteger(0)
            lastSampleNs[sensorId] = 0L
            warmedUp[sensorId] = false
            appLogger.i(TAG, "Started IMU writer for $sensorId → ${file.absolutePath}")

            // Per-sensor collector on injected dispatcher
            collectJobs[sensorId] = scope.launch(ioDispatcher) {
                bleRepository.imuSamples
                    .filter { (id, _) -> id == sensorId }
                    .collect { (id, sample) ->
                        if (warmedUp[id] != true) {
                            val accMag = kotlin.math.sqrt(
                                sample.accX * sample.accX +
                                    sample.accY * sample.accY +
                                    sample.accZ * sample.accZ
                            )
                            if (accMag < WARMUP_MIN_ACC_MAGNITUDE) return@collect
                            warmedUp[id] = true
                            appLogger.i(TAG, "Sensor $id warm-up complete, first real sample accMag=$accMag")
                        }

                        val writer = writers[id] ?: return@collect
                        try {
                            val gap: PendingGap? = pendingGaps.remove(id)
                            if (gap != null && gap.lastSampleNs > 0L) {
                                writer.writeGap(gap.lastSampleNs, sample.timestampNs, gap.seq)
                                appLogger.i(TAG, "IMUGap written for $id: lastNs=${gap.lastSampleNs} firstNs=${sample.timestampNs}")
                            }
                            writer.write(sample)
                            // R2-3: AtomicInteger atomic increment
                            counts[id]?.incrementAndGet()
                            lastSampleNs[id] = sample.timestampNs
                        } catch (e: Exception) {
                            appLogger.e(TAG, "Write error for $id: ${e.message}")
                        }
                    }
            }
        }

        // Periodic flush every 5s to reduce crash data loss
        flushJob = scope.launch(ioDispatcher) {
            while (true) {
                delay(5_000L)
                writers.values.forEach { writer ->
                    try {
                        writer.flush()
                    } catch (e: Exception) {
                        appLogger.e(TAG, "Periodic flush error: ${e.message}")
                    }
                }
            }
        }

        // Watch for BLE reconnect events
        reconnectJob = scope.launch(ioDispatcher) {
            bleRepository.reconnectEvents
                .filter { writers.containsKey(it) }
                .collect { sensorId ->
                    val lastNs = lastSampleNs[sensorId] ?: 0L
                    reconnectSeq++
                    pendingGaps[sensorId] = PendingGap(lastNs, reconnectSeq)
                    warmedUp[sensorId] = false
                    appLogger.w(TAG, "BLE reconnect gap #$reconnectSeq for $sensorId, lastNs=$lastNs")

                    streamingJob?.cancel()
                    streamingJob = scope.launch(ioDispatcher) {
                        try {
                            bleRepository.connectionState
                                .first { it[sensorId] == BleRepository.ConnectionState.CONNECTED }
                            bleRepository.startStreaming(sensorId).getOrElse {
                                appLogger.e(TAG, "Re-start streaming $sensorId failed: ${it.message}")
                            }
                            appLogger.i(TAG, "Streaming restarted for $sensorId after reconnect")
                        } catch (_: kotlinx.coroutines.CancellationException) {
                            // Cancelled — recording stopped
                        }
                    }
                }
        }
    }

    fun stop(): Map<SensorId, Int> {
        flushJob?.cancel(); flushJob = null
        collectJobs.values.forEach { it.cancel() }; collectJobs.clear()
        reconnectJob?.cancel(); reconnectJob = null
        streamingJob?.cancel(); streamingJob = null
        writers.forEach { (sensorId, writer) ->
            try {
                writer.close()
                val count = counts[sensorId]?.get() ?: 0
                appLogger.i(TAG, "Closed IMU writer for $sensorId, $count samples")
            } catch (e: Exception) {
                appLogger.e(TAG, "Close error for $sensorId: ${e.message}")
            }
        }
        writers.clear()
        pendingGaps.clear()
        warmedUp.clear()
        // R2-11: clear lastSampleNs so re-start computes gaps correctly
        lastSampleNs.clear()
        val result = counts.mapValues { it.value.get() }
        counts.clear()
        return result
    }

    private data class PendingGap(val lastSampleNs: Long, val seq: Int)
}
```

- [ ] **Step 3: Update ImuCollectorTest to inject TestDispatcher**

In `ImuCollectorTest.kt`, update constructor call:

```kotlin
@Before
fun setUp() {
    Dispatchers.setMain(testDispatcher)
    // R2-4: pass TestDispatcher as ioDispatcher so advanceUntilIdle works
    collector = ImuCollector(bleRepository, appLogger, testDispatcher)
}
```

- [ ] **Step 4: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/recording/ImuCollector.kt mobile/app/src/main/java/ru/skatelab/capture/di/AppModule.kt mobile/app/src/test/java/ru/skatelab/capture/data/recording/ImuCollectorTest.kt
git commit -m "refactor(imu): per-sensor collectors on injected dispatcher, AtomicInteger, ConcurrentHashMap, full cleanup"
```

---

### Phase 3 Verification

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
All tests must pass before proceeding to Phase 4.

---

## Phase 4: Depends on Phase 3

Task 13 depends on Task 12 (same file: Camera2Recorder). Task 15 depends on Task 14 (same file: ImuStreamWriter).

---

### Task 13: P9 — Handle UNKNOWN timestamp source fallback

**Depends on:** Task 12 (P8 — same file: Camera2Recorder.kt)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt`

- [ ] **Step 1: Override timestamp for UNKNOWN source**

In `Camera2Recorder.startRecording()`, inside the `onCaptureStarted` callback (modified in Task 12), add fallback:

```kotlin
override fun onCaptureStarted(
    session: CameraCaptureSession,
    request: CaptureRequest,
    timestamp: Long,
    frameNumber: Long,
) {
    // For UNKNOWN timestamp sources, use system clock at callback time
    // instead of sensor timestamp (which may be in wrong timebase)
    val effectiveTimestamp = if (getTimestampSource() == "UNKNOWN") {
        android.os.SystemClock.elapsedRealtimeNanos()
    } else {
        timestamp
    }
    timestampTracker?.onFrame(effectiveTimestamp)
    firstFrameCont?.let { cont ->
        firstFrameCont = null
        cont.resume(effectiveTimestamp)
    }
}
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt
git commit -m "fix(camera): fallback to system clock for UNKNOWN timestamp source"
```

---

### Task 15: P16 — Keep @Synchronized on ImuStreamWriter + document why

**Depends on:** Task 14 (P11 — same file: ImuStreamWriter.kt, flush() already added)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt`

**Review fix I11:** Do NOT remove `@Synchronized`. After P6 (per-sensor collectors) + P11 (periodic flush), `flush()` and `close()` can race with `write()`. The overhead is negligible for I/O-bound operations. Defense-in-depth.

- [ ] **Step 1: Ensure @Synchronized is present on all methods**

In `ImuStreamWriter.kt`, verify `@Synchronized` is on:
- `write()` — yes
- `writeGap()` — yes
- `close()` — yes
- `flush()` — added in Task 14 with `@Synchronized`

If any are missing, add `@Synchronized` annotation.

Add a comment documenting why:

```kotlin
/**
 * Writes delimited protobuf IMURecord messages (IMUSample or IMUGap) to a .binpb file.
 * Uses a 16KB BufferedOutputStream for efficient I/O.
 *
 * @Synchronized is kept on all methods because flush() runs on a periodic coroutine
 * (Dispatchers.IO) while write() runs on per-sensor coroutines and close() on the
 * calling thread. The overhead is negligible for I/O-bound operations.
 */
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt
git commit -m "docs(imu): document why @Synchronized is kept on ImuStreamWriter"
```

---

### Phase 4 Verification

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
All tests must pass before proceeding to Phase 5.

---

## Phase 5: Depends on Phase 2 (BleManager.kt free)

Tasks 16-18 + new tasks T19-T21. Sequential within BleManager.kt where needed.

---

### Task 16: P14 — GATT write queue + disconnect cleanup

**Depends on:** Task 9 (P10 — same file: BleManager.kt, all Phase 1+2 BleManager changes committed)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt:349-361`

**Review fix I1 (Critical):** Remove `postDelayed` retry on `writeCharacteristic` failure. When `writeCharacteristic` returns `false`, GATT is busy or disconnected. Retrying blindly causes infinite loop if disconnected. Let `onCharacteristicWrite` (which Android calls even on failure with `status != 0`) drive the next write.
**Review fix R2-2:** `writeQueue`/`writeInProgress` not cleaned on disconnect — stale entries processed against new GATT after reconnect, causing duplicate commands.

- [ ] **Step 1: Add write queue infrastructure + thread-safe recordingSensors (T19)**

Add fields to `BleManager.kt` after `repriorityTimers`:

```kotlin
// GATT write queue: serialize write operations per sensor
private val writeQueue = ConcurrentHashMap<String, MutableList<ByteArray>>()
private val writeInProgress = ConcurrentHashMap<String, Boolean>()
// R2-6: thread-safe set for recordingSensors — accessed from Binder thread + Main
private val recordingSensors = ConcurrentHashMap.newKeySet<SensorId>()
```

Also change `recordingSensors` declaration from `mutableSetOf()` to the `ConcurrentHashMap.newKeySet()` above (remove old declaration).

- [ ] **Step 2: Replace sendCommand with queued version (NO retry on failure)**

Replace `sendCommand()` (lines 348-362):

```kotlin
@SuppressLint("MissingPermission")
fun sendCommand(sensorId: SensorId, bytes: ByteArray) {
    val address = addressToSensorId.entries.find { it.value == sensorId }?.key ?: run {
        logw("sendCommand: no address for $sensorId"); return
    }
    val gatt = gattConnections[address] ?: run {
        logw("sendCommand: no GATT for $address"); return
    }
    val char = writeCharacteristics[address] ?: run {
        logw("sendCommand: no write char for $address"); return
    }

    synchronized(this) {
        val queue = writeQueue.getOrPut(address) { mutableListOf() }
        queue.add(bytes)
        if (writeInProgress[address] == true) {
            logi("sendCommand: queued for $sensorId (write in progress), queue=${queue.size}")
            return
        }
        writeInProgress[address] = true
    }
    writeNext(gatt, char, address, sensorId)
}

@SuppressLint("MissingPermission")
private fun writeNext(gatt: BluetoothGatt, char: BluetoothGattCharacteristic, address: String, sensorId: SensorId) {
    val bytes: ByteArray
    synchronized(this) {
        val queue = writeQueue[address] ?: return
        if (queue.isEmpty()) {
            writeInProgress[address] = false
            return
        }
        bytes = queue.removeAt(0)
    }
    char.value = bytes
    val success = gatt.writeCharacteristic(char)
    logi("writeCharacteristic $sensorId: ${bytes.joinToString("") { "%02x".format(it) }} success=$success")
    // I1: Do NOT retry on failure. onCharacteristicWrite will be called by Android
    // even on failure (status != 0), and it will drive the next write.
    // Retrying blindly causes infinite loops if GATT is disconnected.
    if (!success) {
        logw("writeCharacteristic returned false for $sensorId — waiting for onCharacteristicWrite")
    }
}
```

- [ ] **Step 3: Add onCharacteristicWrite callback in GATT callback**

In `createGattCallback()`, add override:

```kotlin
override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
    logi("onCharacteristicWrite: address=$address status=$status")
    if (status != 0) {
        logw("onCharacteristicWrite failed with status=$status for $address")
    }
    // Process next queued write regardless of status
    val gattConn = gattConnections[address] ?: return
    val writeChar = writeCharacteristics[address] ?: return
    val sId = addressToSensorId[address] ?: return
    handlerThreads[address]?.handler?.post {
        writeNext(gattConn, writeChar, address, sId)
    }
}
```

- [ ] **Step 4: Clean writeQueue/writeInProgress on disconnect (R2-2)**

In `disconnect()` and `onConnectionStateChange(STATE_DISCONNECTED)`, add cleanup:

In `disconnect(sensorId)`:
```kotlin
val address = addressToSensorId.entries.find { it.value == sensorId }?.key
if (address != null) {
    writeQueue.remove(address)
    writeInProgress[address] = false
}
gattConnections[address]?.disconnect()
```

In `createGattCallback()` inside `onConnectionStateChange` when `newState == BluetoothProfile.STATE_DISCONNECTED`:
```kotlin
// R2-2: clean write queue on disconnect to prevent stale commands on reconnect
writeQueue.remove(address)
writeInProgress[address] = false
```

- [ ] **Step 5: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 6: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt
git commit -m "feat(ble): add GATT write queue, no retry on failure, clean queue on disconnect"
```

---

### Task 17: P18 — Make SessionState thread-safe

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/SessionState.kt`
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModel.kt:101`
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt`
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt`
- Test: `mobile/app/src/test/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModelTest.kt`

**Review fix I9:** `SessionState.calibration` is a `var` accessed from Main (CalibrationViewModel writes) and potentially from IO (after P7 wraps session save in Dispatchers.IO). Convert to `MutableStateFlow` for thread safety.

- [ ] **Step 1: Convert SessionState to use MutableStateFlow**

Replace `SessionState.kt`:

```kotlin
package ru.skatelab.capture.presentation

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId

object SessionState {
    private val _calibration = MutableStateFlow<Map<SensorId, CalibrationData>>(emptyMap())
    val calibration: StateFlow<Map<SensorId, CalibrationData>> = _calibration.asStateFlow()

    fun setCalibration(value: Map<SensorId, CalibrationData>) {
        _calibration.value = value
    }

    fun getCalibration(): Map<SensorId, CalibrationData> = _calibration.value
}
```

- [ ] **Step 2: Update CalibrationViewModel**

In `CalibrationViewModel.kt:101`, change:

```kotlin
SessionState.calibration = calMap
```

to:

```kotlin
SessionState.setCalibration(calMap)
```

- [ ] **Step 3: Update RecordingScreen**

In `RecordingScreen.kt`, wherever `SessionState.calibration` is read, change to collect from StateFlow or use `SessionState.getCalibration()`:

If it's inside a Composable, use:
```kotlin
val calibration by SessionState.calibration.collectAsState()
```

If it's a one-shot read:
```kotlin
val cal = SessionState.getCalibration()
```

- [ ] **Step 4: Update AppNavigation**

Same pattern as Step 3 — replace `SessionState.calibration` reads with `SessionState.getCalibration()` or `collectAsState()`.

- [ ] **Step 5: Update tests**

In `CalibrationViewModelTest.kt`, wherever `SessionState.calibration` is asserted, change:

```kotlin
assertEquals(expected, SessionState.calibration)
```

to:

```kotlin
assertEquals(expected, SessionState.getCalibration())
```

Or reset state in `@After`:
```kotlin
@After
fun tearDown() {
    SessionState.setCalibration(emptyMap())
}
```

- [ ] **Step 6: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 7: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/SessionState.kt mobile/app/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModel.kt mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt mobile/app/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt mobile/app/src/test/java/ru/skatelab/capture/presentation/calibration/CalibrationViewModelTest.kt
git commit -m "fix(state): make SessionState thread-safe with MutableStateFlow"
```

---

### Task 18: P19 — Move AppNavigation mkdirs to LaunchedEffect with remember

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt:65`

**Review fix I12:** `mkdirs()` is a side effect in a Composable function, violating Compose side-effect rules. Move to `LaunchedEffect`.
**Review fix R2-15:** `LaunchedEffect(outputDir)` restarts on every recomposition — `System.currentTimeMillis()` creates new File instance each time. Use `remember { File(...) }` + `LaunchedEffect(Unit) { outputDir.mkdirs() }`.

- [ ] **Step 1: Move mkdirs to LaunchedEffect with remember**

In `AppNavigation.kt`, find the `mkdirs()` call (around line 65) and change:

```kotlin
// Before (anti-pattern: side effect in composable body)
val outputDir = File(context.filesDir, "sessions/${System.currentTimeMillis()}")
outputDir.mkdirs()
```

to:

```kotlin
// After: remember prevents recomposition recreation, LaunchedEffect(Unit) runs once
val outputDir = remember {
    File(context.filesDir, "sessions/${System.currentTimeMillis()}")
}
LaunchedEffect(Unit) {
    outputDir.mkdirs()
}
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt
git commit -m "fix(nav): move mkdirs side effect to LaunchedEffect with remember"
```

---

### Task 19 (new): Thread-safe recordingSensors with ConcurrentHashMap.newKeySet

**Depends on:** Task 16 (P14 — same file: BleManager.kt)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt`

**Review fix R2-6:** `recordingSensors` (`mutableSetOf`) not thread-safe — accessed from Binder thread (`isRecording` in `onConnectionStateChange`) + Main (`markRecording`/`markStopped`). Already included in Task 16 Step 1 as field replacement. This task ensures all reads/writes use the ConcurrentHashMap set.

- [ ] **Step 1: Verify all recordingSensors accesses use the new set**

Search `BleManager.kt` for `recordingSensors` usages. Ensure:
- `markRecording(sensorId)` does `recordingSensors.add(sensorId)`
- `markStopped(sensorId)` does `recordingSensors.remove(sensorId)`
- `isRecording(sensorId)` does `recordingSensors.contains(sensorId)`
- `isAnyRecording()` does `recordingSensors.isNotEmpty()`

All these operations are thread-safe on `ConcurrentHashMap.newKeySet()`.

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

Task 16 already committed this change. No separate commit needed if verified in Task 16.

---

### Task 20 (new): Atomic _connectionState updates

**Depends on:** Task 16 (P14 — same file: BleManager.kt)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt`

**Review fix R2-18:** `updateConnectionState` not atomic across sensors — two GATT callbacks from different sensors can lose one update.

- [ ] **Step 1: Use MutableStateFlow.update for atomic state changes**

In `BleManager.kt`, find `updateConnectionState()` and change:

```kotlin
// Before (read-modify-write race on mutable map)
_connectionState.value = _connectionState.value.toMutableMap().apply {
    put(sensorId, state)
}
```

to:

```kotlin
// After (atomic update via StateFlow)
_connectionState.update { current -> current + (sensorId to state) }
```

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt
git commit -m "fix(ble): atomic _connectionState updates via MutableStateFlow.update"
```

---

### Task 21 (new): Clean writeQueue/writeInProgress on disconnect and STATE_DISCONNECTED

**Depends on:** Task 16 (P14 — same file: BleManager.kt)

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt`

**Review fix R2-2:** `writeQueue`/`writeInProgress` not cleaned on disconnect — stale entries processed against new GATT after reconnect, causing duplicate commands. Already included in Task 16 Step 4. This task verifies completeness.

- [ ] **Step 1: Verify cleanup in all disconnect paths**

Check three locations:
1. `disconnect(sensorId)` — `writeQueue.remove(address)` + `writeInProgress[address] = false` (Task 16 Step 4)
2. `onConnectionStateChange(STATE_DISCONNECTED)` — same cleanup (Task 16 Step 4)
3. `connect()` failure path — `addressToSensorId.remove(address)` but NOT writeQueue (queue is empty at this point since no commands sent yet, so safe)

- [ ] **Step 2: Run full test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
Expected: All tests green

- [ ] **Step 3: Commit**

Already committed in Task 16. No separate commit needed.

---

### Phase 5 Verification

Run: `cd mobile && ./gradlew :app:testDebugUnitTest`
All tests must pass.

---

## Dependency Graph

```
Phase 1 (parallel, no conflicts):
  T1(P2), T2(P4), T3(P7), T4(P12), T5(P13), T6(P17),
  T10(P15)*, T12(P8), T14(P11)
  → 9 tasks concurrently
  → Files: RecordingVM, BleManager, SessionRepo+ExportVM, BleRepoImpl, CalibVM, CalibUC,
           FrameTimestampTracker, Camera2Recorder, ImuStreamWriter

Phase 2 (sequential within file groups):
  T7(P3) — after T1 (same file: RecordingVM)
  T8(P5) — after T2 (same file: BleManager)
  T9(P10) — after T8 (same file: BleManager)

Phase 3 (depends on Phase 2):
  T11(P6) — after T9 + T14 (buffer increased, flush() exists)

Phase 4 (depends on Phase 3):
  T13(P9) — after T12 (same file: Camera2Recorder)
  T15(P16) — after T14 (same file: ImuStreamWriter)

Phase 5 (sequential, BleManager free):
  T16(P14) — after T9 (same file: BleManager)
  T17(P18) — independent
  T18(P19) — after T17 (same file: AppNavigation.kt)
  T19 — included in T16 (recordingSensors thread-safety)
  T20 — after T16 (same file: BleManager)
  T21 — included in T16 (writeQueue cleanup)
```

**Critical path:** T2→T8→T9→T11→T14→T15 (4 sequential hops after Phase 1, down from 6)

*T10 uses simpler LinkedBlockingQueue approach per R2-8, removing CoroutineScope injection requirement.*

---

## Review Findings Applied (Round 1)

| # | Issue | Severity | Plan Change |
|---|-------|----------|-------------|
| I1 | GATT write queue retry loop | Critical | Task 16: remove `postDelayed` retry on `writeCharacteristic` failure |
| I2 | stopScan/startScan race | Medium | Task 2: set `activeScanCallback` BEFORE `startScan()` |
| I4 | @Named("ImuIo") unused import | Critical | Task 11 Step 1: remove `asCoroutineDispatcher` import |
| I5 | onCleared stores Activity Context | High | Task 7: use `context.applicationContext` |
| I7 | flushJob not cancelled on re-start | Medium | Task 11: cancel all jobs at beginning of `start()` |
| I8 | Export use case still on Main | High | Task 3: wrap entire export body in `withContext(IO)` |
| I9 | SessionState thread safety missing | High | Task 17: add P18 — `MutableStateFlow` |
| I10 | FrameTimestampTracker scope leak | Medium | Task 10: use `LinkedBlockingQueue` instead of coroutine scope |
| I11 | @Synchronized removal unsafe | Medium | Task 15: DON'T remove — keep for defense-in-depth |
| I12 | AppNavigation mkdirs | Low | Task 18: add P19 — move to `LaunchedEffect` with `remember` |
| I13 | ImuCollector mutable state race | High | Task 11: use `ConcurrentHashMap` + `AtomicInteger` |

## Review Findings Applied (Round 2)

| # | Finding | Severity | Plan Change |
|---|---------|----------|-------------|
| R2-1 | T14 must precede T11 — compilation error | Critical | **Move T14 to Phase 1** |
| R2-2 | writeQueue not cleaned on disconnect | Critical | Task 16 Step 4: clean on `disconnect()` + `STATE_DISCONNECTED` |
| R2-3 | `counts[id] = getOrDefault+1` non-atomic | High | Task 11: use `AtomicInteger` per sensor |
| R2-4 | `ImuCollectorTest` flaky — real IO threads | High | Task 11: inject `ioDispatcher` param, test passes `TestDispatcher` |
| R2-5 | `imuCollector.stop()` exception kills stopRecording | High | Task 1: wrap in `try/catch` |
| R2-6 | `recordingSensors` (mutableSetOf) not thread-safe | High | Task 16 Step 1 + T19: `ConcurrentHashMap.newKeySet()` |
| R2-7 | `_isExporting` stuck on cancellation | High | Task 3: `try/finally { _isExporting.value = false }` |
| R2-8 | `FrameTimestampTracker` scope injection incomplete | High | Task 10: `LinkedBlockingQueue(1000)` instead of `Channel` + `CoroutineScope` |
| R2-9 | `Camera2Recorder` double startRecording leak | High | Task 12: guard `if (captureSession != null) throw` |
| R2-10 | `start()` only cancels `flushJob`, not all jobs | Medium | Task 11: cancel `collectJobs`/`reconnectJob`/`streamingJob` + clear |
| R2-11 | `stop()` doesn't clear `lastSampleNs` | Medium | Task 11: `lastSampleNs.clear()` in `stop()` |
| R2-12 | `collectJobs` uses `mutableMapOf` — race with stop/start | Medium | Task 11: `ConcurrentHashMap<SensorId, Job>()` |
| R2-13 | `activeScanCallback` not cleaned if `startScan()` throws | Medium | Task 2: try-catch around `scanner.startScan()`, null out on exception |
| R2-14 | `activeScanCallback` not `@Volatile` | Medium | Task 2: add `@Volatile` annotation |
| R2-15 | `LaunchedEffect(outputDir)` restarts on recomposition | Medium | Task 18: `remember { File(...) }` + `LaunchedEffect(Unit)` |
| R2-16 | `runCatching` swallows `CancellationException` | Medium | Task 3: re-throw `CancellationException` in `deleteSession` |
| R2-17 | Critical path in header wrong | Medium | Fixed to T2→T8→T9→T11→T14→T15 |
| R2-18 | `updateConnectionState` not atomic across sensors | Low | Task 20: `_connectionState.update { current + (sensorId to state) }` |
| R2-19 | `runBlocking(IO)` in `onCleared` safe | Low | Task 7: comment documenting assumption |
| R2-20 | `ExportViewModelTest` constructor mismatch | Low | Task 3 Step 3: fix test to match constructor |
| R2-21 | StateFlow values set from IO thread cosmetic delay | Low | Documented as intentional; no fix needed |

---

## Verification Checklist

After all phases complete:

1. `cd mobile && ./gradlew :app:testDebugUnitTest` — all unit tests green
2. Install APK on device, verify calibration works (both sensors show "Откалиброван")
3. Record a 30s session, verify IMU data in both `.binpb` files
4. Verify no ANR during export
5. `adb logcat | grep "imuSamples buffer overflow"` — no overflow warnings
6. `adb logcat | grep "BLE scan"` — verify stopScan actually stops scanning
7. Verify foreground service notification persists during IMU flush on stop
8. Disconnect sensor mid-recording, reconnect — verify no duplicate commands in GATT write queue
9. Run `ImuCollectorTest` 10x in a row — verify no flakiness (`./gradlew :app:testDebugUnitTest --tests "ImuCollectorTest"` × 10)
