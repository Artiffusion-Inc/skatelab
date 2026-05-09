# Android Native Capture App — Design Spec

**Date**: 2026-05-09
**Status**: Approved (rev 2 — post scientific review)
**Replaces**: Flutter `mobile/` (deleted)

## Overview

Native Android app for synchronized video + IMU capture. Connects to 2 WiTMotion WT901 BLE sensors (left foot, right foot), records 1080p@60fps video, timestamps all data in a unified clock domain, exports as ZIP for web upload.

## Tech Stack

| Component | Choice |
|---|---|
| Language | Kotlin |
| UI | Jetpack Compose |
| Camera | Camera2 API (primary) + CameraX (LEVEL_3 devices) |
| BLE | Android BLE API (GATT notify) |
| IMU format | Protocol Buffers (delimited per-sample streaming) |
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
│   │   ├── Wt901Commander.kt      # Start/stop streaming, config packets
│   │   ├── BleRepositoryImpl.kt
│   │   └── BleHandlerThread.kt    # Dedicated HandlerThread for BLE processing
│   ├── camera/
│   │   ├── Camera2Recorder.kt      # Camera2 API + MediaRecorder
│   │   ├── FrameTimestampTracker.kt # ImageReader (YUV_420_888) per-frame timestamps
│   │   ├── CameraXRecorder.kt      # CameraX fallback for LEVEL_3 devices
│   │   └── CameraRepositoryImpl.kt
│   ├── export/
│   │   ├── ZipExporter.kt         # MP4 + .binpb + manifest → ZIP
│   │   ├── ManifestBuilder.kt     # JSON manifest v2.0
│   │   └── ImuStreamWriter.kt     # Per-sample writeDelimitedTo() to file
│   ├── sync/
│   │   └── TimeSyncManager.kt     # Median offset, periodic resync, drift tracking
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

## Camera: Camera2 Primary (with CameraX Fallback)

### Why Camera2, not CameraX

**Scientific review finding (H1 FALSIFIED):** CameraX `Preview + VideoCapture + ImageAnalysis` requires a LEVEL_3 camera device. Most phones are FULL or LIMITED — the triple use case combination fails with `IllegalArgumentException`. CameraX VideoCapture provides no per-frame timestamp API.

Camera2 with `MediaRecorder.surface + ImageReader(YUV_420_888)` uses only 2 camera outputs — supported on LEGACY+ devices (all phones). This gives both video recording AND per-frame timestamps, proven by OpenCamera-Sensors.

### Camera2 Recording Architecture

```
Camera2 CameraCaptureSession:
  Surface 1: MediaRecorder.surface → MP4 (H.264 hardware encoder)
  Surface 2: ImageReader(YUV_420_888) → onImageAvailable → image.timestamp → CSV

ImageReader callback:
  - image.timestamp is in CLOCK_BOOTTIME domain (same as elapsedRealtimeNanos)
  - Write to frame_timestamps.csv: frame_index, timestamp_ns
  - DO NOT process image pixels — only extract timestamp, close image immediately
  - Use SingleThreadExecutor for CSV writes (avoid blocking camera callback)
```

### CameraX Fallback (LEVEL_3 devices)

On LEVEL_3 devices, CameraX VideoCapture + ImageAnalysis can coexist. Check `CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL` at runtime. If LEVEL_3: use CameraX for simpler API. Otherwise: Camera2.

### FPS Configuration

- **60fps target**: Set `CONTROL_AE_TARGET_FPS_RANGE = Range(60, 60)` via Camera2 `CaptureRequest.Builder`
- **Check support**: Query `CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES` from CameraCharacteristics
- **30fps fallback**: If 60fps not in available ranges, fall back to 30fps and warn user
- **Post-recording verification**: Use `MediaExtractor` to verify declared FPS matches actual frame count

### Video Stabilization

**Deliberately disabled.** Video stabilization reorders/interpolates frames, corrupting per-frame timestamps. OIS also disabled. Audio recording disabled (MediaRecorder adds extra frames for AV sync).

## BLE Connection

### WT901 Protocol (Revised)

**Key finding (H2):** WT901 provides **absolute chip time** (registers 0x30-0x33: YY, MM, DD, HH, MM, SS, msL, msH), NOT `relative_timestamp_ms`. The time output packet (flag 0x50) contains this absolute timestamp.

**BLE packet format** (per WT901BLECL datasheet):
- Header: `0x55`
- Flag byte: type indicator
- Payload: 8 data bytes (4 registers × 2 bytes each)
- Checksum: 1 byte
- Total: **11 bytes per packet type**
- Default MTU: 20 bytes (BLE 4.0). Request `requestMtu(512)` after connect.

