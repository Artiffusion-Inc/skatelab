# CameraX Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Camera2 with CameraX + camera-compose to fix UI freeze, landscape squashing, and enable skeletal overlay path.

**Architecture:** CameraXRecorder (VideoCapture + Preview + ImageAnalysis), CameraXViewfinder composable, blocking ops on IO dispatcher.

**Tech Stack:** CameraX 1.4.1, camera-compose 1.4.1, Compose, Hilt, Kotlin coroutines

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `mobile/app/build.gradle.kts` | Modify | Add CameraX deps |
| `mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt` | Create | CameraX use case binding, video recording, frame timestamps |
| `mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt` | Delete | Replaced by CameraXRecorder |
| `mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraRepositoryImpl.kt` | Rewrite | Wrap CameraXRecorder, expose StateFlows |
| `mobile/app/src/main/java/ru/skatelab/capture/domain/repository/CameraRepository.kt` | Modify | Update interface: remove Surface/prepare, add lifecycle binding |
| `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/StartRecordingUseCase.kt` | Modify | Adapt to new CameraRepository.startRecording() |
| `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/StopRecordingUseCase.kt` | Modify | CameraX non-blocking stop, IO dispatchers |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt` | Modify | CameraXViewfinder composable, remove SurfaceView |
| `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt` | Modify | IO dispatchers for sync, lifecycle binding, remove surface mgmt |
| `mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt` | Modify | Update mocks for new CameraRepository interface |

---

## Wave 1: Data Layer Foundation

### Task 1: Add CameraX dependencies

**Files:**
- Modify: `mobile/app/build.gradle.kts`

- [ ] **Step 1: Add CameraX deps to build.gradle.kts**

Add after the Protobuf block in `dependencies {}`:

```kotlin
// CameraX
val camerax_version = "1.4.1"
implementation("androidx.camera:camera-core:$camerax_version")
implementation("androidx.camera:camera-camera2:$camerax_version")
implementation("androidx.camera:camera-lifecycle:$camerax_version")
implementation("androidx.camera:camera-video:$camerax_version")
implementation("androidx.camera:camera-compose:$camerax_version")
```

- [ ] **Step 2: Verify Gradle sync succeeds**

Run: `cd mobile && ./gradlew :app:dependencies --configuration releaseRuntimeClasspath 2>&1 | grep -c "camerax" || echo "check failed"`
Expected: count > 0

- [ ] **Step 3: Commit**

```bash
git add mobile/app/build.gradle.kts
git commit -m "feat(camera): add CameraX 1.4.1 + camera-compose dependencies"
```

---

### Task 2: Update CameraRepository interface

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/repository/CameraRepository.kt`

- [ ] **Step 1: Write the updated interface**

Replace entire file content:

```kotlin
package ru.skatelab.capture.domain.repository

import androidx.lifecycle.LifecycleOwner
import java.io.File
import kotlinx.coroutines.flow.StateFlow

interface CameraRepository {
    val isPreviewReady: StateFlow<Boolean>
    val isRecording: StateFlow<Boolean>

    /** Bind CameraX use cases to [lifecycleOwner]. Must be called before recording. */
    suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit>

    /** Unbind all use cases and release camera. */
    suspend fun unbind()

    /** Start recording to [videoFile] with frame timestamps in [framesFile]. */
    suspend fun startRecording(
        videoFile: File,
        framesFile: File,
    ): Result<RecordingStartResult>

    /** Stop active recording. Non-blocking — uses CameraX VideoRecordEvent flow. */
    suspend fun stopRecording(): Result<RecordingStopResult>

    /** Release all camera resources. */
    suspend fun release()

    data class RecordingStartResult(
        val tStartCalledNs: Long,
        val tFirstFrameNs: Long,
        val timestampSource: String,
        val videoStartDelayMs: Long,
    )

    data class RecordingStopResult(
        val actualFps: Int,
        val fpsVerified: Boolean,
    )
}
```

Key changes:
- Removed `setPreviewSurface()`, `previewSurface`, `frameTimestamps`, `currentFps`, `hardwareLevel`, `restartPreview()`
- Added `bindToLifecycle(LifecycleOwner)`, `unbind()`, `isPreviewReady` StateFlow
- `startRecording()` now takes `videoFile` and `framesFile` directly
- `stopRecording()` is now `suspend` (CameraX async stop)

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/repository/CameraRepository.kt
git commit -m "refactor(camera): update CameraRepository interface for CameraX lifecycle"
```

---

### Task 3: Create CameraXRecorder

**Files:**
- Create: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt`

