# CameraX Migration Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task.

**Goal:** Replace Camera2 with CameraX + camera-compose to fix UI freeze on recording start/stop, landscape squashing, and enable future skeletal overlay.

**Architecture:** CameraX VideoCapture for recording, CameraXViewfinder composable for preview (auto aspect ratio), ImageAnalysis use case as placeholder for MogaNet-B overlay. All blocking ops moved to IO dispatcher.

**Tech Stack:** CameraX 1.4.1, camera-compose 1.4.1, Compose, Hilt, Kotlin coroutines

---

## Problems (Root Causes)

1. **UI freeze on recording start** — `timeSynchronizer.sync()` + `awaitSync()` run on main thread (~6s with 2 sensors × 3s timeout)
2. **UI freeze on recording stop** — Camera2 `mediaRecorder.stop()` is blocking; `timeSynchronizer.stop()` on main thread
3. **Landscape squashing** — Hardcoded 1920×1080 resolution, no surface size adaptation to device aspect ratio or rotation
4. **No skeletal overlay path** — Camera2 doesn't provide real-time frame analysis use case

## Solution

### Data/Camera Layer

Replace `Camera2Recorder` with `CameraXRecorder`:

```
CameraXRecorder:
  - ProcessCameraProvider.getInstance() for camera lifecycle
  - Preview + VideoCapture + ImageAnalysis use cases
  - Recorder.Builder().setAspectRatio(RATIO_16_9) for video
  - FileOutputOptions for video file + frame timestamps
  - ActiveUnpublishedVideoEvent flow for recording state
  - ImageAnalysis with STRATEGY_KEEP_ONLY_LATEST (placeholder analyzer)
```

**CameraRepository interface changes:**
- Remove: `prepare(videoFile, framesFile)`, `setPreviewSurface(surface)`, `isRecording`, `previewSurface`
- Add: `bindToLifecycle(lifecycleOwner)`, `unbind()`, `getPreviewView()`
- Keep: `startRecording(videoFile, framesFile)`, `stopRecording()`, `restartPreview()`, `release()`

**CameraRepositoryImpl** — wraps CameraXRecorder, provides StateFlows for UI.

### Presentation/Recording Layer

**RecordingScreen.kt:**
- Replace `AndroidView(SurfaceView)` + `SurfaceHolder.Callback` with `CameraXViewfinder` composable
- Remove manual surface management code
- CameraXViewfinder handles aspect ratio + rotation automatically

**RecordingViewModel.kt:**
- Move `timeSynchronizer.sync()` + `awaitSync()` to `Dispatchers.IO` (was main thread → 6s freeze)
- `startRecording()` — sync on IO, then start recording
- `stopRecording()` — ensure `stopRecordingUseCase()` runs on IO dispatcher
- `prepareCamera()` — now calls `cameraRepository.bindToLifecycle(lifecycleOwner)` instead of `prepare()`
- Remove `setPreviewSurface()` (CameraXViewfinder handles this)
- Add `lifecycleOwner` param to `bindToLifecycle()`

### Blocking Operations Fix

| Operation | Current | Fix |
|-----------|---------|-----|
| `timeSynchronizer.sync()` | Main thread | `withContext(Dispatchers.IO) { ... }` |
| `timeSynchronizer.awaitSync()` | Main thread | `withContext(Dispatchers.IO) { ... }` |
| `mediaRecorder.stop()` | Main thread | CameraX `VideoRecordEvent.Finalize` callback (non-blocking) |
| `cameraRepository.prepare()` | Main thread | CameraX `ProcessCameraProvider` on IO |

### Dependencies

```kotlin
// app/build.gradle.kts
val camerax_version = "1.4.1"
implementation("androidx.camera:camera-core:$camerax_version")
implementation("androidx.camera:camera-camera2:$camerax_version")
implementation("androidx.camera:camera-lifecycle:$camerax_version")
implementation("androidx.camera:camera-video:$camerax_version")
implementation("androidx.camera:camera-compose:$camerax_version")
```

Remove Camera2 direct dependencies (if any beyond camera-camera2 interop).

### ImageAnalysis Placeholder

```kotlin
// In CameraXRecorder
val imageAnalysis = ImageAnalysis.Builder()
    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
    .build()
// No analyzer set yet — will add MogaNet-B inference later
```

This ensures the use case is bound to camera lifecycle and available for future skeletal overlay.

## File Changes

| File | Action | Purpose |
|------|--------|---------|
| `data/camera/Camera2Recorder.kt` | **Delete** | Replaced by CameraXRecorder |
| `data/camera/CameraXRecorder.kt` | **Create** | CameraX VideoCapture + Preview + ImageAnalysis |
| `data/camera/CameraRepositoryImpl.kt` | **Rewrite** | Wrap CameraXRecorder instead of Camera2Recorder |
| `domain/repository/CameraRepository.kt` | **Modify** | Update interface for CameraX lifecycle |
| `domain/usecase/StartRecordingUseCase.kt` | **Modify** | Adapt to CameraX recording API |
| `domain/usecase/StopRecordingUseCase.kt` | **Modify** | Adapt to CameraX non-blocking stop |
| `presentation/recording/RecordingScreen.kt` | **Modify** | CameraXViewfinder composable |
| `presentation/recording/RecordingViewModel.kt` | **Modify** | IO dispatchers, lifecycle binding, remove surface mgmt |
| `app/build.gradle.kts` | **Modify** | Add CameraX deps, remove Camera2 direct deps |
| `di/CameraModule.kt` | **Modify** | Bind CameraXRecorder |

## Out of Scope

- Skeletal overlay inference (MogaNet-B on-device) — future task
- Slow motion / custom FPS config — future task
- Multi-camera support — future task
- Camera switching (front/back) — single back camera for now

## References

- [google/jetpack-camera-app](https://github.com/google/jetpack-camera-app) — architecture reference, video recording, CameraXViewfinder
- [android/platform-samples/camerax](https://github.com/android/platform-samples/tree/main/samples/camera/camerax) — minimal CameraX+Compose integration
- [CameraX compose API](https://developer.android.com/reference/kotlin/androidx/camera/compose/package-summary) — CameraXViewfinder composable docs
- [l2hyunwoo/compose-camera](https://github.com/l2hyunwoo/compose-camera) — KMP CameraX+Compose library (reference for video recording flow)

## Testing

- `RecordingViewModelTest.kt` — update mocks for new CameraRepository interface
- `CameraXRecorderTest.kt` — new: test recording start/stop, file output
- Integration test: record 5s video → verify .mp4 exists + frames.csv has entries
- Manual test: rotate device during recording → no squashing
- Manual test: start/stop recording → no UI freeze
