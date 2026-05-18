# Ice Testing Fixes — Design Spec

> Problems found during on-ice testing 2026-05-18: massive session size, export crash, manifest dimension mismatch, missing session viewer, video quality misconfiguration.

## Problem Summary

| # | Problem | Type | Impact |
|---|---------|------|--------|
| 1 | Video 14 Mbps instead of 2-4 Mbps | Bug | 3 min session = 220 MB (should be 30-60 MB) |
| 2 | Export crash "attempt to write past end of STORED entry" | Bug | Cannot export large sessions |
| 3 | Manifest hardcodes 1920x1080 instead of actual resolution | Bug | Frontend compression misconfig |
| 4 | No session viewer (click → export only) | Feature | Must connect sensors to view data |
| 5 | No video quality configuration | Bug/Fix | CameraX defaults to max quality |

## Execution Phases

**Phase 1 — Bug fixes (zero new dependencies, immediate value):** Items 1, 2, 3. Ship in a single commit.

**Phase 2 — Session Viewer feature:** Item 4. Depends on Phase 1 for realistic testing (30-60 MB videos instead of 220 MB).

---

## 1. Video Bitrate Fix (Bug) — Phase 1

**Root cause:** `CameraXRecorder.kt:74-77` builds `Recorder` without `QualitySelector`. Device picks maximum quality (720x1280 @ 14 Mbps H.264 High profile).

**Fix in** `CameraXRecorder.kt`:

```kotlin
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector

val r = Recorder.Builder()
    .setAspectRatio(androidx.camera.core.AspectRatio.RATIO_16_9)
    .setQualitySelector(
        QualitySelector.fromOrderedList(
            listOf(Quality.HD, Quality.SD),
            FallbackStrategy.lowerQualityOrHigherThan(Quality.SD),
        ),
    )
    .build()
```

**IMPORTANT: Keep `setAspectRatio(RATIO_16_9)` alongside `QualitySelector`.** The Android docs state both settings are respected — `QualitySelector` picks the quality level, `setAspectRatio` constrains the resolution to 16:9. Removing `setAspectRatio` risks 4:3 output on some devices, breaking ML pipeline assumptions. (Confirmed by CameraX official docs.)

- `Quality.HD` = typically 1280x720 @ 2-4 Mbps. Matches frontend compression target (`video-compression.ts`: 1280x720 @ 2 Mbps).
- `Quality.SD` = typically 720x480 @ 1-2 Mbps. Fallback for low-end devices.
- CameraX video 1.5.3 supports `setQualitySelector` since 1.1.0-alpha01. No version bump needed.

**Post-recording verification:** Use `MediaMetadataRetriever` to log actual width/height/bitrate from recorded files. Add in `VideoRecordEvent.Finalize` handler or repository layer:

```kotlin
val retriever = MediaMetadataRetriever()
retriever.setDataSource(videoFile.absolutePath)
val actualWidth = retriever.extractMetadata(METADATA_KEY_VIDEO_WIDTH).toInt()
val actualHeight = retriever.extractMetadata(METADATA_KEY_VIDEO_HEIGHT).toInt()
val actualBitrate = retriever.extractMetadata(METADATA_KEY_BITRATE).toLong()
retriever.release()
```

Pass `actualWidth`/`actualHeight` to ManifestBuilder (see Section 3).

**Expected result:** 3 min session: ~30-60 MB instead of 220 MB. Frontend can skip recompression for app-recorded videos.

**Follow-up:** If post-recording metrics show some OEMs still produce >4 Mbps at HD, add `setTargetVideoEncodingBitRate(3_000_000)` as a follow-up fix.

---

## 2. Export Crash Fix (Bug) — Phase 1

**Root cause:** `ZipExporter.kt:31` — MP4 files use STORED method. STORED requires `entry.size` bytes written exactly. OpenJDK throws `ZipException("attempt to write past end of STORED entry")` when `written - locoff > entry.size`.

For 230 MB MP4:
1. `file.length()` reads size → `computeCrc32()` reads entire file (230 MB I/O)
2. Write loop reads entire file again (230 MB I/O)
3. If file changes between `file.length()` and write completion → size mismatch → crash

Additionally, `closeEntry()` for STORED has a second guard: if `e.size != written - locoff`, throws `"invalid entry size"`. If file shrinks, this fires instead. STORED is fragile in both directions.

