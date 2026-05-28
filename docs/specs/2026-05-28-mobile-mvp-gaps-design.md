# Mobile MVP Gaps — Design

> **Goal:** Close 5 critical gaps in the SkateLab mobile app that break the core user journey (record → upload → analyze → track progress) for the Q2-Q3 2026 pilot.

> **Architecture:** Bottom-sheet element selector reused across camera and gallery upload; Room Flow for upload status observation; UploadWorker extended with elementType; duplicate screens removed.

> **Tech Stack:** Jetpack Compose M3, Room, WorkManager, CameraX, ActivityResultContracts, Vico charts

---

## 1. Element Type Selection

### Problem

`UploadWorker:102` hardcodes `elementType = "axel"` when creating a session. All recorded sessions are created as "axel" regardless of the actual element performed, making metrics meaningless.

### Solution

**Element Type Bottom Sheet** — a `ModalBottomSheet` shown after recording stops or after a gallery video is picked. Displays the `elementLabelsRu` map as radio buttons. Default selection: "axel" (backward compatible). User confirms with "Далее" button.

**Data model change:** `PendingUploadEntity` gets a new nullable field:

```kotlin
@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey val id: String,
    val videoPath: String,
    val imuLeftPath: String? = null,
    val imuRightPath: String? = null,
    val manifestPath: String? = null,
    val elementType: String? = null,  // NEW — null = "axel" for backward compat
    val status: String = "READY",
    val uploadId: String? = null,
    val r2Key: String? = null,
    val sessionId: String? = null,
    val retryCount: Int = 0,
    val createdAt: Long = System.currentTimeMillis(),
)
```

No Room migration needed — nullable field with default `null` is additive.

**UploadWorker change:** Replace `elementType = "axel"` with `elementType = pendingUpload.elementType ?: "axel"`.

**Bottom sheet component:**

```kotlin
@Composable
fun ElementTypeBottomSheet(
    selectedType: String,
    onTypeSelected: (String) -> Unit,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
)
```

- Reads `elementLabelsRu` from `ElementLabels.kt` (shared module)
- Radio button list, single selection
- "Далее" button enabled once a type is selected (always enabled since "axel" is default)
- Dismiss sets elementType to null (fallback to "axel" in UploadWorker)

**Reuse:** Same bottom sheet is shown from both CameraViewModel (after stopRecording) and gallery pick flow.

---

## 2. Processing Navigation

### Problem

After `CameraViewModel.stopRecording()`, the app saves a `PendingUploadEntity` and enqueues `UploadWorker`, but never navigates to `ProcessingScreen`. The user has no visibility into upload or processing progress.

### Solution

**Two-phase ProcessingScreen:**

Phase 1 — **Upload phase**: ProcessingScreen observes `PendingUploadEntity` via Room Flow (`pendingUploadDao.getById(uploadId)`). Shows upload progress (status: READY → UPLOADING). Displays a determinate or indeterminate progress indicator based on status.

Phase 2 — **Processing phase**: When UploadWorker sets status to `PROCESSING` and writes `sessionId`, ProcessingScreen subscribes to SSE via `processApi.stream(sessionId)`. Shows percentage + message from SSE events. On completion, navigates to `ResultDetailRoute(sessionId)`.

**Navigation route change:**

```kotlin
@Serializable
data class ProcessingRoute(val uploadId: String? = null, val sessionId: String? = null)
```

Primary entry: `uploadId` (from camera/gallery flow). The screen loads the PendingUploadEntity from Room and observes status transitions. Fallback entry: `sessionId` only (from deep link, notification, or other entry point) — skips upload phase, goes directly to SSE subscription. Exactly one of `uploadId` or `sessionId` must be non-null.

**CameraViewModel change:** After `stopRecording()` → save PendingUpload → enqueue → emit navigation event with `uploadId`.

**CameraScreen change:** Observe navigation event from CameraViewModel, call `navController.navigate(ProcessingRoute(uploadId))`.

**UploadWorker changes:** Worker must update the PendingUploadEntity status through each phase:
- Before upload: status = "UPLOADING"
- After session created + processing queued: status = "PROCESSING", write `sessionId`
- On completion: status = "COMPLETED"
- On failure: status = "FAILED"

---

## 3. Gallery Upload

### Problem

The only upload path is recording via CameraScreen. Users (coaches) often film separately and want to upload existing videos.

### Solution

**Gallery FAB on CameraScreen** — a secondary FAB (or button) with an "attach" icon. On tap:

1. Launch `ActivityResultContracts.PickVisualMedia` with `PickVisualMediaRequest(MediaType.Video)`
2. Receive selected video URI
3. Copy video to app-specific directory (`context.getExternalFilesDir(DIRECTORY_MOVIES)`)
4. Show ElementTypeBottomSheet
5. Create `PendingUploadEntity` (videoPath = copied file, imuLeftPath/imuRightPath = null, elementType = selected type)
6. Enqueue UploadWorker
7. Navigate to ProcessingRoute(uploadId)

**UploadWorker already handles null IMU paths** — it skips IMU upload steps when paths are null. No changes needed in the upload logic.

**CameraScreen UI:** Primary FAB = record (existing). Secondary FAB = gallery upload, positioned below/to the side. Or a text button "Загрузить видео" at the bottom of the camera preview.

---

## 4. Upload Queue Screen

### Problem

