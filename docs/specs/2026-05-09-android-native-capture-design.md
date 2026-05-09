# Android Native Capture App — Design Spec

**Date**: 2026-05-09
**Status**: Draft (rev 5 — fourth scientific review complete, H25-H28 resolved)
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

**Configuration sequence** (run once after connect, before recording):
1. **Unlock** → `[0xFF, 0xAA, 0x69, 0x88, 0xB5]`
2. *(wait 100ms)*
3. **Enable output content** (register 0x02): 0x51+0x52+0x59 = bitmask 0x0046 (Acc=0x02, Gyro=0x04, Quat=0x40)
   → `[0xFF, 0xAA, 0x02, 0x46, 0x00]`
4. *(wait 100ms)*
5. **Set output rate** 100Hz (register 0x03, value 0x09):
   → `[0xFF, 0xAA, 0x03, 0x09, 0x00]`
6. *(wait 100ms)*
7. **Save configuration** → `[0xFF, 0xAA, 0x00, 0x00, 0x00]`
8. *(wait 500ms for EEPROM write + output mode switch)*

**Start streaming** (send when recording begins, requires Unlock):
9. **Unlock** → `[0xFF, 0xAA, 0x69, 0x88, 0xB5]`
10. *(wait 50ms)*
11. **Set output content to active** (register 0x02, re-send 0x0046):
    → `[0xFF, 0xAA, 0x02, 0x46, 0x00]`
12. *(wait 100ms)*
13. **Save configuration** → `[0xFF, 0xAA, 0x00, 0x00, 0x00]`
14. *(wait 500ms)* — sensor switches from 0x61 combined to individual frames, 100Hz output starts

**Stop streaming** (send when recording ends, requires Unlock):
15. **Unlock** → `[0xFF, 0xAA, 0x69, 0x88, 0xB5]`
16. *(wait 50ms)*
17. **Disable all output** (register 0x02, value 0x0000):
    → `[0xFF, 0xAA, 0x02, 0x00, 0x00]`
18. *(wait 100ms)*
19. **Save configuration** → `[0xFF, 0xAA, 0x00, 0x00, 0x00]`