**Packet types we need** (minimal set to reduce bandwidth):
- `0x51`: Acceleration (ax, ay, az) — 11 bytes
- `0x52`: Angular velocity (gx, gy, gz) — 11 bytes
- `0x59`: Quaternion (qw, qx, qy, qz) — 11 bytes
- `0x50`: Time output (YY, MM, DD, HH, MM, SS, msL, msH) — 11 bytes (periodic, not per-sample)

**Total per sample**: 3 packets × 11 bytes = 33 bytes at 100Hz = 3300 bytes/sec per sensor.
**2 sensors simultaneously**: 6600 bytes/sec — feasible with HIGH priority BLE connection.

**Wt901Commander must:**
1. Configure output to only send 0x51 + 0x52 + 0x59 (disable unnecessary: 0x53 angle, 0x54 magnetic)
2. Set output rate to 100Hz
3. Enable periodic time output (0x50) every ~30 seconds for drift calibration

### Connection Flow

1. `BleScanScreen` → scan for WT901 devices
2. User selects LEFT sensor → connect → `requestMtu(512)` → `requestConnectionPriority(HIGH)` → service discovery → subscribe to IMU characteristic notify
3. User selects RIGHT sensor → same steps
4. `Wt901Parser`: raw BLE bytes → assemble multi-packet frames → `ImuSample(acc, gyro, quat, chipTimeMs)`
5. Connected state persisted in `BleRepository`
6. Re-request `CONNECTION_PRIORITY_HIGH` every 30 seconds

### BLE Processing Pipeline

**Critical (H4 findings):** Android BLE callbacks arrive on Binder threads with batch behavior. Must minimize work in callback.

```
onCharacteristicChanged():
  1. val bytes = characteristic.getValue().copyOf()  // IMMEDIATE copy
  2. val arrivalNs = SystemClock.elapsedRealtimeNanos()  // monotonic
  3. handlerThread.handler.post { Wt901Parser.parse(bytes, arrivalNs) }
  4. return  // free Binder thread immediately
```

**Dedicated HandlerThread** (`BleHandlerThread`) for all BLE processing:
- Parses WT901 packets
- Groups multi-packet frames (0x51 + 0x52 + 0x59 = one IMU sample)
- Computes Android-aligned timestamp
- Writes to display buffer + disk stream

## Clock Synchronization

### Strategy: Median Offset + Periodic Resync

**Original assumption (H4 FALSIFIED):** Single offset-at-start sufficient. **Reality:** BLE notify jitter ±5-15ms, thermal throttle spikes ±30ms. Periodic resync required.

### Step 1: Initial Offset (Median of First 20 Packets)

```
For first 20 BLE packets from each sensor:
  arrivalNs = SystemClock.elapsedRealtimeNanos()
  chipTimeMs = WT901 time output (0x50) or accumulated sample timestamps
  offsets.add(arrivalNs - (chipTimeMs * 1_000_000L))

offset = median(offsets)  // reduces jitter from ~10ms to ~2-3ms
```

### Step 2: Periodic Resync (Every 30 seconds)

```
Every 30 seconds during recording:
  Send WT901 "read register" command for 0x30-0x33 (chip time)
  Compare with current elapsedRealtimeNanos()
  Update offset = exponential_moving_average(old_offset, new_offset, alpha=0.3)

This compensates for:
  - Sensor crystal oscillator drift (20-50 ppm = 6-30ms over 10 min)
  - Android BLE stack connection parameter changes
  - Thermal-induced clock rate changes
```

### Step 3: All Timestamps in CLOCK_BOOTTIME

```
Camera frame: image.timestamp = CLOCK_BOOTTIME (from ImageReader)
IMU sample: androidNs = (chipTimeMs * 1_000_000L) + offset
Calibration event: SystemClock.elapsedRealtimeNanos()

All share same clock domain. No post-hoc alignment.
```

### Expected Sync Accuracy

| Scenario | Error |
|---|---|
| Initial offset (median of 20) | ±2-3ms |
| After 10 min with resync | ±5ms |
| Worst case (thermal spike) | ±30ms |

## Recording Flow

### Start