If a PendingUpload reaches FAILED status (3 retries exhausted), there is no UI to retry or delete it. Users have no visibility into upload queue status.

### Solution

**UploadQueueScreen** — a dedicated screen showing all PendingUpload entries.

**Access:** From ProfileScreen (row "Загрузки" with badge showing pending count) and from MoreScreen.

**UI:**

```
┌─────────────────────────────────┐
│  ← Загрузки                      │
├─────────────────────────────────┤
│  ┌─────────────────────────────┐│
│  │ VID_20260528.mp4            ││
│  │ Аксель  ● UPLOADING         ││
│  │ ████████░░░  80%            ││
│  └─────────────────────────────┘│
│  ┌─────────────────────────────┐│
│  │ VID_20260527.mp4            ││
│  │ Флип    ● FAILED            ││
│  │ [Повторить]  [Отменить]     ││
│  └─────────────────────────────┘│
│  ┌─────────────────────────────┐│
│  │ VID_20260525.mp4            ││
│  │ Лутц    ● COMPLETED         ││
│  └─────────────────────────────┘│
├─────────────────────────────────┤
│  Пустое состояние:              │
│  "Нет загрузок" + иконка        │
└─────────────────────────────────┘
```

**Data:** `PendingUploadDao` gets new queries:
- `fun getAll(): Flow<List<PendingUploadEntity>>` — live list for the screen
- `fun countPending(): Flow<Int>` — badge count (READY + UPLOADING + PROCESSING)

**Actions:**
- **Retry** (FAILED only): Calls `UploadScheduler.enqueue(context, uploadId)` and resets `retryCount = 0` + `status = "READY"` in Room.
- **Cancel** (any non-COMPLETED): Deletes from Room + cancels WorkManager work via `WorkManager.getInstance(context).cancelUniqueWork(uploadId)`.

**Status colors:**
- READY: gray
- UPLOADING: blue (Arctic Sky primary)
- PROCESSING: blue (same, with spinning indicator)
- COMPLETED: green
- FAILED: red (error color)

**Navigation:** New route `UploadQueueRoute`. Added to MainTabsNavHost or navigated from ProfileScreen.

---

## 5. Remove Duplicate Screens

### Problem

Two pairs of duplicate screens exist:
1. `presentation/sessiondetail/SessionDetailScreen` (local VM, IMU charts, export) vs `ui/session/SessionDetailScreen` (shared VM, skeleton overlay, API metrics)
2. `presentation/session/SessionListScreen` (local VM) vs `ui/session/SessionListScreen` (shared VM, filters, pagination)

Navigation is inconsistent — different entry points lead to different screens for the same data.

### Solution

**Delete** the `presentation/` versions and their routes:

**Files to delete:**
- `presentation/sessiondetail/SessionDetailScreen.kt`
- `presentation/sessiondetail/SessionDetailViewModel.kt`
- `presentation/session/SessionListScreen.kt`
- `presentation/session/SessionListViewModel.kt`

**Routes to remove from `Routes.kt`:**
- `SessionDetailRoute` (the local one — not `ResultDetailRoute`)
- `SessionsRoute` (the local one)
- `ExportRoute`

**Remove from `AppNavigation.kt`:**
- `composable<SessionDetailRoute>` block
- `composable<SessionsRoute>` block
- `composable<ExportRoute>` block
- Related imports (`LocalSessionDetailScreen`, `LocalSessionListScreen`, `SessionDetailViewModel`, `SessionListViewModel`, `ExportViewModel`, `ExportScreen`, route imports)

**Keep:** `ui/session/SessionDetailScreen.kt` (shared VM, ExoPlayer + skeleton + metrics), `ui/session/SessionListScreen.kt` (shared VM, filters, pagination).

**RecordingScreen impact:** `RecordingScreen.onRecordingComplete` navigated to `SessionDetailRoute(sessionId)`. Change to navigate to `ResultDetailRoute(sessionId)` (the shared-VM version). If the session isn't processed yet, navigate to `ProcessingRoute(uploadId)` instead.

**MainTabsNavHost:** Already uses the `ui/` versions. The `SessionsRoute` composable in `MainTabsNavHost.kt` uses `AndroidSessionsViewModel` (shared VM) — this stays.

---

## Cross-cutting Concerns

### ProcessingRoute unification

Currently `ProcessingRoute` takes `videoKey` and `sessionId`. This design changes it to take `uploadId`. The screen derives `videoKey` and `sessionId` from the PendingUploadEntity in Room. If the entity is not found (e.g., navigated from deep link or notification), fall back to direct SSE subscription using a sessionId parameter.

### Error handling

- **Upload failed:** ProcessingScreen shows "Ошибка загрузки" with Retry button. Retry re-enqueues UploadWorker.
- **Processing failed (SSE error):** Existing error handling in ProcessingScreen is preserved — shows error with Retry/Back buttons.
- **Video copy failed (gallery):** Show snackbar "Не удалось скопировать видео" on CameraScreen.

### Testing

- **ElementTypeBottomSheet:** Compose UI test — verify radio selection, confirm emits correct type.
- **ProcessingScreen upload phase:** Test Room Flow observation — status transitions READY → UPLOADING → PROCESSING.
- **Gallery upload:** Integration test — pick video, create PendingUpload, verify enqueue.
- **UploadQueueScreen:** Test list rendering, retry action resets status, cancel deletes entity.
- **Duplicate removal:** Verify all navigation paths resolve to `ui/` versions after deletion.