**Fix in** `ZipExporter.kt`:

```kotlin
// Before:
private val STORED_EXTENSIONS = setOf("mp4", "binpb")

// After:
private val STORED_EXTENSIONS = setOf("binpb")
```

MP4 files now use DEFLATED (default). Benefits:
- No size invariant to violate → crash impossible
- No `computeCrc32` call → I/O halved (230 MB instead of 460 MB per file)
- CPU overhead is modest and acceptable for a one-time export (deflate on already-compressed H.264 adds ~0.2% size, negligible CPU)
- Byte-exact preservation guaranteed (deflate round-trip is lossless)

`binpb` files (~800 KB) stay STORED — atomically written, no append-race. Add comment:

```kotlin
// STORED requires size/crc pre-computation. Safe for atomically-written binpb,
// but MP4 is excluded because it may still be finalizing when export runs.
private val STORED_EXTENSIONS = setOf("binpb")
```

**Known secondary issues in ZipExporter** (not blocking this fix, filed for follow-up):
- No coroutine cancellation during blocking FileInputStream reads
- No cleanup of partial ZIP on failure
- No progress reporting (indeterminate spinner only)
- `BufferedInputStream` + separate `ByteArray` is double-buffering

---

## 3. Manifest Dimension Fix (Bug) — Phase 1

**Root cause:** `ManifestBuilder.kt` hardcodes 1920x1080 for video width/height. Actual video is 720x1280 (portrait, device-dependent). This mismatch misleads frontend compression logic.

**Fix:** Pass actual resolution from `VideoRecordEvent.Finalize` or `MediaMetadataRetriever` to ManifestBuilder.

In `CameraXRecorder.kt`, the `stopRecording()` method returns `RecordingStopResult` which currently has `actualFps`, `fpsVerified`, `firstFrameNs`. Add `actualWidth` and `actualHeight` fields:

```kotlin
data class RecordingStopResult(
    val actualFps: Int,
    val fpsVerified: Boolean,
    val firstFrameNs: Long,
    val actualWidth: Int,   // NEW
    val actualHeight: Int,  // NEW
)
```

Populate from `MediaMetadataRetriever` after recording stops. Pass through to `ManifestBuilder.video { width(actualWidth); height(actualHeight) }` instead of hardcoded 1920x1080.

**Impact:** Frontend `video-compression.ts` reads width/height from manifest. Correct values prevent unnecessary recompression and 4K guard false triggers.

---

## 4. Session Viewer (Feature) — Phase 2

### Navigation

- `onSessionClick` → `Routes.SESSION_DETAIL/{sessionId}` (new route)
- Old: click → `Routes.EXPORT/{sessionId}`
- Export button moves inside SessionDetailScreen (Details tab)
- **Post-recording flow:** `onRecordingComplete` → `SESSION_DETAIL` instead of EXPORT. Users review first, export is explicit.
- Add **quick-export icon** to `SessionRow` in `SessionListScreen` for power users who just want to export without viewing.

### New Route

```kotlin
object Routes {
    // ...existing routes...
    const val SESSION_DETAIL = "session_detail/{sessionId}"
    fun sessionDetail(sessionId: String) = "session_detail/$sessionId"
}
```

### Layout — 3-Tab Design

Phone screen cannot fit video + charts + metadata in a single scroll. Use **TabRow** with 3 tabs:

```
┌──────────────────────────────┐
│  ← Сессии                    │  TopAppBar
├──────────────────────────────┤
│  [ Video ] [ Charts ] [ Info ]│  TabRow
├──────────────────────────────┤
│                              │
│   (tab content here)         │
│                              │
└──────────────────────────────┘
```

**Video tab:** Full-width ExoPlayer with playback controls. Can go fullscreen on rotation.

**Charts tab:** Dedicated space for IMU signals (4-6 lines). Full chart height without competing with video.

**Details tab:** Metadata + Export/Delete action buttons. Clean, scannable.

### IMU Visualization

**Data source:** Parse `*_left.binpb` and `*_right.binpb` (delimited protobuf `IMURecord`).

**Proto schema** (`imu.proto`):
```protobuf
message IMUSample {
    uint64 timestamp_ns = 1;
    float acc_x = 2;   float acc_y = 3;   float acc_z = 4;
    float gyro_x = 5;  float gyro_y = 6;  float gyro_z = 7;
    float quat_w = 8;  float quat_x = 9;  float quat_y = 10; float quat_z = 11;
}
```

