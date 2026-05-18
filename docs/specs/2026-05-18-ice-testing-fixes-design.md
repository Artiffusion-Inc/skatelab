# Ice Testing Fixes — Design Spec

> Problems found during on-ice testing 2026-05-18: massive session size, export crash, missing session viewer, video quality misconfiguration.

## Problem Summary

| # | Problem | Type | Impact |
|---|---------|------|--------|
| 1 | Video 14 Mbps instead of 2-4 Mbps | Bug | 3 min session = 220 MB (should be 30-60 MB) |
| 2 | Export crash "attempt to write past end of start entry" | Bug | Cannot export large sessions |
| 3 | No session viewer (click → export only) | Feature | Must connect sensors to view data |
| 4 | No video quality configuration | Bug/Fix | CameraX defaults to max quality |

## 1. Video Bitrate Fix (Bug)

**Root cause:** `CameraXRecorder.kt:74-77` builds `Recorder` without `QualitySelector`. Device picks maximum quality (720x1280 @ 14 Mbps H.264 High profile).

**Fix in** `CameraXRecorder.kt`:

```kotlin
// Before:
val r = Recorder.Builder()
    .setAspectRatio(androidx.camera.core.AspectRatio.RATIO_16_9)
    .build()

// After:
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector

val r = Recorder.Builder()
    .setQualitySelector(
        QualitySelector.fromOrderedList(
            listOf(Quality.HD, Quality.SD),
            FallbackStrategy.lowerQualityOrHigherThan(Quality.SD),
        ),
    )
    .build()
```

- `Quality.HD` = 1280x720 @ 2-4 Mbps. Matches frontend compression target (`video-compression.ts`: 1280x720 @ 2 Mbps).
- `Quality.SD` = 720x480 @ 1-2 Mbps. Fallback for low-end devices.
- `FallbackStrategy.lowerQualityOrHigherThan(Quality.SD)`: guarantees recording always succeeds.
- Remove `setAspectRatio()` — redundant with QualitySelector, can cause binding failures on some devices.
- CameraX video 1.5.3 supports `setQualitySelector` since 1.1.0-alpha01. No version bump needed.

**Expected result:** 3 min session: ~30-60 MB instead of 220 MB. Frontend can skip recompression for app-recorded videos.

## 2. Export Crash Fix (Bug)

**Root cause:** `ZipExporter.kt:31` — MP4 files use STORED method. STORED requires `entry.size` bytes written exactly. For 230 MB MP4:
1. `file.length()` reads size → `computeCrc32()` reads entire file (230 MB I/O)
2. Write loop reads entire file again (230 MB I/O)
3. If file changes between `file.length()` and write completion → size mismatch → crash

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
- ZIP size increase: ~0.2% (MP4 is already compressed, deflate adds framing overhead only)
- Byte-exact preservation guaranteed (deflate round-trip is lossless)

`binpb` files (~800 KB) stay STORED — small enough that double-read is negligible.

## 3. Session Viewer (Feature)

### Navigation

- `onSessionClick` → `Routes.SESSION_DETAIL/{sessionId}` (new route)
- Old: click → `Routes.EXPORT/{sessionId}`
- Export button moves inside SessionDetailScreen

### New Route

```kotlin
object Routes {
    // ...existing routes...
    const val SESSION_DETAIL = "session/{sessionId}"
    fun sessionDetail(sessionId: String) = "session/$sessionId"
}
```

### SessionDetailScreen Layout

```
┌──────────────────────────────┐
│  ← Сессии                    │  TopAppBar
├──────────────────────────────┤
│  ┌──────────────────────────┐│
│  │   Video Player           ││  Media3 ExoPlayer
│  │   (local file playback)  ││
│  └──────────────────────────┘│
│  ┌──────────────────────────┐│
│  │   IMU Charts             ││  |a| + rotation angle
│  │   LEFT: |a|, angle       ││  Synced with video via t0_ns
│  │   RIGHT: |a|, angle      ││
│  └──────────────────────────┘│
│  Metadata                    │
│  • Date, duration            │
│  • FPS, verified             │
│  • Video start delay         │
│  • IMU start delay L/R       │
│  • Calibration status L/R    │
│  • File sizes (video/imu)    │
│  • Reconnect/dropped counts  │
├──────────────────────────────┤
│  [ Export ]  [ Delete ]       │  Bottom actions
└──────────────────────────────┘
```

