# Parallelism & Async Optimization Design

## Context

5-agent deep audit identified ~30 parallelism/async issues across the recording pipeline. This design addresses the critical ones that cause data loss, UI freezes, or significant latency.

## Priority Classification

| Priority | Meaning |
|----------|---------|
| **P0** | Data loss or corruption risk |
| **P1** | UI freeze / ANR risk |
| **P2** | Latency / throughput improvement |

---

## P0: Critical Bugs (Data Loss)

### 1. Global `isRecording` flag breaks per-sensor reconnect

**File:** `BleManager.kt:84`

```kotlin
@Volatile
var isRecording = false
```

**Problem:** When sensor A disconnects during recording, `onConnectionStateChange` checks `isRecording`. If recording stops before reconnect completes, the flag is `false` → reconnect never attempts → data loss for sensor A.

**Fix:** Per-sensor recording state in `BleRepositoryImpl`.

```kotlin
// BleRepositoryImpl
private val recordingSensors = mutableSetOf<SensorId>()

fun markRecording(sensorId: SensorId) { recordingSensors.add(sensorId) }
fun markStopped(sensorId: SensorId) { recordingSensors.remove(sensorId) }
fun isRecording(sensorId: SensorId): Boolean = sensorId in recordingSensors
```

BleManager reconnect check uses `bleRepository.isRecording(sensorId)` instead of global flag.

### 2. `sendSequence` blocks parsing thread (750ms blackout)

**File:** `BleManager.kt:362-378`

```kotlin
fun sendSequence(sensorId: SensorId, steps: List<Wt901Commander.CommandStep>) {
    handlerThread.handler?.post {
        Thread.sleep(100L)  // blocks parser for 100ms
        for (step in steps) {
            sendCommand(sensorId, step.bytes)
            if (step.delayAfterMs > 0) Thread.sleep(step.delayAfterMs)  // 650ms total
        }
    }
}
```

**Problem:** `Thread.sleep` on the shared handler thread blocks ALL parsing for 750ms. During that window, IMU samples queue up → potential BLE buffer overflow → dropped packets.

**Fix:** Convert to suspend function with `delay()`.

```kotlin
suspend fun sendSequence(sensorId: SensorId, steps: List<Wt901Commander.CommandStep>) {
    delay(100L)
    for (step in steps) {
        sendCommand(sensorId, step.bytes)
        if (step.delayAfterMs > 0) delay(step.delayAfterMs)
    }
}
```

Runs on coroutine dispatcher, not handler thread. Parsing continues uninterrupted.

### 3. `removeParser` race — concurrent MutableMap access

**File:** `BleHandlerThread.kt:87`

```kotlin
fun removeParser(sensorAddress: String) {
    parsers.remove(sensorAddress)  // called from disconnect on IO thread
}
```

**Problem:** `parsers` is `mutableMapOf` accessed from both handler thread (via `getOrCreateParser`) and IO thread (via `removeParser`). No synchronization → `ConcurrentModificationException` risk.

**Fix:** Use `ConcurrentHashMap`.

```kotlin
private val parsers = ConcurrentHashMap<String, Wt901Parser>()
```

---

## P1: UI Freeze / ANR Risk

### 4. `fd.sync()` blocks UI thread

**File:** `ImuStreamWriter.close()` called from `ImuCollector.stop()` called from `RecordingViewModel.stopRecording()` on `viewModelScope`.

**Problem:** `fd.sync()` is a blocking kernel call (~5-50ms). On `Dispatchers.Main` this freezes the UI.

**Fix:** `ImuCollector.stop()` should be called on `Dispatchers.IO`.

```kotlin
// RecordingViewModel.stopRecording()
val imuCounts = withContext(Dispatchers.IO) { imuCollector.stop() }
```

Already partially correct — `stopRecording` runs in `viewModelScope.launch` which defaults to Main. Wrap the `imuCollector.stop()` call.

### 5. `onCleared()` blocking I/O

**File:** `RecordingViewModel.kt:306-322`

```kotlin
override fun onCleared() {
    currentOutputDir?.let { dir ->
        val hasVideo = dir.listFiles()?.any { it.extension == "mp4" } ?: false
        if (!hasVideo && dir.exists()) dir.deleteRecursively()  // blocking I/O on main
    }
    viewModelScope.launch { cameraRepository.release() }  // may not complete
}
```

**Fix:** Launch on `Dispatchers.IO`, use `runBlocking` for cleanup since `onCleared` is the last call.

```kotlin
override fun onCleared() {
    runBlocking(Dispatchers.IO) {
        currentOutputDir?.let { dir ->
            val hasVideo = dir.listFiles()?.any { it.extension == "mp4" } ?: false
            if (!hasVideo && dir.exists()) dir.deleteRecursively()
        }
        cameraRepository.release()
    }
}
```

