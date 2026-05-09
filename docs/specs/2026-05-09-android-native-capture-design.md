# Android Native Capture App — Design Spec

**Date**: 2026-05-09
**Status**: Draft (rev 3 — peer review complete, pending user approval)
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

**Rev 3 correction (H13 REVISED):** The spec originally described 3 simultaneous Camera2 outputs (Preview + MediaRecorder + ImageReader). CDD guarantees `PRIV+PRIV+YUV` only on LIMITED/FULL devices, NOT LEGACY. LEGACY guarantees `PRIV+PRIV` (2 outputs).

**Revised architecture:** Check `isSessionConfigurationSupported()` at runtime. If 3-output session works → use Preview + MediaRecorder + ImageReader. If not → drop Preview Surface during recording, use only MediaRecorder + ImageReader (2 outputs). The user sees a frozen last frame in preview during recording on LEGACY devices.

**Rev 3 correction (H9 FALSIFIED):** `MediaRecorder.start()` has measurable latency (50-500ms per AOSP `MEDIA_RECORDER_TRACK_INFO_INITIAL_DELAY_MS`). The first video frame timestamp must be obtained via `CaptureCallback.onCaptureStarted()`, not from `elapsedRealtimeNanos()` at `start()` call.

**Rev 3 addition:** Check `SENSOR_INFO_TIMESTAMP_SOURCE`. If `REALTIME` (value 1), camera timestamps share CLOCK_BOOTTIME domain. If `UNKNOWN` (value 0), measure offset at session start.

```
Camera2 CameraCaptureSession:
  Surface 1: MediaRecorder.surface → MP4 (H.264 hardware encoder)
  Surface 2: ImageReader(YUV_420_888, maxImages=2) → onImageAvailable → image.timestamp → CSV
  [Optional] Surface 3: Preview SurfaceTexture → live view (if supported)

Start recording synchronization:
  1. MediaRecorder.start() — record t_start_called = elapsedRealtimeNanos()
  2. First onCaptureStarted() callback → t_first_frame = callback.timestamp
  3. Video-to-IMU alignment: t_first_frame is the video start reference
  4. Check SENSOR_INFO_TIMESTAMP_SOURCE:
     - REALTIME: camera timestamps already in CLOCK_BOOTTIME domain
     - UNKNOWN: measure offset once per session

ImageReader callback:
  - image.timestamp is in CLOCK_BOOTTIME domain (same as elapsedRealtimeNanos)
  - Use acquireLatestImage() for resilience (auto-drops stale frames)
  - Write to frame_timestamps.csv: frame_index, timestamp_ns
  - DO NOT process image pixels — only extract timestamp, close image immediately
  - Use SingleThreadExecutor for CSV writes (avoid blocking camera callback)
```

### CameraX Fallback (LEVEL_3 devices)

On LEVEL_3 devices, CameraX VideoCapture + ImageAnalysis + Preview can coexist (3 use cases). Check `CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL` at runtime. If LEVEL_3: use CameraX for simpler API with live Preview during recording. Otherwise: Camera2 (Preview may freeze during recording on LEGACY devices).

### FPS Configuration

- **60fps target**: Set `CONTROL_AE_TARGET_FPS_RANGE = Range(60, 60)` via Camera2 `CaptureRequest.Builder`
- **Check support**: Query `CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES` from CameraCharacteristics
- **30fps fallback**: If 60fps not in available ranges, fall back to 30fps and warn user
- **Post-recording verification**: Use `MediaExtractor` to verify declared FPS matches actual frame count

### Video Stabilization

**Deliberately disabled.** Video stabilization reorders/interpolates frames, corrupting per-frame timestamps. OIS also disabled. Audio recording disabled (MediaRecorder adds extra frames for AV sync).

## BLE Connection

### WT901 Protocol (Revised rev 3)

**Key finding (H2):** WT901 provides **absolute chip time** (registers 0x30-0x33: YY, MM, DD, HH, MM, SS, msL, msH), NOT `relative_timestamp_ms`. The time output packet (flag 0x50) contains this absolute timestamp.

**Rev 3 finding (H8 FALSIFIED):** WT901BLECL default BLE mode sends a **combined 0x61 frame** (20 bytes), NOT three separate 0x51/0x52/0x59 packets. The 0x61 frame contains acceleration + angular velocity + Euler angles in one BLE notification. Quaternion (0x59) is NOT included in the combined frame.

