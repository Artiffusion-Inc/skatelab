# Android Native Capture App — Design Spec

**Date**: 2026-05-09
**Status**: Approved
**Replaces**: Flutter `mobile/` (deleted)

## Overview

Native Android app for synchronized video + IMU capture. Connects to 2 WiTMotion WT901 BLE sensors (left foot, right foot), records 1080p@60fps video, timestamps all data in a unified clock domain, exports as ZIP for web upload.

## Tech Stack

| Component | Choice |
|---|---|
| Language | Kotlin |
| UI | Jetpack Compose |
| Camera | CameraX (VideoCapture API) |
| BLE | Android BLE API (GATT notify) |
| IMU format | Protocol Buffers (`imu.proto`) |
| DI | Hilt |
| Async | Kotlin Flow + Coroutines |
| Min SDK | 24 (Android 7.0) |
| Target SDK | 35 |

## Architecture

Single-process, Clean Architecture (DDD). Max 350 lines per file.

```
app/src/main/java/ru/skatelab/capture/
├── App.kt                          # Application + Hilt entry
├── MainActivity.kt                 # Single Activity
├── domain/
│   ├── model/
│   │   ├── ImuSample.kt            # acc(3) + gyro(3) + quat(4) + timestampNs
│   │   ├── SensorId.kt            # LEFT | RIGHT enum
│   │   ├── CaptureSession.kt      # Video + IMU refs + manifest
│   │   └── CalibrationData.kt     # quat_ref + calibratedAt
│   ├── usecase/
│   │   ├── ConnectSensorUseCase.kt
│   │   ├── CalibrateSensorUseCase.kt
│   │   ├── StartRecordingUseCase.kt
│   │   ├── StopRecordingUseCase.kt
│   │   └── ExportSessionUseCase.kt
│   └── repository/
│       ├── BleRepository.kt        # Interface
│       ├── CameraRepository.kt     # Interface
│       └── SessionRepository.kt    # Interface
├── data/
│   ├── ble/
│   │   ├── BleManager.kt          # Scan, connect, GATT notify
│   │   ├── Wt901Parser.kt         # Raw bytes → ImuSample
│   │   ├── Wt901Commander.kt      # Start/stop streaming commands
│   │   └── BleRepositoryImpl.kt
│   ├── camera/
│   │   ├── CameraRecorder.kt      # CameraX VideoCapture
│   │   ├── FrameTimestampTracker.kt # ImageReader per-frame timestamps
│   │   └── CameraRepositoryImpl.kt
│   ├── export/
│   │   ├── ZipExporter.kt         # MP4 + .pb + manifest → ZIP
│   │   ├── ManifestBuilder.kt     # JSON manifest v2.0
│   │   └── ProtobufEncoder.kt     # ImuSample → IMUStream .pb
│   ├── sync/
│   │   └── TimeSyncManager.kt     # Offset calc, clock domain bridging
│   └── repository/
│       └── SessionRepositoryImpl.kt
└── presentation/
    ├── theme/
    │   └── AppTheme.kt
    ├── ble/
    │   ├── BleScanScreen.kt
    │   └── BleScanViewModel.kt
    ├── camera/
    │   ├── CameraPreviewScreen.kt
    │   └── CameraViewModel.kt
    ├── calibration/
    │   ├── CalibrationScreen.kt
    │   └── CalibrationViewModel.kt
    ├── recording/
    │   ├── RecordingScreen.kt
    │   └── RecordingViewModel.kt
    └── export/
        ├── ExportScreen.kt
        └── ExportViewModel.kt
```

## BLE Connection

### WT901 Protocol

- **Service UUID**: per WT901 spec (to be verified at implementation)
- **Notify characteristic**: IMU data frames (acc + gyro + quaternion + relative_timestamp_ms)
- **Write characteristic**: start/stop streaming commands
- **Sample rate**: 100Hz configurable via Wt901Commander

### Connection Flow

1. `BleScanScreen` → scan for WT901 devices
2. User selects LEFT sensor → connect → subscribe notify
3. User selects RIGHT sensor → connect → subscribe notify
4. `Wt901Parser`: raw BLE bytes → `ImuSample(acc, gyro, quat, sensorRelativeMs)`
5. Connected state persisted in `BleRepository`