### 6. `SessionRepositoryImpl.saveSession()` blocking I/O

**File:** `SessionRepositoryImpl.kt:30-35`

```kotlin
override suspend fun saveSession(session: CaptureSession): Result<Unit> = runCatching {
    val dir = File(sessionsDir, session.id)
    dir.mkdirs()
    metaFile.writeText(sessionToJson(session))
}
```

**Problem:** Already `suspend` but uses `runCatching` with default dispatcher. Should explicitly use `Dispatchers.IO` since file I/O is blocking.

**Fix:** Wrap in `withContext(Dispatchers.IO)`.

```kotlin
override suspend fun saveSession(session: CaptureSession): Result<Unit> = runCatching {
    withContext(Dispatchers.IO) {
        val dir = File(sessionsDir, session.id)
        dir.mkdirs()
        val metaFile = File(dir, META_FILE)
        metaFile.writeText(sessionToJson(session))
    }
}
```

### 7. `StopRecordingUseCase` — resource leak on partial failure

**File:** `StopRecordingUseCase.kt:14-27`

```kotlin
suspend operator fun invoke(): Result<Unit> = runCatching {
    withContext(Dispatchers.Main) { cameraRepository.stopRecording().getOrThrow() }
    withContext(Dispatchers.IO) { ... stop streaming ... }
    withContext(Dispatchers.Main) { cameraRepository.release() }
}
```

**Problem:** Single `runCatching` wrapper. If `stopRecording()` fails, BLE streaming never stops and camera never releases. If `stopStreaming` fails, `release()` never called.

**Fix:** Sequential cleanup with per-step error handling.

```kotlin
suspend operator fun invoke(): Result<Unit> {
    val errors = mutableListOf<Throwable>()

    // Always attempt all cleanup steps
    try {
        withContext(Dispatchers.Main) { cameraRepository.stopRecording().getOrDefault(Unit) }
    } catch (e: Exception) { errors.add(e) }

    try {
        withContext(Dispatchers.IO) {
            bleRepository.stopStreaming(SensorId.LEFT).getOrDefault(Unit)
            bleRepository.stopStreaming(SensorId.RIGHT).getOrDefault(Unit)
        }
    } catch (e: Exception) { errors.add(e) }

    try {
        withContext(Dispatchers.Main) { cameraRepository.release() }
    } catch (e: Exception) { errors.add(e) }

    return if (errors.isEmpty()) Result.success(Unit) else Result.failure(errors.first())
}
```

---

## P2: Throughput Improvements

### 8. Per-sensor `BleHandlerThread` for head-of-line blocking elimination

**Current:** Single `BleHandlerThread` parses both sensors sequentially. If LEFT sensor sends large packet, RIGHT sensor parsing is delayed.

**Fix:** Two handler threads, one per sensor.

```kotlin
class BleManager(...) {
    private val leftHandlerThread = BleHandlerThread("ble-parse-left")
    private val rightHandlerThread = BleHandlerThread("ble-parse-right")
```

`postParsing` routes to the correct handler thread based on `SensorId`.

### 9. Increase `MutableSharedFlow` buffer for IMU samples

**File:** `BleManager.kt:73`

```kotlin
private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 64)
```

**Problem:** At 100Hz × 2 sensors = 200 samples/sec. Buffer of 64 ≈ 320ms before overflow. Under GC pressure, this can fill.

**Fix:** Increase to 256 (≈1.3s buffer).

```kotlin
private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 256)
```

### 10. Camera2: Remove `ImageReader`, use `onCaptureStarted()` timestamps

**File:** `Camera2Recorder.kt:99-105`

```kotlin
imageReader = ImageReader.newInstance(width, height, YUV_420_888, 2)
imageReader?.setOnImageAvailableListener({ reader ->
    val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
    timestampTracker?.onFrame(image.timestamp)
    image.close()
}, callbackHandler)
```

**Problem:** `ImageReader` allocates YUV_420_888 buffers (1920×1080 × ~1.5 = ~3MB each, 2 buffers = 6MB GPU memory). Only `image.timestamp` is used — the pixel data is discarded.

**Fix:** Use `onCaptureStarted()` in `CaptureCallback` for timestamps. No `ImageReader` needed.

```kotlin
// In startRecording(), remove ImageReader from surfaces and listener setup
// Add timestamp capture in the existing CaptureCallback:
override fun onCaptureStarted(session, request, timestamp, frameNumber) {
    timestampTracker?.onFrame(timestamp)
    // ... existing first-frame logic
}
```

Removes 6MB GPU memory allocation and an unnecessary image-acquire/close cycle per frame.

