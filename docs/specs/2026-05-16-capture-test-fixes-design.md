# Android Capture Test Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 bugs in session manifest and CaptureSession model discovered during device testing.

**Architecture:** Update CaptureSession data model to carry actual FPS/verified flags and firstFrameNs, propagate through ViewModel → Repository → Export pipeline.

**Tech Stack:** Kotlin, Android, JUnit 5

---

## Background

Device testing of the recording + export pipeline revealed:
- `frames.csv` was empty (only header) — fixed by adding `ImageAnalysis.setAnalyzer()` in `CameraXRecorder`
- `actual_fps_verified` always `false` in manifest.json despite FPS being measured correctly
- `fps` field in manifest shows hardcoded 60 instead of actual measured FPS (30)
- `firstFrameNs` always 0 in manifest despite `FrameTimestampTracker` tracking it

## Bug 1 (RESOLVED): frames.csv empty — onFrame() not called

**Status:** Fixed in `CameraXRecorder.bindToLifecycle()` — added `imageAnalysis.setAnalyzer(cameraExecutor)` that calls `timestampTracker?.onFrame(SystemClock.elapsedRealtimeNanos())`.

No further action needed. Documented for history.

## Bug 2: actual_fps_verified always false in manifest

**File:** `CaptureSession.kt`, `ExportSessionUseCase.kt`, `RecordingViewModel.kt`, `SessionRepositoryImpl.kt`

**Current (broken):**
- `CaptureSession` has `videoFps: Int` (hardcoded 60) but no `actualFps` or `fpsVerified`
- `ExportSessionUseCase.buildManifest()` calls `fps(session.videoFps)` — always writes 60
- `ExportSessionUseCase` never calls `actualFpsVerified()` — always defaults to `false`
- `StopRecordingUseCase.StopResult` has `actualFps` and `fpsVerified`, but ViewModel doesn't pass them to `CaptureSession`

**Fix:**
- Add `actualFps: Int` and `fpsVerified: Boolean` to `CaptureSession`
- Remove `videoFps: Int` from `CaptureSession` (replaced by `actualFps`)
- `RecordingViewModel.stopRecording()` passes `stopResult.actualFps` and `stopResult.fpsVerified` into `CaptureSession`
- `ExportSessionUseCase.buildManifest()` calls:
  - `fps(session.actualFps)` instead of `fps(session.videoFps)`
  - `actualFpsVerified(session.fpsVerified)`
- `SessionRepositoryImpl` serializes/deserializes `actualFps` and `fpsVerified` (with backward compat: `actualFps` defaults to `videoFps` value if missing from old JSON, `fpsVerified` defaults to `false`)

## Bug 3: fps field shows hardcoded 60 instead of actual measured FPS

**File:** Same as Bug 2

**Current:** `videoFps` is set to a hardcoded constant (60) when creating `CaptureSession`. Actual FPS measured by `FrameTimestampTracker` (typically ~30) is discarded.

**Fix:** Replaced by `actualFps` from Bug 2. `RecordingViewModel` uses `actualVideoFps` field (already populated from `StopRecordingUseCase.StopResult`) instead of a hardcoded value.

## Bug 4: firstFrameNs always 0 in manifest

**File:** `CaptureSession.kt`, `ExportSessionUseCase.kt`, `RecordingViewModel.kt`, `SessionRepositoryImpl.kt`

**Current (broken):**
- `FrameTimestampTracker.getFirstFrameNs()` returns the timestamp of the first recorded frame
- `ManifestBuilder.VideoBlock` has `firstFrameNs(ns: Long)` method
- But `CaptureSession` has no `firstFrameNs` field, so `ExportSessionUseCase` never calls it
- Manifest always shows `"first_frame_ns": 0`

**Fix:**
- Add `firstFrameNs: Long` to `CaptureSession` (relative offset from `t0Ns`, i.e. `tracker.getFirstFrameNs() - t0Ns`)
- `RecordingViewModel.stopRecording()` computes `firstFrameNs = timestampTracker.getFirstFrameNs() - startInfo.t0Ns` and passes it to `CaptureSession`
- `ExportSessionUseCase.buildManifest()` calls `firstFrameNs(session.firstFrameNs)`
- `SessionRepositoryImpl` serializes/deserializes `firstFrameNs` (backward compat: defaults to `0L`)

## Files to Change

| File | Change |
|------|--------|
| `CaptureSession.kt` | Add `actualFps`, `fpsVerified`, `firstFrameNs`; remove `videoFps` |
| `RecordingViewModel.kt` | Pass `actualFps`/`fpsVerified` from stop result; compute `firstFrameNs` from tracker |
| `ExportSessionUseCase.kt` | Use `session.actualFps`, call `actualFpsVerified()`, call `firstFrameNs()` |
| `SessionRepositoryImpl.kt` | Serialize/deserialize new fields with backward compat |
| `StopRecordingUseCase.kt` | Return `actualFps`/`fpsVerified` (already does — no change needed) |
| `CameraXRecorder.kt` | Already fixed (Bug 1) — no further change |
| `RecordingViewModelTest.kt` | Update tests for new CaptureSession fields |
| `ExportSessionUseCaseTest.kt` | Update manifest assertion for `actualFps`, `fpsVerified`, `firstFrameNs` |
| `SessionRepositoryImplTest.kt` | Add backward compat tests for new fields |

## Testing

- Unit test: `CaptureSession` construction with new fields
- Unit test: `ExportSessionUseCase` produces manifest with correct `fps`, `actual_fps_verified`, `first_frame_ns`
- Unit test: `SessionRepositoryImpl` backward compat — old JSON without `actualFps`/`firstFrameNs` deserializes correctly
- Integration: record 5-10s session, export, verify manifest has `fps: ~30`, `actual_fps_verified: true`, `first_frame_ns: >0`