**Rev 3 correction (H16 CONFIRMED):** Writing OutputContent register (0x02) **switches** the sensor from 0x61 combined mode to individual frame mode — they do NOT coexist. There is NO combined frame that includes quaternions (0x71 is a query-response frame, not a streaming frame).

**Rev 3 finding (H12 FALSIFIED):** `requestMtu(512)` is unnecessary. WT901 uses nRF52832 (max MTU 247). The firmware always sends exactly 20 bytes per notification regardless of negotiated MTU. Use default MTU (23). Do NOT request MTU negotiation.

**BLE Service UUIDs** (confirmed from multiple SDK implementations):
- Service: `0000FFE5-0000-1000-8000-00805F9A34FB`
- Read/Notify: `0000FFE4-0000-1000-8000-00805F9A34FB`
- Write (commands): `0000FFE9-0000-1000-8000-00805F9A34FB`

**BLE packet format** — two modes:

**Mode A: Combined 0x61 frame (default, 20 bytes, NO checksum):**
```
byte[0]  = 0x55 (header)
byte[1]  = 0x61 (type: combined acceleration + angular velocity + angle)
bytes[2-3]  = ax (int16 LE, signed two's complement, -32768..32767 → ±16g)
bytes[4-5]  = ay (int16 LE, signed)
bytes[6-7]  = az (int16 LE, signed)
bytes[8-9]  = gx (int16 LE, signed, -32768..32767 → ±2000°/s)
bytes[10-11] = gy (int16 LE, signed)
bytes[12-13] = gz (int16 LE, signed)
bytes[14-15] = roll (int16 LE, signed, -32768..32767 → ±180°)
bytes[16-17] = pitch (int16 LE, signed)
bytes[18-19] = yaw (int16 LE, signed)
```

> **WARNING:** The 0x61 combined frame does NOT contain quaternion data. Quaternion output requires switching to Mode B (individual frames) via OutputContent register. There is no combined frame with quaternions — the 0x71 frame is a query-response only, not a streaming frame.

**Mode B: Individual frames (11 bytes each, with checksum):**
```
0x51 (Acceleration): [0x55][0x51][axL][axH][ayL][ayH][azL][azH][tL][tH][chk]
  — ax/ay/az: int16 LE signed two's complement (-32768..32767), scale = value/32768 * 16 (g)
  — t: temperature int16 LE, scale = value/100 (°C) — NOT a 4th acceleration axis
0x52 (Angular Velocity): [0x55][0x52][gxL][gxH][gyL][gyH][gzL][gzH][tL][tH][chk]
  — gx/gy/gz: int16 LE signed two's complement, scale = value/32768 * 2000 (°/s)
  — t: temperature (same)
0x59 (Quaternion): [0x55][0x59][qwL][qwH][qxL][qxH][qyL][qyH][qzL][qzH][chk]
  — qw/qx/qy/qz: int16 LE signed two's complement, scale = value/32768
0x50 (Time): [0x55][0x50][YY][MM][DD][HH][MM][SS][msL][msH][chk]
  — Absolute chip time (year, month, day, hour, minute, second, millisecond)
  — NOT streamed at 100Hz; queried on-demand via register read for clock sync
```

**Selected approach:** Use **Mode B** (individual frames) to get quaternions:
- Enable 0x51 (acceleration) + 0x52 (angular velocity) + 0x59 (quaternion) via OutputContent register
- 0x50 (time) queried on-demand for clock sync (register read), not streamed at 100Hz
- Disable 0x53 (Euler angles) + 0x54 (magnetic field) — not needed (Euler derivable from quaternion)
- **Partial frame buffering required**: one BLE notification (20 bytes) may contain parts of two 11-byte frames. Parser must handle frame boundaries across notifications.

**Total per sample**: 3 packets × 11 bytes = 33 bytes at 100Hz = 3300 bytes/sec per sensor.
**2 sensors simultaneously**: 6600 bytes/sec — feasible with HIGH priority BLE connection (conservative ~8000 bytes/sec throughput).

**Wt901Commander command protocol:**

All commands are 5 bytes: `[0xFF, 0xAA, <command_or_register>, <param1>, <param2>]`
- Byte 3 = register address for write commands (e.g., `0x02` = OutputContent, `0x03` = OutputRate)
- Byte 3 = `0x27` (read-command opcode) for register reads, byte 4 = register address to query

