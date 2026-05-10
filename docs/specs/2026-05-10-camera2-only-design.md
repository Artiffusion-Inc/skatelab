# Camera2-Only Recorder Design

## Context

App has two camera recorders: `Camera2Recorder` (FULL/LEVEL_3 devices) and `CameraXRecorder` (LEGACY/LIMITED fallback). CameraXRecorder has critical issues:
- No real frame timestamps — only `CAMERAX_ESTIMATED` (synthetic 16.67ms intervals)
- MP4 finalization requires async `VideoRecordEvent.Finalize` handling (was a stub → now fixed, but adds complexity)
- `StubLifecycleOwner` hack for CameraX lifecycle

Camera2Recorder already works correctly:
- `ImageReader` + `FrameTimestampTracker` for real per-frame timestamps
- `MediaRecorder.stop()` is synchronous — no finalization race
- Direct `CaptureRequest` control (fps range, stabilization)

## Decision

Remove `CameraXRecorder`. Use only `Camera2Recorder`. Accept that LEGACY/LIMITED devices cannot record video.

## Changes

### Delete
- `CameraXRecorder.kt` — entire file (incl. `StubLifecycleOwner`)
- `CameraRepositoryImpl.useCameraX` flag and `cameraXRecorder` field
- `CameraRepositoryImpl.probeHardwareLevel()` — no longer needed for branching
- `CameraRepository.setPreviewSurfaceProvider(Any?)` — CameraX-specific API
- CameraX dependencies from `build.gradle.kts`: `camera-video`, `camera-core`, `camera-lifecycle`
- CameraX `PreviewView` usage in UI (replace with `SurfaceView`/`TextureView`)

### Simplify
- `CameraRepositoryImpl.prepare()` → directly create `Camera2Recorder`, no hardware level branching
- `CameraRepositoryImpl.startRecording()`, `stopRecording()`, `release()` → single code path, no `if (useCameraX)` branches
- Keep `hardwareLevel` flow in `CameraRepository` for informational logging, but remove branching logic

### LEGACY device handling
- `Camera2Recorder.prepare()` will fail on LEGACY devices (Camera2 HAL issues)
- `CameraRepositoryImpl` catches the failure, returns `Result.failure()`
- UI shows error toast: "Camera not supported on this device"

## Interface changes
- `CameraRepository.setPreviewSurfaceProvider(Any?)` — **removed**
- `CameraRepository.setPreviewSurface(Surface?)` — **kept**

## What stays unchanged
- `Camera2Recorder` — no modifications needed
- `FrameTimestampTracker` — no modifications
- `StartRecordingUseCase`, `StopRecordingUseCase` — no modifications
- `RecordingViewModel` — minor: remove `setPreviewSurfaceProvider()` call, update UI

## Risk
LEGACY/LIMITED camera HAL devices (common on Android 10-12 budget phones) cannot record. This is accepted — the app targets figure skating training where users typically have mid-range or flagship devices.