Note: Proto3 omits default-value fields (0.0) on wire. Missing fields return 0.0 when parsed — handle explicitly.

**Derived signals (per sensor):**

1. `|a| = sqrt(acc_x² + acc_y² + acc_z²)` — total acceleration magnitude. During free flight, |a| drops toward **~9.8 m/s²** (gravity), NOT ~0. Values significantly above 9.8 indicate centrifugal acceleration from spins or ground contact forces.

2. `|ω| = sqrt(gyro_x² + gyro_y² + gyro_z²)` — angular velocity magnitude (deg/s). This is the **primary spin-speed signal**. Directly shows rotation rate without noisy quaternion differentiation. Values observed up to ~1700°/s in real skating data.

3. `accumulated_rotation` — unwrapped rotation from calibration reference. Computed from consecutive quaternion pairs:
   ```
   dot = |q0 · q1|  (clamped to [0, 1])
   step_angle = 2 * acos(dot)
   accumulated_rotation += step_angle  // rad, monotonically increasing
   ```
   **NOT** `2 * acos(qw)` — that wraps at π and is useless for multi-revolution spins (figure skating involves 10s-100s of rotations per session).

**Chart lines:** 6 lines total per sensor pair:
- `|a|_L`, `|a|_R` — acceleration magnitude
- `|ω|_L`, `|ω|_R` — angular velocity
- `rot_L`, `rot_R` — accumulated rotation

Or, for a simpler initial view, show 4 lines: `|a|_L`, `|ω|_L`, `|a|_R`, `|ω|_R`. Add accumulated rotation as a toggle.

**Time axis:** Session-relative time in seconds:
```kotlin
session_time_s = (timestamp_ns - t0_ns) / 1_000_000_000.0
```
Both IMU samples and video frames use the same `SystemClock.elapsedRealtimeNanos()` monotonic clock. The `video_start_delay_ms` and `imu_start_delay_ms` in the manifest are **diagnostic offsets**, not sync parameters. The `clock_offset_ns` field is the WT901 chip-time offset — it is **unused** for exported binpb timestamps because the parser timestamps with Android `arrivalNs`, not sensor chip time.

**Video-IMU sync (v1 — playhead-only):**
- Chart tap → video seek: In chart touch handler, compute `target_ms = (tapped_time_s * 1000).toLong()` and call `exoPlayer.seekTo(target_ms)`.
- Video → chart: Show a vertical **playhead line** on the chart that moves with video time. Do NOT scroll the chart programmatically (avoids feedback loops, reduces complexity). Programmatic chart scroll can be added in v2.

**Bidirectional sync architecture (v2, if needed):**
```kotlin
// ViewModel single source of truth
private val _currentPositionMs = MutableStateFlow(0L)
val currentPositionMs: StateFlow<Long> = _currentPositionMs.asStateFlow()

fun seekTo(positionMs: Long) { _currentPositionMs.value = positionMs }
fun onPlaybackPosition(positionMs: Long, fromUser: Boolean = false) {
    if (!fromUser) _currentPositionMs.value = positionMs
}
```
Break feedback loop: chart touch sets `fromUser=true`, ExoPlayer position listener only updates when `!player.isSeeking`.

### Memory

- IMU: ~280 KB per sensor for 3 min @ 100Hz (`FloatArray`). No downsampling needed for sessions under 5 minutes.
- Video: ExoPlayer handles internal buffering; file is not fully loaded into RAM.
- For longer sessions (>5 min), consider LTTB or simple decimation before charting.

### Dependencies

| Library | Purpose | Size |
|---------|---------|------|
| Media3 ExoPlayer 1.6.0 | Video playback | ~2 MB |
| Vico 2.1.0 | Compose-native charting | ~500 KB |

Vico supports multi-series line charts, touch markers (`markerVisibilityListener`), and is Compose-native. Verify programmatic scroll API on first integration — if insufficient, fallback to custom Canvas implementation for chart.

```kotlin
// build.gradle.kts additions
val media3Version = "1.6.0"
implementation("androidx.media3:media3-exoplayer:$media3Version")
implementation("androidx.media3:media3-ui:$media3Version")

implementation("com.patrykandpatrick.vico:compose:2.1.0")
implementation("com.patrykandpatrick.vico:core:2.1.0")
```

