# Remove CameraXRecorder — Camera2-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove CameraXRecorder and all CameraX dependencies, keeping only Camera2Recorder for video capture.

**Architecture:** Camera2Recorder already works with `ImageReader` + `FrameTimestampTracker` for real per-frame timestamps. CameraRepositoryImpl simplifies to a single code path. RecordingScreen switches from CameraX `PreviewView` to `SurfaceView` for camera preview.

**Tech Stack:** Android Camera2 API, SurfaceView, MediaRecorder

---

### Task 1: Remove CameraXRecorder.kt

**Files:**
- Delete: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt`

- [ ] **Step 1: Delete CameraXRecorder.kt**

```bash
rm mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "refactor(mobile): remove CameraXRecorder — Camera2-only path"
```

---

### Task 2: Remove CameraX dependencies from build.gradle.kts

**Files:**
- Modify: `mobile/app/build.gradle.kts`

- [ ] **Step 1: Remove CameraX dependencies**

Remove these 5 lines from `dependencies` block:

```kotlin
    // Camera — remove these lines:
    implementation("androidx.camera:camera-core:1.4.2")
    implementation("androidx.camera:camera-camera2:1.4.2")
    implementation("androidx.camera:camera-lifecycle:1.4.2")
    implementation("androidx.camera:camera-video:1.4.2")
    implementation("androidx.camera:camera-view:1.4.2")
```

- [ ] **Step 2: Commit**

```bash
git add mobile/app/build.gradle.kts && git commit -m "refactor(mobile): remove CameraX dependencies"
```

---

### Task 3: Simplify CameraRepositoryImpl — remove CameraX branching

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/data/camera/CameraRepositoryImpl.kt`
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/repository/CameraRepository.kt`

- [ ] **Step 1: Remove `setPreviewSurfaceProvider` from CameraRepository interface**

In `CameraRepository.kt`, remove:

```kotlin
    fun setPreviewSurfaceProvider(provider: Any?)
```

- [ ] **Step 2: Simplify CameraRepositoryImpl — remove CameraX branching**

Replace the entire `CameraRepositoryImpl.kt` with a simplified version that only uses `Camera2Recorder`:

```kotlin
package ru.skatelab.capture.data.camera