Pre-configuration unlock: `[0xFF, 0xAA, 0x69, 0x88, 0xB5]`

1. **Unlock** → `[0xFF, 0xAA, 0x69, 0x88, 0xB5]`
2. **Enable output content** (register 0x02): 0x51+0x52+0x59 = bitmask 0x0046 (Acc=0x02, Gyro=0x04, Quat=0x40)
   → `[0xFF, 0xAA, 0x02, 0x46, 0x00]`
3. **Set output rate** 100Hz (register 0x03, value 0x09):
   → `[0xFF, 0xAA, 0x03, 0x09, 0x00]`
4. **Save configuration** → `[0xFF, 0xAA, 0x00, 0x00, 0x00]`

**0x50 (time) NOT enabled for streaming** — queried on-demand via register read (`[0xFF, 0xAA, 0x27, 0x30, 0x00]`) for periodic clock sync. This avoids adding 1100 bytes/sec of time data that's only needed every 30 seconds.

No ACK — fire-and-forget. Can verify via register read (`[0xFF, 0xAA, 0x27, <reg>, 0x00]`, response via 0x71 notification).

### Connection Flow

1. `BleScanScreen` → scan for WT901 devices
2. User selects LEFT sensor → connect → `requestConnectionPriority(HIGH)` → service discovery → subscribe to IMU characteristic notify (FFE4)
3. User selects RIGHT sensor → same steps
4. `Wt901Parser`: raw BLE bytes → parse individual frames by type byte → `ImuSample(acc, gyro, quat, chipTimeMs)`
5. Connected state persisted in `BleRepository`
6. Re-request `CONNECTION_PRIORITY_HIGH` every 30 seconds
7. **Do NOT request MTU negotiation** — default MTU 23 is sufficient (WT901 always sends 20-byte notifications)

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
- **Partial frame buffering**: 11-byte frames may span two BLE notifications (20 bytes). Parser accumulates bytes, detects frame boundaries by 0x55 header byte, validates checksum before processing
- Parses individual WT901 frames by type byte (0x51, 0x52, 0x59)
- **No strict ordering assumed** — each frame processed independently
- Groups into complete IMU samples: when acc(0x51) + gyro(0x52) + quat(0x59) all received for same sample cycle → emit ImuSample
- Uses per-sensor sample state machine (expecting 0x51 first after output cycle, then 0x52, then 0x59, with timeout fallback if order differs)
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
   - **Rev 3 (H9):** Record `t_start_called = SystemClock.elapsedRealtimeNanos()` at `MediaRecorder.start()` call
   - **Rev 3 (H9):** Wait for first `CaptureCallback.onCaptureStarted()` → `t_first_frame = callback.timestamp` = exact video start
   - Check `SENSOR_INFO_TIMESTAMP_SOURCE`:
     - `REALTIME` (1): camera timestamps already in CLOCK_BOOTTIME → direct alignment
     - `UNKNOWN` (0): measure offset once, store in manifest
   - Start `ImuStreamWriter` (open `BufferedOutputStream` for each sensor's .binpb file)
   - Start BLE streaming via `Wt901Commander.start()` on both sensors
   - Record `sessionStartNs = t_first_frame` (NOT `elapsedRealtimeNanos()` at start call)
   - Start Foreground Service (wake lock + notification, type `connectedDevice|camera`)
   - Start periodic resync timer (30s interval)

### During Recording

- Camera2 → MP4 on disk (hardware encoder)
- FrameTimestampTracker → `frame_timestamps.csv` on disk (SingleThreadExecutor)
- BLE (L+R) → `BleHandlerThread` → `ImuStreamWriter.writeDelimitedTo(sample)` → `.binpb` on disk
- Display buffer: `ArrayRingBuffer<ImuSample>(60_000)` (~3.6MB) for UI (10 minutes at 100Hz per sensor, or 5 minutes both sensors)
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
   - Build `manifest.json` (include `t_first_frame_ns`, `timestamp_source`, `video_start_delay_ms`)
   - **Manifest field semantics:** `t0_ns` = `first_frame_ns` = session start time (the first video frame timestamp from `onCaptureStarted()`). `video_start_delay_ms` = `first_frame_ns - t_start_called_ns` (latency between `MediaRecorder.start()` call and actual first frame)
   - Verify video FPS via `MediaExtractor`
   - Create `CaptureSession` with all file references
   - Stop Foreground Service

## Calibration

Sensors are **on the athlete's feet**, athlete stands still.

### Flow

1. `CalibrationScreen`: "Встаньте ровно, не двигайтесь. Датчики на ногах."
2. Collect 10 seconds of quaternion data (~1000 samples at 100Hz) from each sensor
3. Filter: discard samples where `|angular_velocity| > 5°/s` (movement detected — threshold from WT901 datasheet static accuracy spec)
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
├── capture_20260509_143000_left.binpb    # Delimited protobuf IMURecord stream (IMUSample | IMUGap)
├── capture_20260509_143000_right.binpb   # Delimited protobuf IMURecord stream (IMUSample | IMUGap)
├── capture_20260509_143000_frames.csv    # frame_index,timestamp_ns
└── capture_20260509_143000.json          # Manifest v2.0
```

**Note on .binpb format:** Each file contains a stream of length-delimited `IMURecord` messages (via `writeDelimitedTo`). `IMURecord` is a wrapper with `oneof record` containing either `IMUSample` or `IMUGap`. Readers dispatch by the wrapper's field tag: field 1 (`0x0A`) = IMUSample, field 2 (`0x12`) = IMUGap. This replaces the tag-based dispatch on inner message fields (which was broken — both IMUSample.timestamp_ns and IMUGap.last_sample_ns produce the same tag byte `0x08`).

### Manifest v2.0

```json
{
  "version": "2.0",
  "created_at": "2026-05-09T14:30:00Z",
  "t0_ns": 12345678901200,
  "duration_ms": 5000,
  "video": {
    "filename": "capture_20260509_143000.mp4",
    "fps": 60,
    "width": 1920,
    "height": 1080,
    "actual_fps_verified": true,
    "frame_timestamps_file": "capture_20260509_143000_frames.csv",
    "timestamp_source": "REALTIME",
    "video_start_delay_ms": 120,
    "first_frame_ns": 12345678901200
  },
  "imu": {
    "left": {
      "filename": "capture_20260509_143000_left.binpb",
      "format": "delimited_imu_record",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-XXXX",
      "clock_offset_ns": 12345,
      "resync_intervals_s": 30,
      "reconnect_count": 0
    },
    "right": {
      "filename": "capture_20260509_143000_right.binpb",
      "format": "delimited_imu_record",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-YYYY",
      "clock_offset_ns": 67890,
      "resync_intervals_s": 30,
      "reconnect_count": 1
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

**Compatibility:** `foregroundServiceType` attribute is required on API 34+, ignored on earlier versions. Manifest declaration is sufficient — no runtime version check needed.

### Screen Rotation During Recording (H14 FALSIFIED)

**Rev 3 addition.** The preview Surface is destroyed when the Activity is recreated on rotation. All reference apps (OpenCamera-Sensors, VIRec, VideoIMUCapture-Android) use `configChanges` to prevent Activity recreation.

```xml
<activity
    android:name=".MainActivity"
    android:configChanges="orientation|screenSize|keyboardHidden"
    android:screenOrientation="portrait" />
```

The Foreground Service holds the recording state (MediaRecorder, BLE connections, camera session). The recording Surface (from MediaRecorder) is NOT tied to Activity lifecycle. Only the preview Surface must be re-bound on orientation change — handled in `onConfigurationChanged()`.

### BLE Disconnect/Reconnect During Recording (H15 REVISED)

**Rev 3 addition.** On BLE disconnect, the reconnect sequence MUST re-subscribe to notifications:

1. `onConnectionStateChange(STATE_CONNECTED)`
2. `gatt.discoverServices()`
3. `gatt.setCharacteristicNotification(characteristic, true)` — MANDATORY
4. Write CCCD descriptor (`ENABLE_NOTIFICATION_VALUE`)
5. Only then `onCharacteristicChanged()` resumes

**Gap markers in protobuf stream:** When reconnect occurs during recording, insert an `IMUGap` message to mark the discontinuity. This prevents the backend from interpolating across a gap (which would corrupt DTW alignment, CoM integration, and biomechanical metrics).

```protobuf
message IMUGap {
  uint64 last_sample_ns = 1;     // timestamp of last sample before disconnect
  uint64 first_sample_ns = 2;    // timestamp of first sample after reconnect
  uint32 reconnect_seq = 3;     // reconnect sequence number (for offset tracking)
}
```

The `.binpb` file becomes a mixed stream of `IMUSample` and `IMUGap` messages. Readers must dispatch by message type.

## Error Handling

| Scenario | Handling |
|---|---|
| BLE disconnect during recording | Foreground Service + auto-reconnect (3 attempts, 1s interval). On each reconnect: re-subscribe to FFE4 notify, insert `IMUGap` marker, compute new offset. If all attempts fail: stop recording, mark session `incomplete`. **Both sensors disconnecting simultaneously:** serialize reconnection (left first, then right) — Android BLE stack limits concurrent GATT operations. |
| Camera permission denied | `PermissionScreen` → request, block navigation until granted |
| 1080p@60fps unsupported | Check `CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES`. Fallback to 30fps → UI warning |
| Encoder drops frames at 60fps | Post-recording FPS verification via `MediaExtractor`. Flag if actual < declared |
| Storage full | Pre-flight check: minimum 500MB free. If insufficient during recording: stop + warn |
| App killed during recording | Foreground Service + persistent notification. On restart: check incomplete sessions, offer export |
| Sensor not found in scan | Show "No WT901 found. Make sure sensor is powered on." with retry button |
| BLE notification drops | Monitor sequential timestamps. If gap > 50ms detected: log warning in manifest |
| Camera3 outputs not supported | Check `isSessionConfigurationSupported()` before recording. If 3-output fails: drop Preview Surface, use 2-output session (MediaRecorder + ImageReader only). User sees frozen frame during recording on LEGACY |
| `SENSOR_INFO_TIMESTAMP_SOURCE` = UNKNOWN | Measure camera-to-CLOCK_BOOTTIME offset at session start. Record offset in manifest. Apply correction to all frame timestamps |
| Duplicate BLE packets after reconnect | Discard packets with `chip_time_ns <= lastReceivedChipTimeNs` per sensor |
| Screen rotation during recording | `configChanges` prevents Activity recreation. Foreground Service holds recording state. `onConfigurationChanged()` updates preview layout |

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

// Rev 3 addition: gap marker for BLE disconnect/reconnect events.
// Inserted into .binpb stream when BLE reconnects during recording.
// Prevents backend from interpolating across data gaps.
message IMUGap {
  uint64 last_sample_ns = 1;     // timestamp of last sample before disconnect
  uint64 first_sample_ns = 2;    // timestamp of first sample after reconnect
  uint32 reconnect_seq = 3;      // reconnect sequence number (for offset tracking)
}

// The .binpb file is a stream of delimited IMURecord messages.
// Each IMURecord wraps either an IMUSample or IMUGap via oneof.
// Writers: sample.toRecord().writeDelimitedTo(stream)
// Readers: IMURecord.parseDelimitedFrom(stream) → dispatch on oneof field
message IMURecord {
  oneof record {
    IMUSample sample = 1;
    IMUGap gap = 2;
  }
}
```

**Breaking changes from Flutter proto:**
1. `relative_timestamp_ms` → `timestamp_ns` (field 1 type changed from uint64 ms to uint64 ns). Field number unchanged (1). Backend protobuf parser must update to expect nanosecond timestamps.
2. File format changed from `IMUStream` single message to delimited `IMURecord` stream. Backend must parse `IMURecord` wrapper and dispatch via `oneof record` field.

## Key Decisions (Revised)

| Decision | Choice | Why |
|---|---|---|
| Camera API | Camera2 (primary), CameraX (LEVEL_3) | CameraX triple-use-case needs LEVEL_3; Camera2 + ImageReader works on LEGACY+ |
| Camera outputs | 2-output (MediaRecorder + ImageReader) with optional Preview | CDD guarantees `PRIV+PRIV+YUV` only on LIMITED/FULL. LEGACY: max 2 outputs. `isSessionConfigurationSupported()` check at runtime |
| Clock sync | Median offset + periodic resync | BLE jitter ±5-15ms falsifies single-offset; drift 6-30ms/10min needs correction |
| Video start sync | `onCaptureStarted()` timestamp | MediaRecorder.start() has 50-500ms latency. First frame timestamp from callback is the real t0 |
| Camera timestamp source | Check `SENSOR_INFO_TIMESTAMP_SOURCE` | REALTIME = same CLOCK_BOOTTIME as IMU. UNKNOWN = measure offset once |
| WT901 timestamp | Absolute chip time, not relative | WT901 has no relative_timestamp_ms; provides absolute time via 0x50 packet |
| WT901 output mode | Individual frames (0x51+0x52+0x59) via OutputContent 0x0046 | Writing OutputContent register SWITCHES from 0x61 combined to individual frames (they do NOT coexist). No combined frame with quaternion exists |
| WT901 BLE commands | Write characteristic FFE9, no ACK | Protocol: `FF AA <reg> <valL> <valH>`. Unlock required before config. No ACK. Time queried on-demand via register read (0x27) |
| Partial frame buffering | Required in parser | 11-byte frames may span 20-byte BLE notifications. Must accumulate bytes, detect 0x55 header boundaries, validate checksum |
| MTU negotiation | Do NOT request MTU, use default 23 | WT901 always sends 20-byte notifications. nRF52832 max 247. Higher MTU = zero benefit |
| IMU storage | Incremental writeDelimitedTo() to disk | 67MB in-memory buffer falsified; protobuf >1MB messages warned against |
| Display buffer | 60K samples (10s, 3.6MB) ring buffer | Safe on all devices; supports real-time UI |
| IMU file format | Delimited `IMURecord` stream (`oneof` sample/gap) | Tag-based dispatch on inner fields was broken (both produce `0x08`). `IMURecord` wrapper with `oneof` is the standard protobuf pattern for mixed-type streams |
| BLE processing | Dedicated HandlerThread + immediate byte copy | Binder thread batching; characteristic value reuse race condition |
| BLE reconnect | Re-subscribe to FFE4 + CCCD, insert IMUGap | Must re-subscribe on reconnect. Duplicates/out-of-order possible |
| Screen rotation | `configChanges` prevents Activity recreation | Surface destroyed on rotation. All ref apps use configChanges. Service holds recording state |
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
- IMUStream single-message protobuf (replaced by IMURecord delimited streaming)
- MTU negotiation (WT901 always sends 20-byte notifications; default MTU 23 sufficient)
- Combined 0x61 frame parsing (OutputContent register switches to individual frames; 0x61 and individual frames do NOT coexist)

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
| H8 | WT901 packets 0x51→0x52→0x59 arrive sequentially | FALSIFIED | Default BLE = combined 0x61 frame (20 bytes). Individual frames have no ordering guarantee. No frame-complete marker |
| H9 | MediaRecorder.start() ≈ instantaneous | FALSIFIED | AOSP defines `MEDIA_RECORDER_TRACK_INFO_INITIAL_DELAY_MS` (info code 1007). Real: 50-500ms. Must use `onCaptureStarted()` for video t0 |
| H10 | ImageReader maxImages=2 sufficient for timestamps | CONFIRMED | YUV_420_888 = non-stalling (drops, not stalls). `acquireLatestImage()` + immediate close = safe |
| H11 | WT901 config via BLE write trivially implementable | CONFIRMED | UUIDs: FFE5/FFE4/FFE9. Commands: `FF AA <reg> <valL> <valH>`. Unlock required. No ACK |
| H12 | requestMtu(512) supported, no fallback needed | FALSIFIED | nRF52832 max MTU=247. WT901 always sends 20-byte notifications. Default MTU 23 sufficient |
| H13 | Preview + MediaRecorder + ImageReader = 3 outputs on LEGACY+ | REVISED | CDD guarantees `PRIV+PRIV+YUV` only on LIMITED/FULL. LEGACY: max 2 outputs. Use `isSessionConfigurationSupported()` |
| H14 | Foreground Service holds camera through rotation | FALSIFIED | Surface destroyed on Activity recreation. All ref apps use `configChanges`. Service holds recording, not preview |
| H15 | No gap markers needed for BLE disconnect | REVISED | Must re-subscribe on reconnect. Duplicates/out-of-order possible. `IMUGap` protobuf message required |
| H16 | Enabling OutputContent 0x59 makes 0x61 and individual frames coexist | CONFIRMED FALSE | Writing register 0x02 SWITCHES from 0x61 combined to individual frames. No combined frame with quaternion exists. 0x71 is query-response only |