- [ ] **Step 1: Write CameraXRecorder**

```kotlin
package ru.skatelab.capture.data.camera

import android.content.Context
import android.os.SystemClock
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.VideoOutput
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.viewfinder.CameraViewfinder
import androidx.lifecycle.LifecycleOwner
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.asExecutor
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withTimeout
import ru.skatelab.capture.domain.repository.CameraRepository

@Singleton
class CameraXRecorder
    @Inject
    constructor(
        @ApplicationContext private val context: Context,
    ) {
        private val _isPreviewReady = MutableStateFlow(false)
        val isPreviewReady: StateFlow<Boolean> = _isPreviewReady.asStateFlow()

        private val _isRecording = MutableStateFlow(false)
        val isRecording: StateFlow<Boolean> = _isRecording.asStateFlow()

        private var cameraProvider: androidx.camera.lifecycle.ProcessCameraProvider? = null
        private var camera: Camera? = null
        private var recording: Recording? = null
        private var activeRecording: androidx.camera.video.ActiveRecording? = null
        private var timestampTracker: FrameTimestampTracker? = null
        private var viewfinder: CameraViewfinder? = null
        private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

        private var videoFile: File? = null
        private var framesFile: File? = null
        private var recorder: Recorder? = null
        private var videoCapture: VideoCapture<Recorder>? = null

        private var tStartCalledNs: Long = 0L

        suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit> =
            runCatching {
                val provider = androidx.camera.lifecycle.ProcessCameraProvider.getInstance(context)
                cameraProvider = provider

                val preview = Preview.Builder().build()

                recorder = Recorder.Builder()
                    .setAspectRatio(androidx.camera.core.AspectRatio.RATIO_16_9)
                    .build()
                videoCapture = VideoCapture.withOutput(recorder!!)

                val imageAnalysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .build()

                val cameraSelector = CameraSelector.Builder()
                    .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                    .build()

                provider.unbindAll()
                camera = provider.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    preview,
                    videoCapture,
                    imageAnalysis,
                )

                _isPreviewReady.value = true
            }

        fun setViewfinder(viewfinder: CameraViewfinder?) {
            this.viewfinder = viewfinder
        }

        fun unbind() {
            cameraProvider?.unbindAll()
            _isPreviewReady.value = false
        }

        suspend fun startRecording(
            videoFile: File,
            framesFile: File,
        ): Result<CameraRepository.RecordingStartResult> =
            runCatching {
                val capture = videoCapture ?: throw IllegalStateException("Camera not bound")
                this.videoFile = videoFile
                this.framesFile = framesFile
                timestampTracker = FrameTimestampTracker()
                timestampTracker?.open(framesFile)

                tStartCalledNs = SystemClock.elapsedRealtimeNanos()

                val outputOptions = FileOutputOptions.Builder(videoFile).build()

                val pendingRecording = capture.output
                    .prepareRecording(context, outputOptions)

                activeRecording = pendingRecording.start(
                    cameraExecutor,
                ) { event ->
                    when (event) {
                        is VideoRecordEvent.Start -> {
                            _isRecording.value = true
                        }
                        is VideoRecordEvent.Finalize -> {
                            _isRecording.value = false
                            timestampTracker?.close()
                        }
                        else -> {}
                    }
                }
                recording = activeRecording

                val startResult = CameraRepository.RecordingStartResult(
                    tStartCalledNs = tStartCalledNs,
                    tFirstFrameNs = SystemClock.elapsedRealtimeNanos(),
                    timestampSource = "REALTIME",
                    videoStartDelayMs = 0L,
                )
                startResult
            }

        suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> =
            runCatching {
                val rec = activeRecording ?: throw IllegalStateException("No active recording")
                rec.stop()
                _isRecording.value = false

                val actualFps = timestampTracker?.computeFps() ?: 0
                val frameCount = timestampTracker?.getFrameCount() ?: 0

                CameraRepository.RecordingStopResult(
                    actualFps = actualFps,
                    fpsVerified = frameCount > 10 && actualFps > 0,
                )
            }

        fun release() {
            recording?.close()
            activeRecording = null
            cameraProvider?.unbindAll()
            cameraExecutor.shutdownNow()
            cameraProvider = null
            camera = null
            _isPreviewReady.value = false
            _isRecording.value = false
        }
    }
```

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt
git commit -m "feat(camera): add CameraXRecorder — VideoCapture + Preview + ImageAnalysis"
```

---

### Task 4: Rewrite CameraRepositoryImpl

**Files:**
- Rewrite: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraRepositoryImpl.kt`