### IMU Visualization

**Data source:** Parse `*_left.binpb` and `*_right.binpb` (delimited protobuf `ImuRecord`).

**Derived signals (per sensor):**
- `|a| = sqrt(ax² + ay² + az²)` — total acceleration. Jumps visible as |a| → ~0 during flight.
- `rotation_angle = 2 * acos(qw)` — rotation from calibration reference. Spins visible as angle change.

**Chart:** 4 lines total — `|a|_L`, `angle_L`, `|a|_R`, `angle_R`. Time axis in seconds from t0_ns.

**Video-IMU sync:** Video position (ms) maps to IMU time via:
```
imu_time_s = (video_position_ms + video_start_delay_ms) / 1000
```
When user seeks video, chart scrubber follows. When chart is tapped, video seeks to that position.

### Dependencies

| Library | Purpose | Size |
|---------|---------|------|
| Media3 ExoPlayer | Video playback | ~2 MB |
| Vico | Compose-native charting | ~500 KB |

Vico preferred over MPAndroidChart: Compose-native, lighter, maintained. Start with Vico; if it lacks line-chart features needed here (multi-series, scrubber sync), switch to Ycharts (another Compose-native option).

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
            _session.value?.let { parseImuData(it) }
        }
    }

    private fun parseImuData(session: CaptureSession) {
        // Parse both binpb files on Dispatchers.IO
        // Compute |a| and rotation_angle
        // Emit ImuChartData(times, |a|_L, angle_L, |a|_R, angle_R)
    }
}

data class ImuChartData(
    val timeSeconds: FloatArray,
    val accMagLeft: FloatArray,
    val rotAngleLeft: FloatArray,
    val accMagRight: FloatArray,
    val rotAngleRight: FloatArray,
)
```

### Video Playback

Use `Media3 ExoPlayer` with local `File` source. No network needed.

```kotlin
val context = LocalContext.current
val exoPlayer = remember {
    AndroidExoPlayer.Builder(context).build().apply {
        val mediaItem = MediaItem.fromUri(session.videoFile.toUri())
        setMediaItem(mediaItem)
        prepare()
    }
}
DisposableEffect(Unit) {
    onDispose { exoPlayer.release() }
}
```

## 4. Video Configuration

Fixed HD 720p via QualitySelector (Section 1). No user-facing settings. This is a bugfix, not a feature.

The frontend compression system (`video-compression.ts`) remains as-is — it handles web uploads from non-app sources. App-recorded videos at 720p @ 2-4 Mbps will often be under the 10 MB skip threshold, so frontend compression may be skipped entirely.

## File Changes Summary

| File | Change | Type |
|------|--------|------|
| `CameraXRecorder.kt` | Add QualitySelector, remove setAspectRatio | Bug fix |
| `ZipExporter.kt` | Remove "mp4" from STORED_EXTENSIONS | Bug fix |
| `SessionDetailScreen.kt` | New: video player + IMU charts + metadata | Feature |
| `SessionDetailViewModel.kt` | New: load session, parse IMU, expose state | Feature |
| `ImuChartData.kt` | New: data class for chart data | Feature |
| `ImuParser.kt` | New: parse binpb, compute |a| and rotation | Feature |
| `AppNavigation.kt` | Add SESSION_DETAIL route, change onSessionClick | Feature |
| `Routes.kt` | Add SESSION_DETAIL constant and helper | Feature |
| `build.gradle.kts` | Add Media3 ExoPlayer + Vico dependencies | Feature |

## Non-Goals

- Raw IMU data viewer (10-axis × 2 sensor). Can add toggle later.
- Video quality settings UI. Fixed 720p is sufficient.
- Video trimming/cropping in-app. Frontend handles post-upload.
- Cloud sync or remote session storage.