> **Rev 5 (H25 CONFIRMED):** Unlock must be sent before EVERY configuration write — including start/stop streaming. The 10-second configuration window expires after Save, and all official WitMotion SDKs (C, Android, C#) call Unlock before each register modification. Start streaming is 4 commands (~750ms total). Stop streaming is 4 commands (~750ms total). Register reads (0x27) do NOT need Unlock — they are not configuration writes.

> **Note:** Streaming is controlled by the OutputContent register: non-zero value = stream enabled, zero = stream disabled. After Save, the sensor begins transmitting at the configured rate. The "start" sequence re-sends OutputContent 0x0046 to ensure individual-frame mode (not default 0x61 combined mode).

**0x50 (time) NOT enabled for streaming** — queried on-demand via register read (`[0xFF, 0xAA, 0x27, 0x30, 0x00]`) for periodic clock sync. This avoids adding 1100 bytes/sec of time data that's only needed every 30 seconds.

**Rev 4 addition (H20 CONFIRMED):** Inter-command delays are required. The sensor's Unlock opens a **10-second configuration window** — all subsequent commands must complete within this window. Based on XAMLCORP C# SDK (100ms serial delays, 50ms BLE delays) and ElettraSciComp C++ SDK (5s after calibrate):
- 100ms delay between configuration commands (safe margin)
- 500ms delay after Save command (EEPROM write + output mode switch)
- GATT operations must be serialized — `BluetoothGatt.writeCharacteristic()` silently fails if another GATT operation is in progress. Use a write queue with mutual exclusion (SemaphoreSlim pattern from C# SDK)
- Use `WRITE_TYPE_NO_RESPONSE` (write without response) for FFE9 characteristic — avoids blocking GATT thread
- **P1 resolution:** `WRITE_TYPE_NO_RESPONSE` is acceptable even for configuration commands. Rationale: (1) The sensor's 10-second unlock window provides implicit confirmation — if the write fails silently, the next command in the sequence will also fail, and the sensor won't enter the expected mode (detectable via register read). (2) `WRITE_TYPE_DEFAULT` (with ACK) adds per-command latency (4-6ms BLE round-trip × 5 commands = 20-30ms extra), which eats into the 10-second window. (3) Post-configuration verification via register read (`[0xFF, 0xAA, 0x27, 0x02, 0x00]`) confirms OutputContent was set correctly. If verification fails → retry entire sequence.

No ACK — fire-and-forget. Can verify via register read (`[0xFF, 0xAA, 0x27, <reg>, 0x00]`, response via 0x71 notification).

**0x71 response format** (query-response, P1 resolution):
```
[0x55][0x71][reg][dataL][dataH][chk]  (7 bytes)
- byte[0] = 0x55 (header)
- byte[1] = 0x71 (type: register read response)
- byte[2] = register address that was queried
- bytes[3-4] = register value (int16 LE)
- byte[5] = checksum (sum of bytes[0-4] & 0xFF)
```
Used for post-configuration verification and clock sync register reads.

### Connection Flow

1. `BleScanScreen` → scan for WT901 devices (filter by ServiceUUID `0000FFE5-0000-1000-8000-00805F9A34FB` to reduce scan noise; fall back to name-prefix "WT901" if ServiceUUID filter not supported on device)
2. User selects LEFT sensor → connect → `requestConnectionPriority(HIGH)` → service discovery → subscribe to IMU characteristic notify (FFE4)
3. User selects RIGHT sensor → same steps
4. **Configure sensors** (once per connect): send Unlock → Enable OutputContent → Set Rate → Save via `Wt901Commander` (see command protocol above). This prepares the sensor for streaming but does NOT start data output yet.
5. `Wt901Parser`: raw BLE bytes → parse individual frames by type byte → bitmask sample grouping → `ImuSample(acc, gyro, quat, chipTimeMs)`
6. Connected state persisted in `BleRepository`
7. Re-request `CONNECTION_PRIORITY_HIGH` every 30 seconds
8. **Rev 4 (H21):** All GATT operations serialized via write queue — `BluetoothGatt.writeCharacteristic()` silently fails if another operation is in progress. Use `WRITE_TYPE_NO_RESPONSE` for FFE9 characteristic. Write commands can be sent during active streaming (FFE9 write and FFE4 notify are independent characteristics).
9. **Do NOT request MTU negotiation** — default MTU 23 is sufficient (WT901 always sends 20-byte notifications)

**Start streaming** (at recording start): Send Unlock → OutputContent 0x0046 → Save (steps 9-14 in command protocol, ~750ms). Data arrives on FFE4.

**Stop streaming** (at recording end): Send Unlock → OutputContent 0x0000 → Save (steps 15-19 in command protocol, ~750ms). Data stops on FFE4.

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
- **Rev 4 (H18):** The 0x55 header byte can appear in data payload. For individual frames (0x51/0x52/0x59), checksum validation rejects false 0x55 headers. Algorithm: scan for 0x55 → check if enough bytes remain for a frame → validate checksum → if invalid, advance past this 0x55 and continue scanning. The 0x61 combined frame has NO checksum — only relevant if combined mode is used (not in our architecture). Pattern from XAMLCORP `PacketParser.cs` with buffer accumulation + lock.
- Parses individual WT901 frames by type byte (0x51, 0x52, 0x59)
- **No strict ordering assumed** — each frame processed independently
- Groups into complete IMU samples: when acc(0x51) + gyro(0x52) + quat(0x59) all received for same sample cycle → emit ImuSample
- **Rev 4 (H17, revised per P0 #9):** No reference SDK implements sample grouping — all process frames independently. Our sample grouping uses a **bitmask accumulator** (NOT a sequential state machine), since H8 confirmed no ordering guarantee for individual frames:
  - **Bitmask:** Track received frame types with a bitmask: `ACC=0x01, GYRO=0x02, QUAT=0x04`. When `received_mask == 0x07` → all three present → emit `ImuSample`, reset mask and timer.
  - **Any frame type first:** No assumption about which frame type (0x51, 0x52, or 0x59) arrives first in a cycle. First frame of any type starts the 15ms timer.
  - **Duplicate handling:** If a frame type already received in current cycle (e.g., second 0x51 before 0x52 arrives), the previous incomplete cycle is dropped — increment `dropped_partial_count`, reset mask, start new cycle with current frame.
  - **Timeout:** If 15ms elapses (1.5× the 10ms expected interval at 100Hz) without completing the bitmask → incomplete cycle. Increment `dropped_partial_count`, reset mask. **Do NOT emit a partial ImuSample** (proto3 float defaults to 0.0, not NaN — partial samples would produce bogus zero values).
  - **Frame loss detection:** The bitmask directly reveals which frame types are missing at timeout. Log to manifest if desired.
  - **Rev 4 (P0 #23 resolved):** Proto3 float fields default to 0.0, not NaN. Partial IMU samples with missing fields would silently produce bogus zero values (e.g., acc_x=0 when no 0x51 received). Three approaches considered:
    1. ~~FloatValue wrappers~~ — doubles message size (wrapper per field), over-engineering for edge case
    2. ~~Separate PartialIMUSample message~~ — adds schema complexity, backend must handle yet another message type
    3. **Skip incomplete cycles + counter in manifest** (CHOSEN) — simply drop incomplete cycles, increment `dropped_partial_count` per sensor in manifest. Backend sees a gap in timestamps (detectable), not bogus zero values. Clean, minimal, no schema changes.
- Computes Android-aligned timestamp
- Writes to display buffer + disk stream

## Clock Synchronization

### Strategy: Median Offset + Periodic Resync

**Original assumption (H4 FALSIFIED):** Single offset-at-start sufficient. **Reality:** BLE notify jitter ±5-15ms, thermal throttle spikes ±30ms. Periodic resync required.

### Step 1: Initial Offset (Median of First 20 Packets)

```
For first 20 BLE packets from each sensor:
  arrivalNs = SystemClock.elapsedRealtimeNanos()
  chipTimeMs = read from WT901 time registers (0x30-0x33) via on-demand register read
  offsets.add(arrivalNs - (chipTimeMs * 1_000_000L))

offset = median(offsets)  // reduces jitter from ~10ms to ~2-3ms
```

**Rev 5 (H26 CONFIRMED):** WT901 individual frame mode (0x51/0x52/0x59) provides NO per-sample timestamp. The 11-byte frames contain only sensor data + checksum. All reference SDKs (Android, C#, Python) use arrival time only — no chip time extraction. The phrase "accumulated sample timestamps" is removed as misleading; the sensor has no sample counter. Per-sample timestamps are assigned using `elapsedRealtimeNanos()` at BLE notification arrival. Periodic 0x50 register reads (every 30s) provide drift correction against sensor crystal oscillator drift (20-50 ppm).

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

### Startup Ordering Research (H28)

**Rev 5 (H28 CONFIRMED):** Research of 3 reference apps + 2 papers confirms: **start IMU first, then camera.** Record the delay in the manifest.

**Evidence from reference apps:**

1. **OpenCamera-Sensors** (MobileRoboticsSkoltech/Skoltech): Sensors are enabled (`enableSensors()`) and `SensorManager.registerListener()` is called **before** `MediaRecorder.start()`. The `RawSensorInfo.startRecording()` opens sensor CSV writers and sets `mIsRecording = true`. IMU data flows immediately. Camera starts after, with its inherent 50-500ms latency. No explicit delay field in manifest — the timestamp CSV files implicitly contain the gap (first frame timestamp may be hundreds of ms after first sensor event).

2. **VideoIMUCapture-Android** (DavidGillsjo): The `CameraCaptureFragment.startRecording()` method orders: (1) `recordingWriter.startRecording(metaFile)` — open metadata writer, (2) `imuManager.startRecording(recordingWriter)` — set `mRecordingInertialData = true`, (3) `camera2Proxy.startRecordingCaptureResult(recordingWriter)` — start camera capture result recording, (4) `mRenderer.changeRecordingState(true)` — start video encoder. Crucially, the IMU `SensorEventCallback` is **always registered** (`imuManager.register()` is called at session start, not recording start). The `startRecording()` method just flips the `mRecordingInertialData` boolean — so IMU data is already flowing when video starts. This is the cleanest approach: sensors always active, recording flag gates data to disk.

3. **RecSync** (Skoltech, arXiv:2107.00987): Focuses on multi-phone phase alignment, not single-phone startup order. Confirms that switching from preview to video mode does NOT shift camera phase on most devices (drift < 1.2 ms/min on 47 tested phones). This means camera timestamps are stable across mode transitions.

**Evidence from papers:**

- **VersaVIS** (Tschopp et al., 2019, arXiv:1912.02469): Hardware-triggered approach — MCU triggers IMU readout and camera exposure simultaneously. Initialization requires finding corresponding sequence numbers between camera and trigger board "since a simultaneous start of the cameras and the trigger board cannot be guaranteed." Even with hardware triggers, startup synchronization is non-trivial and requires post-start alignment.

- **Aerts & Demeester (2019, ICINCO)**: Motion-based sync via particle filter. Explicitly notes "software generated timestamp is based on the internal clock of the computer and the arrival time of the recorded image" — acknowledges camera timestamp uncertainty. Does not address startup ordering.

**Startup latency analysis for our architecture:**

| Component | Action | Latency | Detectable |
|-----------|--------|---------|------------|
| Camera | `MediaRecorder.start()` → first `onCaptureStarted()` | 50-500ms | Yes: `callback.timestamp` gives exact t0 |
| BLE IMU | OutputContent 0x0046 + Save → first 0x51/0x52/0x59 notification | ~500ms (EEPROM settle) | Yes: first `onCharacteristicChanged()` arrival timestamp |
| On-device IMU | `SensorManager.registerListener()` → first `onSensorChanged()` | ~1-10ms (immediate) | Yes: `event.timestamp` |

**WT901 BLE IMU has the longest startup latency** (~500ms for EEPROM write + output mode switch), making it the bottleneck. However, unlike the camera, the BLE sensor data does NOT have a reliable timestamp from its own clock until we compute the offset (median of first 20 packets). This means:

- If we start IMU first and camera second: camera starts 500ms after IMU. We get video starting with IMU already flowing. The gap is `t_first_frame - first_imu_arrival_ns`. Camera provides precise t0. Backend trims initial IMU-only portion.

- If we start camera first and IMU second: IMU starts 500ms after camera. We get video-only frames for 500ms. IMU timestamps during the offset computation phase (first 20 packets) are unreliable — they use arrival timestamps which have ±5-15ms jitter. Worse: we have video without IMU at the start, which is more harmful for the ML pipeline (pose estimation needs IMU for CorrectiveLens 3D lifting from the first frame).

**Conclusion (H28 CONFIRMED): Start IMU streaming first (500ms settle), then camera.** Video without IMU at start is more harmful to the ML pipeline than IMU without video. The backend's CorrectiveLens (2D→3D lift→kinematic constraints→project back) needs IMU data aligned with video from the earliest possible frame.

**VideoIMUCapture pattern — recording flag vs. sensor registration:** VideoIMUCapture's `IMUManager` separates sensor *registration* from *recording*: `register()` is called at session start (sensors always active), while `startRecording()` just flips `mRecordingInertialData = true`. This is ideal for our BLE architecture too: BLE GATT notifications are already subscribed from connection time. The `Wt901Commander.startStreaming()` command (OutputContent 0x0046) makes the sensor start emitting data — there is no separate "recording" flag needed at the BLE layer. Data flows when streaming is enabled, and `ImuStreamWriter` gates disk writes. This matches VideoIMUCapture's pattern where the sensor listener is always active and the recording boolean controls disk output.

### Start (Revised Rev 5)

1. `StartRecordingUseCase`:
   - Start Foreground Service (wake lock + notification, type `connectedDevice|camera`)
   - Open `ImuStreamWriter` for each sensor's `.binpb` file (`BufferedOutputStream`)
   - **Start BLE streaming** via `Wt901Commander.startStreaming()` on both sensors (OutputContent 0x0046 + Save)
   - Record `t_imu_start_sent_ns = SystemClock.elapsedRealtimeNanos()` (when BLE start command was sent)
   - **Wait for first BLE notification** on each sensor → record `t_first_imu_left_ns`, `t_first_imu_right_ns`
   - Compute initial clock offset for each sensor (begin accumulating, don't wait for all 20 packets)
   - **Start Camera2** `CameraCaptureSession` with MediaRecorder + ImageReader → MP4 file + frame_timestamps.csv
   - Record `t_start_called = SystemClock.elapsedRealtimeNanos()` at `MediaRecorder.start()` call
   - Wait for first `CaptureCallback.onCaptureStarted()` → `t_first_frame = callback.timestamp` = exact video start
   - Check `SENSOR_INFO_TIMESTAMP_SOURCE`:
     - `REALTIME` (1): camera timestamps already in CLOCK_BOOTTIME → direct alignment
     - `UNKNOWN` (0): measure offset once, store in manifest
   - Record `sessionStartNs = t_first_frame` (NOT `elapsedRealtimeNanos()` at start call)
   - Start periodic resync timer (30s interval)
   - **Compute and store delays** (see manifest section):
     - `video_start_delay_ms = (t_first_frame - t_start_called) / 1_000_000`
     - `imu_start_delay_ms = (t_first_frame - t_first_imu_arrival_ns) / 1_000_000` (positive = IMU started before camera; negative = camera started before IMU)
   - Complete initial clock offset computation (wait for 20 BLE packets total per sensor)

### During Recording

- Camera2 → MP4 on disk (hardware encoder)
- FrameTimestampTracker → `frame_timestamps.csv` on disk (SingleThreadExecutor)
- BLE (L+R) → `BleHandlerThread` → `ImuStreamWriter.writeDelimitedTo(sample)` → `.binpb` on disk
- Display buffer: `ArrayRingBuffer<ImuSample>(60_000)` per sensor (~3.6MB for one sensor at 100Hz for 10 minutes; two sensors = ~7.2MB total, 5 min each)
- RecordingScreen HUD: duration, FPS, IMU sample rate, sensor battery, storage remaining

### IMU Disk Writing (Incremental Streaming)

**Revised (H3+H6 FALSIFIED):** No giant in-memory buffer. No single IMUStream message.

```kotlin
// Per-sample protobuf streaming to disk during recording
// Rev 4 (H22): Explicit 16KB buffer, periodic flush, protobuf-javalite
val fileOut = BufferedOutputStream(FileOutputStream(file), 16_384) // 16 KB buffer
// On each IMU sample:
sample.toRecord().writeDelimitedTo(fileOut)  // ~61 bytes per write

// Periodic flush every 1 second (timer-based coroutine)
private val flushJob = scope.launch {
    while (isActive) {
        delay(1_000)
        fileOut.flush()
    }
}

// On stop:
fileOut.flush()
fileOut.fd.sync()  // fsync — guarantee durability
fileOut.close()
// File is immediately upload-ready — no serialization step
```

**Rev 4 (H22) performance notes:**
- 200 writes/sec × 61 bytes = 12,200 bytes/sec — negligible I/O
- 16 KB buffer auto-flushes every ~1.3 seconds
- Explicit 1-second flush bounds data-at-risk to ~1 second of IMU data (~1200 bytes)
- `fd.sync()` on stop guarantees durability — no data loss on clean shutdown
- On crash: ~1 second of data at risk (acceptable — session marked incomplete)
- Use `protobuf-javalite` runtime (~1.5 MB vs ~5 MB for full protobuf)
- protobuf #4177 (small internal buffer) does NOT affect `BufferedOutputStream`-wrapped file output

**Benefits:**
- In-memory footprint: ~3.6MB (display buffer only) vs ~67MB (old design)
- Peak memory during recording: minimal — no giant protobuf allocation
- Safe on 4GB devices
- Upload-ready immediately on stop

### Stop

1. `StopRecordingUseCase`:
   - Stop Camera2 recording (flush MP4)
   - Stop ImageReader (close frame_timestamps.csv)
   - Stop BLE streaming on both sensors via `Wt901Commander.stopStreaming()` (OutputContent 0x0000 + Save)
   - Flush/close .binpb files
   - Build `manifest.json` (include `t_first_frame_ns`, `timestamp_source`, `video_start_delay_ms`, `imu_start_delay_ms` per sensor)
   - **Manifest field semantics:** `t0_ns` = `first_frame_ns` = session start time (the first video frame timestamp from `onCaptureStarted()`). `video_start_delay_ms` = `(first_frame_ns - t_start_called_ns) / 1_000_000` (latency between `MediaRecorder.start()` call and actual first frame). `imu_start_delay_ms` (per sensor) = `(first_frame_ns - t_first_imu_arrival_ns) / 1_000_000` (positive = IMU before camera, expected; negative = camera before IMU, abnormal)
   - Verify video FPS via `MediaExtractor`
   - Create `CaptureSession` with all file references
   - Stop Foreground Service

## Calibration

Sensors are **on the athlete's feet**, athlete stands still.

### Flow

1. `CalibrationScreen`: "Встаньте ровно, не двигайтесь. Датчики на ногах."
2. Collect 10 seconds of quaternion data (~1000 samples at 100Hz) from each sensor
3. Filter: discard samples where `|angular_velocity| > 5°/s` (movement detected — threshold from WT901 datasheet static accuracy spec)
4. **Normalized arithmetic mean** of remaining quaternions → `quat_ref` per sensor:
   - Ensure hemisphere consistency: if `dot(q_i, q_ref) < 0`, flip sign of `q_i`
   - Compute component-wise sum, normalize to unit length
   - Mathematically justified for static calibration (Gramkow 2001: error < 0.00001° when spread < 0.05° — WT901 static accuracy is 0.05° RMS)
   - For functional calibration with movement: would need Markley eigenvector method (H19 — not required for MVP)
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
      "imu_start_delay_ms": 480,
      "resync_intervals_s": 30,
      "reconnect_count": 0,
      "dropped_partial_count": 0
    },
    "right": {
      "filename": "capture_20260509_143000_right.binpb",
      "format": "delimited_imu_record",
      "sample_rate_hz": 100,
      "sensor_id": "WT901-YYYY",
      "clock_offset_ns": 67890,
      "imu_start_delay_ms": 490,
      "resync_intervals_s": 30,
      "reconnect_count": 1,
      "dropped_partial_count": 2
    }
  },
  "calibration": {
    "left": { "quat_ref": [1,0,0,0], "calibrated_at": "2026-05-09T14:29:50Z" },
    "right": { "quat_ref": [1,0,0,0], "calibrated_at": "2026-05-09T14:29:50Z" }
  }
}
```

**Manifest field semantics:**
- `t0_ns` / `first_frame_ns` = CLOCK_BOOTTIME nanoseconds of the first video frame from `onCaptureStarted()` — the session start reference
- `video_start_delay_ms` = `(first_frame_ns - t_start_called_ns) / 1_000_000` (latency between `MediaRecorder.start()` call and actual first frame). Always positive. Typically 50-500ms.
- `imu_start_delay_ms` (per sensor) = `(first_frame_ns - t_first_imu_arrival_ns) / 1_000_000`. **Positive** = IMU started before camera (expected with H28 startup order). **Negative** = camera started before IMU (abnormal, indicates excessive BLE settle time). This tells the backend exactly how much IMU data precedes the first video frame. Example: `480` means the first IMU sample arrived 480ms before the first video frame.
- `clock_offset_ns` (per sensor) = `android_arrival_ns - (chip_time_ms × 1_000_000)` — the median offset from initial sync. Updated by periodic resync. Each sensor has an independent offset because crystal oscillators differ between physical devices.

**Backend alignment with `imu_start_delay_ms`:**
- If `imu_start_delay_ms > 0`: IMU data starts before video. Backend discards IMU samples with `timestamp_ns < first_frame_ns`. The `imu_start_delay_ms` value is the expected duration of this initial IMU-only data.
- If `imu_start_delay_ms ≤ 0`: Video started before IMU. Backend discards video frames before the first IMU sample. This should be rare (only if BLE settle takes >500ms + camera start latency).
- Either way, the backend aligns to `t0_ns = first_frame_ns` as the session reference point. All timestamps in the session are relative to `t0_ns`.

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

### Android Permissions (Rev 4, H23)

**BLE permissions across all API levels (24-35):**

```xml
<!-- Legacy permissions for API 24-30 (Android 7-11) -->
<uses-permission android:name="android.permission.BLUETOOTH"
    android:maxSdkVersion="30" />
<uses-permission android:name="android.permission.BLUETOOTH_ADMIN"
    android:maxSdkVersion="30" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"
    android:maxSdkVersion="30" />

<!-- Android 12+ (API 31+) BLE permissions -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />

<!-- Foreground Service -->
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CAMERA" />
```

**Runtime permission flow:**
```kotlin
fun hasRequiredBlePermissions(): Boolean =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        hasPermission(BLUETOOTH_SCAN) && hasPermission(BLUETOOTH_CONNECT)
    } else {
        hasPermission(ACCESS_FINE_LOCATION)
    }
```

**Key points:**
- `neverForLocation` on `BLUETOOTH_SCAN`: app derives no physical location from BLE. User sees "Nearby devices" prompt, NOT location prompt.
- `BLUETOOTH_CONNECT` must be granted before `startForeground()` on Android 14+ (runtime prerequisite for `connectedDevice` FGS type).
- Background BLE scan not needed during recording — GATT notifications arrive without scanning.
- Samsung Android 12-13 bug with `neverForLocation` was fixed in One UI 5.1+.

### Android 14+ FGS Requirements

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

**Rev 5 (H27 CONFIRMED):** WT901 retains EEPROM-saved configuration across BLE disconnect/reconnect (sensor stays powered). No re-configuration needed on reconnect — only re-subscribe to FFE4 + CCCD. Defensive: verify OutputContent register via 0x71 response after reconnect. If OutputContent ≠ 0x0046, send full Unlock → OutputContent → Save sequence.

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

1. **BleScanScreen**: Scan for WT901 devices, assign LEFT/RIGHT, show connection status + battery (read battery via register 0x0A → 0x71 response with percentage value)
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
| BLE reconnect | Re-subscribe to FFE4 + CCCD, verify OutputContent, insert IMUGap | H27: EEPROM config persists across BLE reconnect (sensor stays powered). Verify OutputContent register after reconnect. Only re-configure if register ≠ 0x0046 |
| Screen rotation | `configChanges` prevents Activity recreation | Surface destroyed on rotation. All ref apps use configChanges. Service holds recording state |
| FGS type | connectedDevice\|camera | Android 14+ requirement for BLE + camera in foreground |
| FPS config | Camera2 AE_TARGET_FPS_RANGE | QualitySelector only controls resolution; FPS is separate Camera2 setting |
| FPS verification | Post-recording MediaExtractor | No CameraX/RecordingStats API for actual FPS |
| Command timing | 100ms inter-command, 500ms post-Save | XAMLCORP SDK uses 100ms serial delays. 10-second auto-lock window. EEPROM write needs settle time |
| GATT serialization | Write queue with mutual exclusion | `writeCharacteristic()` silently fails on concurrent ops. Use `WRITE_TYPE_NO_RESPONSE`. FFE9 write and FFE4 notify are independent |
| Sample grouping | Bitmask accumulator with 15ms timeout | No ordering guarantee (H8). Bitmask tracks {ACC, GYRO, QUAT}, emit when all three present. Duplicate frame type → drop previous incomplete cycle. Timeout → drop incomplete cycle, do NOT emit partial sample (proto3 float defaults to 0.0) |
| 0x55 collision | Checksum validation rejects false headers | 0x55 in payload fails checksum on individual frames. Buffer accumulation pattern from XAMLCORP PacketParser |
| Quaternion calibration | Normalized arithmetic mean with hemisphere check | Gramkow 2001: error < 0.00001° for static. Markley eigenvector needed only for functional calibration with movement |
| Protobuf runtime | protobuf-javalite | ~1.5 MB vs ~5 MB full. Supports writeDelimitedTo identically |
| IMU disk flush | 16 KB buffer + 1s periodic flush + fd.sync() on stop | Bounds data-at-risk to ~1 second. fsync guarantees durability on clean stop |
| BLE permissions | neverForLocation on BLUETOOTH_SCAN + BLUETOOTH_CONNECT | API 31+: "Nearby devices" prompt. API 24-30: ACCESS_FINE_LOCATION. Samsung One UI 5.1+ fixed neverForLocation bug |
| Partial IMU samples | Drop incomplete cycles, count in manifest | Proto3 float defaults to 0.0 not NaN. Emitting partial samples would produce bogus zero values. Skip + count is minimal and correct |
| Streaming control | Unlock + OutputContent register + Save | H25: Unlock required before EVERY register write. 10-second window expires after Save. Official C SDK always calls Unlock before WitSetContent(). Start: Unlock→0x0046→Save (~750ms). Stop: Unlock→0x0000→Save (~750ms) |
| IMU timestamps | Android arrival time + periodic 0x50 register reads | H26: No per-sample timestamp in individual frames. All SDKs use arrival time. Periodic register reads for drift correction |
| Startup order | IMU first, camera second | H28 confirmed. WT901 BLE settle ~500ms is longest startup latency. OpenCamera-Sensors + VideoIMUCapture both start sensors before camera. Video without IMU is more harmful (CorrectiveLens needs IMU from first frame). `imu_start_delay_ms` in manifest records the gap |

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
| H17 | Reference SDKs implement sample grouping state machine | FALSIFIED | None of 3 SDKs (Android, C#, TypeScript) groups 0x51+0x52+0x59 into samples. All process frames independently. Must implement our own state machine with 15ms timeout |
| H18 | 0x55 header byte collision causes misparse | REVISED | Can occur but checksum validation on individual frames rejects false 0x55. C# SDK's buffer accumulation + checksum pattern is correct. 0x61 combined frame has NO checksum — not used in our architecture |
| H19 | Simple quaternion averaging is mathematically incorrect for calibration | REVISED | Normalized arithmetic mean is acceptable for STATIC calibration (Gramkow 2001: error < 0.00001° when spread < 0.05°). Markley eigenvector method only needed for functional calibration with movement |
| H20 | WT901 config commands can be sent rapidly with no delay | FALSIFIED | 10-second auto-lock window for Unlock. XAMLCORP SDK: 100ms serial inter-command, 500ms post-Save. BLE: 50ms between Unlock and next command. EEPROM write needs settle time |
| H21 | GATT operations are automatically serialized by Android | FALSIFIED | `writeCharacteristic()` silently fails on concurrent operations. C# SDK uses SemaphoreSlim. Must implement write queue. Write commands work during active streaming (FFE9 write + FFE4 notify are independent) |
| H22 | protobuf writeDelimitedTo at 200 Hz has performance concerns | CONFIRMED SAFE | 12,200 bytes/sec through 16 KB BufferedOutputStream is negligible. protobuf-javalite recommended. Periodic flush + fd.sync() on stop. Crash data-at-risk: ~1 second |
| H23 | BLE permissions are the same across all Android versions | FALSIFIED | Android 12+ completely new model: BLUETOOTH_SCAN + BLUETOOTH_CONNECT replace BLUETOOTH + ACCESS_FINE_LOCATION. neverForLocation removes location requirement. Must handle both models |
| H24 | Proto3 can represent partial IMU samples via NaN | FALSIFIED | Proto3 float defaults to 0.0 not NaN. Partial samples with missing fields would produce bogus zero values. Solution: skip incomplete cycles, count in manifest `dropped_partial_count` |
| H28 | Start IMU streaming first (500ms settle), then camera. Record imu_start_delay_ms in manifest | CONFIRMED | OpenCamera-Sensors: registerListener() before MediaRecorder.start(). VideoIMUCapture: IMU always registered, startRecording() just flips boolean. WT901 BLE startup ~500ms (EEPROM settle). Camera 50-500ms. IMU-first ensures video has aligned IMU from first frame. Backend trims initial IMU-only data using imu_start_delay_ms. CorrectiveLens needs IMU from earliest video frame. |
| H25 | Unlock window persists across operations | FALSIFIED | 10-second window expires after Save. Official C SDK: WitSetContent() always calls Unlock first. Official Android SDK: unlockReg() before every config action. Must Unlock before start/stop streaming |
| H26 | WT901 individual frames provide per-sample timestamps | FALSIFIED | 11-byte frames contain only sensor data + checksum. No sample counter. All 3 reference SDKs use Android arrival time. Timestamps assigned via elapsedRealtimeNanos() at BLE notification arrival + periodic 0x50 register reads for drift correction |
| H27 | WT901 retains EEPROM-saved config across BLE reconnect | CONFIRMED | BLE disconnect ≠ power cycle. Sensor MCU stays running with saved register values. SDKs only re-subscribe to FFE4 notifications on reconnect. Defensive: verify OutputContent register after reconnect |