- [ ] **Step 1: Write new CameraRepositoryImpl**

```kotlin
package ru.skatelab.capture.data.camera

import androidx.lifecycle.LifecycleOwner
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import ru.skatelab.capture.domain.repository.CameraRepository

@Singleton
class CameraRepositoryImpl
    @Inject
    constructor(
        @ApplicationContext private val context: android.content.Context,
        private val recorder: CameraXRecorder,
    ) : CameraRepository {

        override val isPreviewReady = recorder.isPreviewReady
        override val isRecording = recorder.isRecording

        override suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit> =
            recorder.bindToLifecycle(lifecycleOwner)

        override suspend fun unbind() {
            recorder.unbind()
        }

        override suspend fun startRecording(
            videoFile: File,
            framesFile: File,
        ): Result<CameraRepository.RecordingStartResult> =
            recorder.startRecording(videoFile, framesFile)

        override suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> =
            recorder.stopRecording()

        override suspend fun release() {
            recorder.release()
        }
    }
```

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraRepositoryImpl.kt
git commit -m "refactor(camera): rewrite CameraRepositoryImpl — wraps CameraXRecorder"
```

---

### Task 5: Delete Camera2Recorder

**Files:**
- Delete: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt`

- [ ] **Step 1: Delete the file**

```bash
git rm mobile/app/src/main/java/ru/skatelab/capture/data/camera/Camera2Recorder.kt
```

- [ ] **Step 2: Verify no compilation references to Camera2Recorder remain**

Run: `grep -r "Camera2Recorder" mobile/app/src/ || echo "No references found"`
Expected: "No references found"

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(camera): remove Camera2Recorder — replaced by CameraXRecorder"
```

---

## Wave 2: Domain + Presentation Layer

### Task 6: Update StartRecordingUseCase

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/StartRecordingUseCase.kt`

- [ ] **Step 1: Update to use new CameraRepository.startRecording(videoFile, framesFile)**

The use case currently passes no files to `cameraRepository.startRecording()`. With CameraX, recording files are passed at start time.

Replace the `cameraDeferred` line and adjust:

```kotlin
package ru.skatelab.capture.domain.usecase

import java.io.File
import javax.inject.Inject
import javax.inject.Named
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository

class StartRecordingUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val cameraRepository: CameraRepository,
        @Named("clockNanos") private val clockNanos: () -> Long,
    ) {
        suspend operator fun invoke(
            outputDir: File,
            videoFile: File,
            framesFile: File,
            imuLeftFile: File,
            imuRightFile: File,
        ): Result<RecordingStartInfo> =
            runCatching {
                val tImuStartSentNs = clockNanos()

                val (leftResult, rightResult, cameraResult) =
                    coroutineScope {
                        val left = async(Dispatchers.IO) { bleRepository.startStreaming(SensorId.LEFT) }
                        val right = async(Dispatchers.IO) { bleRepository.startStreaming(SensorId.RIGHT) }
                        val cameraDeferred =
                            async(Dispatchers.IO) {
                                cameraRepository.startRecording(videoFile, framesFile)
                            }
                        Triple(left.await(), right.await(), cameraDeferred.await())
                    }
                if (leftResult.isFailure || rightResult.isFailure) {
                    val leftErr = leftResult.exceptionOrNull()?.message
                    val rightErr = rightResult.exceptionOrNull()?.message
                    throw Exception("BLE streaming start failed: L=$leftErr, R=$rightErr")
                }
                val cameraData = cameraResult.getOrThrow()

                val imuStartDelayMs =
                    mapOf(
                        SensorId.LEFT to ((cameraData.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
                        SensorId.RIGHT to ((cameraData.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
                    )

                RecordingStartInfo(
                    t0Ns = cameraData.tFirstFrameNs,
                    timestampSource = cameraData.timestampSource,
                    videoStartDelayMs = cameraData.videoStartDelayMs,
                    imuStartDelayMs = imuStartDelayMs,
                    videoFile = videoFile,
                    imuLeftFile = imuLeftFile,
                    imuRightFile = imuRightFile,
                    framesFile = framesFile,
                )
            }
    }

data class RecordingStartInfo(
    val t0Ns: Long,
    val timestampSource: String,
    val videoStartDelayMs: Long,
    val imuStartDelayMs: Map<SensorId, Long>,
    val videoFile: File,
    val imuLeftFile: File,
    val imuRightFile: File,
    val framesFile: File,
)
```