### 11. Batch-flush `FrameTimestampTracker`

**Current:** Each frame calls `executor.submit { write }` + `flush()`. At 60fps, 60 executor submissions + 60 flushes per second.

**Fix:** Batch flush every N frames or time interval.

```kotlin
private var framesSinceFlush = 0

fun onFrame(timestampNs: Long) {
    // ... frame count logic ...
    val w = writer ?: return
    executor.submit {
        w.write("$index,$timestampNs\n")
        framesSinceFlush++
        if (framesSinceFlush >= 30) {  // flush every 30 frames = ~0.5s
            w.flush()
            framesSinceFlush = 0
        }
    }
}
```

### 12. Parallelize BLE start/stop operations

**File:** `StartRecordingUseCase.kt:32-35`

```kotlin
val leftResult = bleRepository.startStreaming(SensorId.LEFT)
val rightResult = bleRepository.startStreaming(SensorId.RIGHT)
```

**Fix:** Use `async/awaitAll` for independent BLE ops.

```kotlin
val (leftResult, rightResult) = awaitAll(
    async { bleRepository.startStreaming(SensorId.LEFT) },
    async { bleRepository.startStreaming(SensorId.RIGHT) },
)
```

Same for `stopStreaming` in `StopRecordingUseCase`.

### 13. Export ZIP: `STORED` compression for already-compressed files

**File:** `ZipExporter.kt`

MP4 (H.264) and protobuf `.binpb` are already compressed. `DEFLATE` wastes CPU for no size benefit.

**Fix:** Use `STORED` method for `.mp4` and `.binpb` entries.

```kotlin
private fun addToZip(zos: ZipOutputStream, file: File) {
    val method = if (file.extension in listOf("mp4", "binpb")) ZipEntry.STORED else ZipEntry.DEFLATED
    val entry = ZipEntry(file.name)
    if (method == ZipEntry.STORED) {
        entry.method = ZipEntry.STORED
        entry.size = file.length()
        entry.compressedSize = file.length()
        entry.crc32 = file.crc32()
    }
    // ...
}
```

### 14. Dedicated `@Named("ImuIo")` single-thread dispatcher for IMU collection

**Current:** `ImuCollector` uses `Dispatchers.IO` — shared with other I/O operations (session save, file cleanup, BLE writes). Under load, `Dispatchers.IO` thread pool can saturate.

**Fix:** Single-thread dispatcher guarantees ordering and avoids contention.

```kotlin
@Named("ImuIo")
@Singleton
class ImuCollector @Inject constructor(
    private val bleRepository: BleRepository,
    private val appLogger: AppLogger,
    @Named("ImuIo") private val ioDispatcher: CoroutineDispatcher,
)
```

Module provides:

```kotlin
@Named("ImuIo")
@Provides
fun provideImuIoDispatcher(): CoroutineDispatcher = Executors.newSingleThreadExecutor().asCoroutineDispatcher()
```

---

## What We're NOT Doing

| Rejected Idea | Why |
|---|---|
| `ConcurrentHashMap` for `addressToSensorId` | Read-heavy, write-once. Current `ConcurrentHashMap` is fine. |
| Separate coroutine per sensor in ImuCollector | `SharedFlow.collect` on single thread is already correct — ordering preserved. Separate coroutines add complexity for no gain. |
| Compress IMU protobuf on-the-fly | Premature. Current `writeDelimitedTo` is already efficient. |
| Camera2 `onCaptureCompleted` instead of `onCaptureStarted` | `onCaptureStarted` gives earlier timestamp. `onCaptureCompleted` has shutter lag. |

## Dependency Order

Changes must be applied in this order:

1. **P0-1** (global `isRecording` → per-sensor state) — blocks reconnect reliability
2. **P0-2** (`sendSequence` suspend) — blocks streaming start reliability
3. **P0-3** (`ConcurrentHashMap` for parsers) — prevents rare crash
4. **P1-4** (`fd.sync` on IO) — quick fix, unblocks P1-5
5. **P1-5** (`onCleared` IO) — depends on P1-4 pattern
6. **P1-6** (`saveSession` IO) — independent
7. **P1-7** (stop recording cleanup) — independent
8. **P2-8** (per-sensor handler threads) — depends on P0-2 (suspend `sendSequence`)
9. **P2-9** (SharedFlow buffer increase) — independent
10. **P2-10** (remove ImageReader) — independent
11. **P2-11** (batch flush timestamps) — depends on P2-10
12. **P2-12** (parallel BLE start/stop) — depends on P0-2
13. **P2-13** (ZIP STORED for mp4/binpb) — independent
14. **P2-14** (ImuIo dispatcher) — independent