1. `StartRecordingUseCase`:
   - Start Camera2 `CameraCaptureSession` with MediaRecorder + ImageReader → MP4 file + frame_timestamps.csv
   - Start `ImuStreamWriter` (open `BufferedOutputStream` for each sensor's .binpb file)
   - Start BLE streaming via `Wt901Commander.start()` on both sensors
   - Record `sessionStartNs = elapsedRealtimeNanos()`
   - Start Foreground Service (wake lock + notification, type `connectedDevice|camera`)
   - Start periodic resync timer (30s interval)

### During Recording

- Camera2 → MP4 on disk (hardware encoder)
- FrameTimestampTracker → `frame_timestamps.csv` on disk (SingleThreadExecutor)
- BLE (L+R) → `BleHandlerThread` → `ImuStreamWriter.writeDelimitedTo(sample)` → `.binpb` on disk
- Display buffer: `ArrayRingBuffer<ImuSample>(60_000)` (~3.6MB) for UI (10 seconds at 100Hz × 2 sensors)
- RecordingScreen HUD: duration, FPS, IMU sample rate, sensor battery, storage remaining

### IMU Disk Writing (Incremental Streaming)

**Revised (H3+H6 FALSIFIED):** No giant in-memory buffer. No single IMUStream message.

```kotlin
// Per-sample protobuf streaming to disk during recording
val fileOut = BufferedOutputStream(FileOutputStream(file))
// On each IMU sample:
sample.toProto().writeDelimitedTo(fileOut)  // ~60 bytes per write

// On stop:
fileOut.flush()
fileOut.close()
// File is immediately upload-ready — no serialization step
```

**Benefits:**
- In-memory footprint: ~3.6MB (display buffer only) vs ~67MB (old design)
- Peak memory during recording: minimal — no giant protobuf allocation
- Safe on 4GB devices
- Upload-ready immediately on stop

### Stop

1. `StopRecordingUseCase`:
   - Stop Camera2 recording (flush MP4)
   - Stop ImageReader (close frame_timestamps.csv)
   - Stop BLE streaming on both sensors
   - Flush/close .binpb files
   - Build `manifest.json`
   - Verify video FPS via `MediaExtractor`
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
├── capture_20260509_143000_left.binpb    # Delimited protobuf IMUSample stream
├── capture_20260509_143000_right.binpb   # Delimited protobuf IMUSample stream
├── capture_20260509_143000_frames.csv    # frame_index,timestamp_ns
└── capture_20260509_143000.json          # Manifest v2.0
```

**Note on .binpb format:** Each file contains a stream of length-delimited `IMUSample` messages (via `writeDelimitedTo`). Reader must use `IMUSample.parseDelimitedFrom()` to iterate. This replaces the single `IMUStream` wrapper (protobuf recommends against messages >1MB).

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
    "actual_fps_verified": true,
    "frame_timestamps_file": "capture_20260509_143000_frames.csv"
  },
  "imu": {
    "left": {
      "filename": "capture_20260509_143000_left.binpb",
      "format": "delimited_imu_sample",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-XXXX",
      "clock_offset_ns": 12345,
      "resync_intervals_s": 30
    },
    "right": {
      "filename": "capture_20260509_143000_right.binpb",
      "format": "delimited_imu_sample",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-YYYY",
      "clock_offset_ns": 67890,
      "resync_intervals_s": 30
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
   - `PUT <presigned_url>` for each: `.mp4`, `_left.binpb`, `_right.binpb`, `_frames.csv`, `.json`
   - Collect R2 keys from upload responses

2. **Create session**:
   - `POST /api/v1/sessions` with `video_key`, `imu_left_key`, `imu_right_key`, `manifest_key`

The ZIP is a local export format. Upload sends individual files to match the backend's existing presigned URL flow.

## Foreground Service

### Android 14+ Requirements

```xml
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CAMERA" />

<service
    android:name=".SensorRecordingService"
    android:foregroundServiceType="connectedDevice|camera"
    android:exported="false" />
```

Runtime prerequisites: `BLUETOOTH_CONNECT` + `CAMERA` permissions before `startForeground()`.

## Error Handling

| Scenario | Handling |
|---|---|
| BLE disconnect during recording | Foreground Service + auto-reconnect (3 attempts, 1s interval). If all fail: stop recording, mark session `incomplete` |
| Camera permission denied | `PermissionScreen` → request, block navigation until granted |
| 1080p@60fps unsupported | Check `CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES`. Fallback to 30fps → UI warning |
| Encoder drops frames at 60fps | Post-recording FPS verification via `MediaExtractor`. Flag if actual < declared |
| Storage full | Pre-flight check: minimum 500MB free. If insufficient during recording: stop + warn |
| App killed during recording | Foreground Service + persistent notification. On restart: check incomplete sessions, offer export |
| Sensor not found in scan | Show "No WT901 found. Make sure sensor is powered on." with retry button |
| BLE notification drops | Monitor sequential timestamps. If gap > 50ms detected: log warning in manifest |

## UI Screens

1. **BleScanScreen**: Scan for WT901 devices, assign LEFT/RIGHT, show connection status + battery
2. **CalibrationScreen**: 10s countdown, movement detection feedback, quaternion visualization
3. **CameraPreviewScreen**: Live camera preview with record button, settings (resolution, FPS), hardware level indicator
4. **RecordingScreen**: Active recording HUD — duration, FPS, IMU rate, battery indicators, sync accuracy, stop button
5. **ExportScreen**: Session list, ZIP generation progress, upload to R2 progress

## Protobuf Schema

```protobuf
syntax = "proto3";

message IMUSample {
  uint64 timestamp_ns = 1;        // CLOCK_BOOTTIME nanoseconds (was relative_timestamp_ms)
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

// IMUStream wrapper NOT used for file format.
// Files contain delimited IMUSample messages (writeDelimitedTo/parseDelimitedFrom).
// IMUStream kept for backward compat with backend if needed.
message IMUStream {
  repeated IMUSample samples = 1;
}
```

**Breaking change from Flutter proto:** `relative_timestamp_ms` → `timestamp_ns` (field 1 type changed from uint64 ms to uint64 ns). Field number unchanged (1). Backend protobuf parser must update to expect nanosecond timestamps.

## Key Decisions (Revised)

| Decision | Choice | Why |
|---|---|---|
| Camera API | Camera2 (primary), CameraX (LEVEL_3) | CameraX triple-use-case needs LEVEL_3; Camera2 + ImageReader works on LEGACY+ |
| Clock sync | Median offset + periodic resync | BLE jitter ±5-15ms falsifies single-offset; drift 6-30ms/10min needs correction |
| WT901 timestamp | Absolute chip time, not relative | WT901 has no relative_timestamp_ms; provides absolute time via 0x50 packet |
| IMU storage | Incremental writeDelimitedTo() to disk | 67MB in-memory buffer falsified; protobuf >1MB messages warned against |
| Display buffer | 60K samples (10s, 3.6MB) ring buffer | Safe on all devices; supports real-time UI |
| IMU file format | Delimited IMUSample stream | Avoids giant IMUStream serialization; upload-ready on stop |
| BLE processing | Dedicated HandlerThread + immediate byte copy | Binder thread batching; characteristic value reuse race condition |
| FGS type | connectedDevice\|camera | Android 14+ requirement for BLE + camera in foreground |
| FPS config | Camera2 AE_TARGET_FPS_RANGE | QualitySelector only controls resolution; FPS is separate Camera2 setting |
| FPS verification | Post-recording MediaExtractor | No CameraX/RecordingStats API for actual FPS |

## Out of Scope (MVP)

- Video stabilization (deliberately disabled — corrupts timestamps)
- Audio recording (MediaRecorder adds extra frames for AV sync)
- Multi-phone sync (RecSync / SoftwareSync)
- Real-time IMU visualization on camera preview
- Automatic cloud upload without user action
- Room DB for IMU buffer (incremental disk writes replace this)
- IMUStream single-message protobuf (replaced by delimited streaming)

## Hypothesis Verification Log

| ID | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | CameraX VideoCapture + ImageReader coexist | FALSIFIED | Requires LEVEL_3 device (most phones FULL/LIMITED). Google Issue #173725080 |
| H2 | WT901 relative_timestamp_ms monotonic, drift <1ms/10min | REVISED | No relative_timestamp_ms exists. Absolute chip time. Drift 6-30ms/10min (20-50ppm) |
| H3 | In-memory 67MB buffer safe on Android | FALSIFIED | Marginal on 4GB devices (192-256MB heap). LMK can kill at critical pressure |
| H4 | BLE notify latency stable (<5ms jitter) | FALSIFIED | Jitter ±5-15ms, spikes ±30ms. Android batches notifications. Thermal throttle worsens |
| H5 | CameraX QualitySelector handles 60fps | REVISED | QualitySelector = resolution only. FPS = Camera2Interop. No actual FPS API. Encoder may drop frames silently |
| H6 | Protobuf IMUStream with 600K samples serializable | FALSIFIED | Peak 66MB. Protobuf docs: "messages >1MB → alternate strategy". Use delimited streaming |
| H7 | Single Foreground Service for BLE + camera | CONFIRMED | Works with `connectedDevice\|camera` FGS type. Android 14+ requires declarations |