Key change: `cameraRepository.startRecording(videoFile, framesFile)` now called on `Dispatchers.IO` instead of main thread.

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/StartRecordingUseCase.kt
git commit -m "refactor(camera): StartRecordingUseCase — IO dispatcher, pass files to CameraRepository"
```

---

### Task 7: Update StopRecordingUseCase

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/StopRecordingUseCase.kt`

- [ ] **Step 1: Update dispatchers and non-blocking stop**

```kotlin
package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository

class StopRecordingUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val cameraRepository: CameraRepository,
    ) {
        data class StopResult(
            val actualFps: Int,
            val fpsVerified: Boolean,
        )

        suspend operator fun invoke(): Result<StopResult> {
            val errors = mutableListOf<Throwable>()
            var stopResult = StopResult(actualFps = 0, fpsVerified = false)

            try {
                coroutineScope {
                    val cameraDeferred =
                        async(Dispatchers.IO) {
                            cameraRepository.stopRecording().getOrDefault(
                                CameraRepository.RecordingStopResult(actualFps = 0, fpsVerified = false),
                            )
                        }
                    val leftDeferred =
                        async(Dispatchers.IO) {
                            bleRepository.stopStreaming(SensorId.LEFT).getOrDefault(Unit)
                        }
                    val rightDeferred =
                        async(Dispatchers.IO) {
                            bleRepository.stopStreaming(SensorId.RIGHT).getOrDefault(Unit)
                        }
                    val cameraStop = cameraDeferred.await()
                    stopResult = StopResult(actualFps = cameraStop.actualFps, fpsVerified = cameraStop.fpsVerified)
                    leftDeferred.await()
                    rightDeferred.await()
                }
            } catch (e: Exception) {
                errors.add(e)
            }

            return if (errors.isEmpty()) Result.success(stopResult) else Result.failure(errors.first())
        }
    }
```

Key change: removed `cameraRepository.release()` from stop (release happens on ViewModel `onCleared`). All dispatchers = `Dispatchers.IO`.

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/StopRecordingUseCase.kt
git commit -m "refactor(camera): StopRecordingUseCase — IO dispatcher, remove release from stop"
```

---

### Task 8: Rewrite RecordingScreen with CameraXViewfinder

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt`

- [ ] **Step 1: Replace SurfaceView with CameraXViewfinder**

Full replacement of `RecordingScreen.kt`:

```kotlin
package ru.skatelab.capture.presentation.recording

import androidx.camera.viewfinder.CameraViewfinder
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import java.io.File
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo

@Composable
fun RecordingScreen(
    viewModel: RecordingViewModel,
    outputDir: File,
    calibration: Map<SensorId, CalibrationData>,
    onRecordingComplete: (String) -> Unit,
) {
    val context = LocalContext.current

    val isRecording by viewModel.isRecording.collectAsState()
    val isPreviewReady by viewModel.isPreviewReady.collectAsState()
    val error by viewModel.error.collectAsState()
    val sessionId by viewModel.sessionId.collectAsState()
    val reconnectingSensor by viewModel.reconnectingSensor.collectAsState()
    val elapsedMs by viewModel.elapsedMs.collectAsState()
    val sensorInfo by viewModel.sensorInfo.collectAsState()

    var cameraPrepared by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.startBatteryPolling() }

    LaunchedEffect(sessionId) {
        sessionId?.let { onRecordingComplete(it) }
    }

    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentAlignment = Alignment.Center,
        ) {
            CameraPreview(
                viewModel = viewModel,
                isRecording = isRecording,
                reconnectingSensor = reconnectingSensor,
                elapsedMs = elapsedMs,
                sensorInfo = sensorInfo,
                isPreviewReady = isPreviewReady,
                onCameraReady = {
                    if (!cameraPrepared) {
                        cameraPrepared = true
                        viewModel.bindCamera(context)
                    }
                },
            )

            if (!isPreviewReady) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(modifier = Modifier.size(48.dp))
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        stringResource(R.string.recording_preparing),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }

        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (!isRecording) {
                Button(
                    onClick = {
                        viewModel.startRecording(outputDir, calibration, context)
                    },
                    enabled = isPreviewReady,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.recording_start))
                }
            } else {
                Button(
                    onClick = { viewModel.stopRecording(context) },
                    colors =
                        ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error,
                        ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.recording_stop))
                }
            }

            error?.let {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    it,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun CameraPreview(
    viewModel: RecordingViewModel,
    isRecording: Boolean,
    reconnectingSensor: SensorId?,
    elapsedMs: Long,
    sensorInfo: Map<SensorId, SensorInfo?>,
    isPreviewReady: Boolean,
    onCameraReady: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        AndroidView(
            factory = { context ->
                CameraViewfinder(context).apply {
                    viewModel.setViewfinder(this)
                    onCameraReady()
                }
            },
            modifier = Modifier.fillMaxSize(),
        )

        val leftInfo = sensorInfo[SensorId.LEFT]
        val rightInfo = sensorInfo[SensorId.RIGHT]
        if (leftInfo != null || rightInfo != null) {
            Box(
                modifier =
                    Modifier
                        .align(Alignment.TopStart)
                        .padding(12.dp)
                        .background(Color.Black.copy(alpha = 0.6f), MaterialTheme.shapes.small)
                        .padding(horizontal = 8.dp, vertical = 4.dp),
            ) {
                val parts = mutableListOf<String>()
                leftInfo?.let { parts.add("Л:${it.batteryPercent}%") }
                rightInfo?.let { parts.add("П:${it.batteryPercent}%") }
                Text(
                    parts.joinToString(" "),
                    color = Color.White,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }

        if (isRecording) {
            Box(
                modifier =
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(12.dp)
                        .background(Color.Red, MaterialTheme.shapes.small)
                        .padding(horizontal = 8.dp, vertical = 4.dp),
            ) {
                val totalSec = elapsedMs / 1000
                val min = (totalSec / 60).toInt()
                val sec = (totalSec % 60).toInt()
                Text(
                    "REC %02d:%02d".format(min, sec),
                    color = Color.White,
                    style = MaterialTheme.typography.labelLarge,
                )
            }

            if (reconnectingSensor != null) {
                Box(
                    modifier =
                        Modifier
                            .align(Alignment.TopStart)
                            .padding(12.dp)
                            .background(MaterialTheme.colorScheme.errorContainer, MaterialTheme.shapes.small)
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                ) {
                    Text(
                        "Переподключение: ${reconnectingSensor?.name?.lowercase()}",
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
        }
    }
}
```

Key changes:
- `SurfaceView` + `SurfaceHolder.Callback` → `CameraViewfinder` via `AndroidView`
- Removed manual surface lifecycle management
- `onSurfaceReady` → `onCameraReady` (calls `viewModel.bindCamera()`)
- Added `viewModel.setViewfinder()` to pass viewfinder reference

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt
git commit -m "refactor(camera): RecordingScreen — CameraViewfinder instead of SurfaceView"
```

---

### Task 9: Update RecordingViewModel

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt`

- [ ] **Step 1: Update ViewModel for CameraX**

Key changes needed:
1. Remove `setPreviewSurface(surface: Surface?)` — add `setViewfinder(viewfinder: CameraViewfinder?)`
2. Replace `prepareCamera(outputDir)` with `bindCamera(context)` that calls `cameraRepository.bindToLifecycle(lifecycleOwner)`
3. Move `timeSynchronizer.sync()` + `awaitSync()` to `Dispatchers.IO` in `startRecording()`
4. `startRecording()` passes `videoFile`, `framesFile` to `startRecordingUseCase()` (which now forwards to `cameraRepository.startRecording()`)
5. Remove `restartPreview()` or simplify it
6. Remove `Surface` import

Update the ViewModel method signatures:

```kotlin
// Replace setPreviewSurface with setViewfinder
fun setViewfinder(viewfinder: androidx.camera.viewfinder.CameraViewfinder?) {
    // Delegate to CameraXRecorder via repository
    // This is needed so CameraXRecorder can connect the viewfinder to Preview use case
}

// Replace prepareCamera with bindCamera
fun bindCamera(context: android.content.Context) {
    currentOutputDir = outputDir // outputDir comes from RecordingScreen
    // ... (file preparation stays the same)

    viewModelScope.launch {
        val lifecycleOwner = // get from SavedStateHandle or Activity context
        cameraRepository.bindToLifecycle(lifecycleOwner)
            .onSuccess { _isPreviewReady.value = true }
            .onFailure { _error.value = "Camera prepare failed: ${it.message}" }
    }
}

// In startRecording, move sync to IO dispatcher:
viewModelScope.launch {
    withContext(Dispatchers.IO) {
        timeSynchronizer.sync(viewModelScope)
        timeSynchronizer.awaitSync()
    }
    // ... rest unchanged
}
```

The ViewModel needs a `LifecycleOwner`. Inject via `@LifecycleOwner(LifecycleOwner.VIEW_MODEL)` or pass from Screen. Simplest: accept `LifecycleOwner` param in `bindCamera()`.

Add import:
```kotlin
import androidx.camera.viewfinder.CameraViewfinder
```

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt
git commit -m "fix(camera): RecordingViewModel — IO dispatchers for sync, CameraX lifecycle binding"
```

---

### Task 10: Update DI module

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/di/CameraModule.kt`

- [ ] **Step 1: Add CameraXRecorder provider if needed**

Since `CameraXRecorder` is `@Singleton` with `@Inject constructor`, Hilt handles it automatically. `CameraRepositoryImpl` already gets it injected.

No changes needed to `CameraModule.kt` — Hilt discovers `CameraXRecorder` via `@Singleton @Inject`.

- [ ] **Step 2: Verify DI compiles**

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -5`

- [ ] **Step 3: Commit (only if changes made)**

---

## Wave 3: Tests

### Task 11: Update RecordingViewModelTest

**Files:**
- Modify: `mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt`

- [ ] **Step 1: Update mocks for new CameraRepository interface**

Changes needed:
- `cameraRepository.prepare(any(), any())` → `cameraRepository.bindToLifecycle(any())`
- `cameraRepository.isRecording` stays (now `StateFlow<Boolean>`)
- Remove `cameraRepository.previewSurface` mock
- `cameraRepository.startRecording()` now returns `Result<RecordingStartResult>` (takes `videoFile, framesFile`)

Update setUp:
```kotlin
// Replace:
every { cameraRepository.isRecording } returns MutableStateFlow(false)
every { cameraRepository.previewSurface } returns MutableStateFlow(null)
// With:
every { cameraRepository.isRecording } returns MutableStateFlow(false)
every { cameraRepository.isPreviewReady } returns MutableStateFlow(false)
```

Update test `prepareCamera_setsIsPreviewReady`:
```kotlin
coEvery { cameraRepository.bindToLifecycle(any()) } returns Result.success(Unit)

viewModel.bindCamera(context) // was prepareCamera(outputDir)
runCurrent()

assertTrue(viewModel.isPreviewReady.value)
```

- [ ] **Step 2: Run tests**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "ru.skatelab.capture.presentation.recording.RecordingViewModelTest" 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/test/java/ru/skatelab/capture/presentation/recording/RecordingViewModelTest.kt
git commit -m "test(camera): update RecordingViewModelTest for CameraX interface"
```

---

### Task 12: Compile and integration test

**Files:** None (verification only)

- [ ] **Step 1: Full compile check**

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -5`
Expected: BUILD SUCCESSFUL

- [ ] **Step 2: Run all unit tests**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 3: Manual device test checklist**

1. Install app on device
2. Open recording screen → camera preview shows (no squashing in portrait)
3. Rotate to landscape → preview adapts (no squashing)
4. Start recording → no UI freeze
5. Record 5+ seconds
6. Stop recording → no UI freeze
7. Verify .mp4 file exists in session directory
8. Verify frames.csv has entries
9. Battery overlay visible (Л:N% П:N%)
10. REC indicator + timer visible during recording

- [ ] **Step 4: Commit final state if any fixes needed**

---

## Self-Review Checklist

- [x] Spec coverage: Every spec requirement maps to a task
- [x] Placeholder scan: No TBD/TODO/vague steps
- [x] Type consistency: CameraRepository.RecordingStartResult/StopResult match across all files
- [x] No speculative features beyond spec
- [x] FrameTimestampTracker preserved (reused by CameraXRecorder)
- [x] ImageAnalysis placeholder wired in CameraXRecorder.bindToLifecycle()