### ExoPlayer Ownership

**ExoPlayer must live in `SessionDetailViewModel`**, not in Compose `remember`. `remember` does not survive configuration changes (rotation). `rememberSaveable` cannot save an ExoPlayer (not Parcelable). The ViewModel survives rotation.

```kotlin
@HiltViewModel
class SessionDetailViewModel @Inject constructor(
    private val sessionRepository: SessionRepository,
) : ViewModel() {
    private var _exoPlayer: ExoPlayer? = null

    fun getPlayer(context: Context): ExoPlayer {
        return _exoPlayer ?: ExoPlayer.Builder(context).build().also {
            _exoPlayer = it
        }
    }

    override fun onCleared() {
        _exoPlayer?.release()
        _exoPlayer = null
    }
}
```

In Compose, use `AndroidView` with `PlayerView`.

### SessionDetailViewModel

```kotlin
@HiltViewModel
class SessionDetailViewModel @Inject constructor(
    private val sessionRepository: SessionRepository,
) : ViewModel() {
    private val _session = MutableStateFlow<CaptureSession?>(null)
    val session: StateFlow<CaptureSession?> = _session.asStateFlow()

    private val _imuData = MutableStateFlow<ImuChartData?>(null)
    val imuData: StateFlow<ImuChartData?> = _imuData.asStateFlow()

    fun loadSession(sessionId: String) {
        viewModelScope.launch {
            _session.value = sessionRepository.getSession(sessionId)
            // Parse IMU lazily when Charts tab is first selected
        }
    }

    fun loadImuData() {
        viewModelScope.launch(Dispatchers.IO) {
            _session.value?.let { session ->
                _imuData.value = ImuParser.parse(session)
            }
        }
    }
}

data class ImuChartData(
    val timeSeconds: FloatArray,
    val accMagLeft: FloatArray,
    val angVelLeft: FloatArray,
    val accMagRight: FloatArray,
    val angVelRight: FloatArray,
)
```

### IMU Parsing

New `ImuParser.kt` (in `data/imu/` or `data/parser/`):
- Read delimited protobuf `IMURecord` from `.binpb` files
- Compute derived signals: `|a|`, `|ω|`, accumulated rotation
- Return `ImuChartData` with `FloatArray` fields
- Parse on `Dispatchers.IO`

---

## 5. Video Configuration

Fixed HD 720p via QualitySelector (Section 1). No user-facing settings. This is a bugfix, not a feature.

The frontend compression system (`video-compression.ts`) remains as-is — it handles web uploads from non-app sources. App-recorded videos at 720p @ 2-4 Mbps will often be under the 10 MB skip threshold, so frontend compression may be skipped entirely.

---

## File Changes Summary

| File | Change | Phase |
|------|--------|-------|
| `CameraXRecorder.kt` | Add QualitySelector (keep setAspectRatio), add MediaMetadataRetriever | 1 |
| `ManifestBuilder.kt` | Use actual width/height from recording instead of hardcoded 1920x1080 | 1 |
| `ZipExporter.kt` | Remove "mp4" from STORED_EXTENSIONS, add comment | 1 |
| `RecordingStopResult` | Add actualWidth/actualHeight fields | 1 |
| `SessionDetailScreen.kt` | New: 3-tab layout with video/charts/metadata | 2 |
| `SessionDetailViewModel.kt` | New: load session, ExoPlayer, parse IMU, expose state | 2 |
| `ImuChartData.kt` | New: data class for chart data | 2 |
| `ImuParser.kt` | New: parse binpb, compute \|a\|, \|ω\|, accumulated rotation | 2 |
| `AppNavigation.kt` | Add SESSION_DETAIL route, change onSessionClick, change onRecordingComplete | 2 |
| `Routes.kt` | Add SESSION_DETAIL constant and helper | 2 |
| `build.gradle.kts` | Add Media3 ExoPlayer + Vico dependencies | 2 |
| `SessionListScreen.kt` | Add quick-export icon to SessionRow | 2 |

## Non-Goals

- Raw IMU data viewer (10-axis × 2 sensor). Can add toggle later.
- Video quality settings UI. Fixed 720p is sufficient.
- Video trimming/cropping in-app. Frontend handles post-upload.
- Cloud sync or remote session storage.
- Programmatic chart scroll synced with video (v2 after playhead-only v1).
- Export progress bar / cancellation (follow-up).