## Clock Synchronization

### Strategy: Offset at Start

All timestamps unified in `CLOCK_BOOTTIME` domain (`SystemClock.elapsedRealtimeNanos()`).

**IMU→Android mapping**:
```
When first BLE packet arrives from each sensor:
  t0_android = SystemClock.elapsedRealtimeNanos()
  t0_sensor_ms = packet.relative_timestamp_ms
  offset = t0_android - (t0_sensor_ms * 1_000_000L)

All subsequent IMU timestamps:
  androidNs = (sensorRelativeMs * 1_000_000L) + offset
```

**Camera frame timestamps**:
- CameraX `VideoRecordEvent` does not expose per-frame timestamps
- Solution: parallel `ImageReader` with `YUV_420_888` added as extra output surface
- `image.timestamp` is in `CLOCK_BOOTTIME` domain (same as `elapsedRealtimeNanos()`)
- Written to `frame_timestamps.csv` per recording

**Result**: camera frames, IMU samples, and calibration events all share one clock domain. No post-hoc alignment needed.

### Drift

For recordings < 10 minutes, single-offset is sufficient. WT901 internal clock drift is negligible for this duration. For longer recordings, periodic drift calibration can be added later.

## Recording Flow

### Start

1. `StartRecordingUseCase`:
   - Start CameraX `VideoCapture` → MP4 file on disk
   - Start `FrameTimestampTracker` (ImageReader callback → CSV)
   - Start BLE streaming via `Wt901Commander.start()` on both sensors
   - Record `sessionStartNs = elapsedRealtimeNanos()`
   - Start Foreground Service (wake lock + notification)

### During Recording

- CameraX → MP4 on disk (hardware encoder)
- FrameTimestampTracker → `frame_timestamps.csv` on disk
- BLE (L+R) → in-memory `RingBuffer<ImuSample>` (capacity ~600K samples = 10 min × 100Hz × 2 sensors × 56 bytes ≈ 67MB)
- RecordingScreen HUD: duration, FPS, IMU sample rate, sensor battery, storage remaining

### Stop

1. `StopRecordingUseCase`:
   - Stop CameraX recording (flush MP4)
   - Stop BLE streaming on both sensors
   - Flush RingBuffer → `left.pb`, `right.pb` (Protobuf)
   - Build `manifest.json`
   - Create `CaptureSession` with all file references
   - Stop Foreground Service

## Calibration

Sensors are **on the athlete's feet**, athlete stands still.

### Flow

1. `CalibrationScreen`: "Встаньте ровно, не двигайтесь. Датчики на ногах."
2. Collect 10 seconds of quaternion data (~1000 samples at 100Hz) from each sensor
3. Filter: discard samples where `|angular_velocity| > threshold` (movement detected)
4. Average remaining quaternions → `quat_ref` per sensor
5. UI: progress bar (10s countdown), feedback on movement detection
6. Save `CalibrationData(quat_ref, calibratedAt)` per sensor
7. During recording: each quaternion normalized via `quat_ref⁻¹` → relative orientation

### In Manifest

```json
"calibration": {
  "left": { "quat_ref": [1,0,0,0], "calibrated_at": "2026-05-09T..." },
  "right": { "quat_ref": [1,0,0,0], "calibrated_at": "2026-05-09T..." }
}
```

## Export

### ZIP Structure

```
capture_20260509_143000.zip
├── capture_20260509_143000.mp4           # 1080p@60fps H.264
├── capture_20260509_143000_left.pb      # Protobuf IMUStream
├── capture_20260509_143000_right.pb     # Protobuf IMUStream
├── capture_20260509_143000_frames.csv   # frame_index,timestamp_ns
└── capture_20260509_143000.json         # Manifest v2.0
```

### Manifest v2.0