import android.content.Context
import android.view.Surface
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CameraRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
) : CameraRepository {

    private val _isRecording = MutableStateFlow(false)
    private val _frameTimestamps = MutableStateFlow(0L)
    private val _currentFps = MutableStateFlow(0)
    private val _hardwareLevel = MutableStateFlow(-1)
    private val _previewSurface = MutableStateFlow<Surface?>(null)

    private var recorder: Camera2Recorder? = null

    override val isRecording: Flow<Boolean> = _isRecording
    override val frameTimestamps: Flow<Long> = _frameTimestamps
    override val currentFps: Flow<Int> = _currentFps
    override val hardwareLevel: Flow<Int> = _hardwareLevel
    override val previewSurface: StateFlow<Surface?> = _previewSurface.asStateFlow()

    override fun setPreviewSurface(surface: Surface?) {
        _previewSurface.value = surface
    }

    override suspend fun prepare(outputFile: File, timestampsFile: File): Result<Unit> = runCatching {
        val rec = Camera2Recorder(context)
        rec.openCamera()
        _hardwareLevel.value = rec.getHardwareLevel()
        rec.prepare(
            outputFile = outputFile,
            timestampsFile = timestampsFile,
            previewSurface = _previewSurface.value,
        )
        recorder = rec
    }

    override suspend fun startRecording(): Result<CameraRepository.RecordingStartResult> = runCatching {
        val rec = recorder ?: throw IllegalStateException("Camera not prepared")
        val result = rec.startRecording()
        _isRecording.value = true
        _currentFps.value = result.actualFps
        result
    }

    override suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> = runCatching {
        val rec = recorder ?: throw IllegalStateException("Camera not recording")
        val result = rec.stopRecording()
        _isRecording.value = false
        _currentFps.value = 0
        result
    }

    override suspend fun release() {
        recorder?.release()
        recorder = null
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "refactor(mobile): simplify CameraRepositoryImpl — Camera2-only path"
```

---

### Task 4: Remove setPreviewSurfaceProvider from RecordingViewModel

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt`

- [ ] **Step 1: Remove setPreviewSurfaceProvider method**

Remove these lines from `RecordingViewModel.kt`:

```kotlin
    fun setPreviewSurfaceProvider(provider: Any?) {
        cameraRepository.setPreviewSurfaceProvider(provider)
    }
```

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt && git commit -m "refactor(mobile): remove setPreviewSurfaceProvider from RecordingViewModel"
```

---

### Task 5: Replace CameraX PreviewView with SurfaceView in RecordingScreen

**Files:**
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt`

- [ ] **Step 1: Rewrite CameraPreview composable**

Replace the `CameraPreview` composable to use `SurfaceView` instead of CameraX `PreviewView`. Remove `setPreviewSurfaceProvider` call. Keep `setPreviewSurface` call.

New `CameraPreview` implementation:

```kotlin
@Composable
private fun CameraPreview(
    viewModel: RecordingViewModel,
    isRecording: Boolean,
    reconnectingSensor: SensorId?,
    elapsedMs: Long,
    onSurfaceReady: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        AndroidView(
            factory = { context ->
                android.view.SurfaceView(context).apply {
                    holder.addCallback(object : android.view.SurfaceHolder.Callback {
                        override fun surfaceCreated(holder: android.view.SurfaceHolder) {
                            viewModel.setPreviewSurface(holder.surface)
                            onSurfaceReady()
                        }
                        override fun surfaceChanged(holder: android.view.SurfaceHolder, format: Int, width: Int, height: Int) {}
                        override fun surfaceDestroyed(holder: android.view.SurfaceHolder) {
                            viewModel.setPreviewSurface(null)
                        }
                    })
                }
            },
            modifier = Modifier.fillMaxSize(),
        )

        // REC indicator + timer overlay
        if (isRecording) {
            Box(
                modifier = Modifier
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

            // Reconnect warning
            if (reconnectingSensor != null) {
                Box(
                    modifier = Modifier
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

Remove the `import androidx.camera.view.PreviewView` import.

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt && git commit -m "refactor(mobile): replace CameraX PreviewView with SurfaceView"
```

---

### Task 6: Update CameraRepositoryImplTest — remove CameraX tests

**Files:**
- Modify: `mobile/app/src/test/java/ru/skatelab/capture/data/camera/CameraRepositoryImplTest.kt`

- [ ] **Step 1: Replace tests with Camera2-only assertions**

The old tests check hardware level branching logic. Since we removed that branching, replace with a simple test that verifies the threshold constants:

```kotlin
package ru.skatelab.capture.data.camera

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraRepositoryImplTest {

    @Test
    fun fullHardwareLevel_isSupported() {
        val isSupported = FULL >= FULL
        assertTrue("FULL (2) devices should be supported", isSupported)
    }

    @Test
    fun level3HardwareLevel_isSupported() {
        val isSupported = LEVEL_3 >= FULL
        assertTrue("LEVEL_3 (3) devices should be supported", isSupported)
    }

    @Test
    fun legacyHardwareLevel_isNotSupported() {
        val isSupported = LEGACY >= FULL
        assertFalse("LEGACY (0) devices should NOT be supported", isSupported)
    }

    @Test
    fun limitedHardwareLevel_isNotSupported() {
        val isSupported = LIMITED >= FULL
        assertFalse("LIMITED (1) devices should NOT be supported", isSupported)
    }

    companion object {
        private const val LEGACY = 0
        private const val LIMITED = 1
        private const val FULL = 2
        private const val LEVEL_3 = 3
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add mobile/app/src/test/java/ru/skatelab/capture/data/camera/CameraRepositoryImplTest.kt && git commit -m "test(mobile): update CameraRepositoryImplTest for Camera2-only path"
```

---

### Task 7: Compile and verify

- [ ] **Step 1: Compile**

```bash
cd mobile && ./gradlew :app:compileDebugKotlin
```

Expected: BUILD SUCCESSFUL, no new errors (existing deprecation warnings OK).

- [ ] **Step 2: Run unit tests**

```bash
cd mobile && ./gradlew :app:testDebugUnitTest
```

Expected: All tests pass.

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix(mobile): compile and test fixes for Camera2-only"
```