```json
{
  "version": "2.0",
  "created_at": "2026-05-09T14:30:00Z",
  "t0_ns": 12345678900000,
  "duration_ms": 5000,
  "video": {
    "filename": "capture_20260509_143000.mp4",
    "fps": 60,
    "width": 1920,
    "height": 1080,
    "frame_timestamps_file": "capture_20260509_143000_frames.csv"
  },
  "imu": {
    "left": {
      "filename": "capture_20260509_143000_left.pb",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-XXXX",
      "clock_offset_ns": 12345
    },
    "right": {
      "filename": "capture_20260509_143000_right.pb",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-YYYY",
      "clock_offset_ns": 67890
    }
  },
  "calibration": {
    "left": { "quat_ref": [1,0,0,0], "calibrated_at": "2026-05-09T14:29:50Z" },
    "right": { "quat_ref": [1,0,0,0], "calibrated_at": "2026-05-09T14:29:50Z" }
  }
}
```

### Upload

**Two-phase upload** (matches existing backend contract):

1. **Unpack ZIP locally**, upload each file individually via presigned URLs:
   - `POST /api/v1/uploads/presign` → get presigned PUT URL for each file
   - `PUT <presigned_url>` for each: `.mp4`, `_left.pb`, `_right.pb`, `_frames.csv`, `.json`
   - Collect R2 keys from upload responses

2. **Create session**:
   - `POST /api/v1/sessions` with `video_key`, `imu_left_key`, `imu_right_key`, `manifest_key`

The ZIP is a local export format. Upload sends individual files to match the backend's existing presigned URL flow.

## Error Handling

| Scenario | Handling |
|---|---|
| BLE disconnect during recording | Foreground Service + auto-reconnect (3 attempts, 1s interval). If all fail: stop recording, mark session `incomplete` |
| Camera permission denied | `PermissionScreen` → request, block navigation until granted |
| 1080p@60fps unsupported | CameraX `QualitySelector` fallback: 1080p@30fps → UI warning |
| Storage full | Pre-flight check: minimum 500MB free. If insufficient during recording: stop + warn |
| App killed during recording | Foreground Service + persistent notification. On restart: check incomplete sessions, offer export |
| Sensor not found in scan | Show "No WT901 found. Make sure sensor is powered on." with retry button |

## UI Screens

1. **BleScanScreen**: Scan for WT901 devices, assign LEFT/RIGHT, show connection status + battery
2. **CalibrationScreen**: 10s countdown, movement detection feedback, quaternion visualization
3. **CameraPreviewScreen**: Live camera preview with record button, settings (resolution, FPS)
4. **RecordingScreen**: Active recording HUD — duration, FPS, IMU rate, battery indicators, stop button
5. **ExportScreen**: Session list, ZIP generation progress, upload to R2 progress

## Protobuf Schema (reused from Flutter)

```protobuf
syntax = "proto3";

message IMUSample {
  uint64 relative_timestamp_ms = 1;
  float acc_x = 2;
  float acc_y = 3;
  float acc_z = 4;
  float gyro_x = 5;
  float gyro_y = 6;
  float gyro_z = 7;
  float quat_w = 8;
  float quat_x = 9;
  float quat_y = 10;
  float quat_z = 11;
}

message IMUStream {
  repeated IMUSample samples = 1;
}
```

## Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Camera API | CameraX | User preference; simpler API than Camera2; VideoCapture handles encoding |
| Clock sync | Offset at start | Sufficient for <10min; WT901 drift negligible; simpler than periodic calibration |
| IMU storage | In-memory RingBuffer | 67MB for 10min × 2 sensors; flush on stop; no DB overhead |
| IMU format | Protobuf | Reused from Flutter; compact binary; backend already expects it |
| Export | ZIP archive | Compatible with existing upload flow; single file to manage |
| DI | Hilt | Standard Android DI; works with ViewModels and Services |
| minSdk | 24 | CameraX requires API 21+; BLE peripheral mode 24+; practical minimum |

## Out of Scope (MVP)

- Video stabilization (deliberately disabled — corrupts timestamps)
- Audio recording (MediaRecorder adds extra frames for AV sync)
- Multi-phone sync (RecSync / SoftwareSync)
- Real-time IMU visualization on camera preview
- Automatic cloud upload without user action
- Room DB for IMU buffer (add if long recordings needed)
