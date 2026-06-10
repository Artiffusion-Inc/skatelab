# Upload & Processing UX Polish — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 critical bugs in upload pipeline and polish all UX states (progress, empty, error) for the video upload → processing → results flow.

**Architecture:** Fix data flow bugs in UploadWorker/Room, add progress tracking via WorkManager progress reports, redesign ProcessingScreen composable, add empty/error state screens for Progress, Sessions, and Uploads tabs.

**Tech Stack:** Kotlin, Jetpack Compose M3, Room, WorkManager, Ktor SSE

---

## Problem Statement

User uploads a video → screen hangs on "Ready" with no progress → eventually shows "uploaded" in Profile → no analysis runs, nothing in Progress or Sessions tabs.

Root causes:
1. `videoKey` (stored as `r2Key`) is never written to Room after upload — ProcessingScreen gets empty string
2. `sessionId` is not passed when status changes to PROCESSING — UI can't start SSE stream
3. No visual progress feedback during upload — only a spinner

---

## Bug Fixes

### BF-1: Save videoKey to Room after upload

**File:** `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt`

After `chunkedUploader.upload()` returns `videoKey`, save it:

```kotlin
// Step 1.5: Save video key so ProcessingScreen can use it
pendingUploadDao.updateVideoKey(entity.id, videoKey)
```

**File:** `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt`

Add DAO method:
```kotlin
@Query("UPDATE pending_uploads SET videoKey = :videoKey WHERE id = :id")
suspend fun updateVideoKey(id: String, videoKey: String)
```

### BF-2: Pass sessionId with PROCESSING status

**File:** `UploadWorker.kt`

Current (broken):
```kotlin
pendingUploadDao.updateStatus(entity.id, "PROCESSING")  // no sessionId
```

Fixed — move session creation BEFORE status update:
```kotlin
val session = skateLabClient.sessions.create(...)
pendingUploadDao.updateStatus(entity.id, "PROCESSING", session.id)
```

### BF-3: Rename r2Key → videoKey everywhere

Rename field in all files:
- `PendingUploadEntity.kt`: `r2Key` → `videoKey`
- `PendingUploadDao.kt`: any references
- `AndroidProcessingViewModel.kt`: `entity.r2Key` → `entity.videoKey`
- `UploadWorker.kt`: uses new `updateVideoKey()` method
- Room migration: add auto-migration or destructive (dev-only DB)

---

## Upload Progress

### UP-1: WorkManager progress reporting

**File:** `UploadWorker.kt`

Use `setProgressData()` to report upload progress:

```kotlin
override suspend fun doWork(): Result {
    val videoKey = chunkedUploader.upload(
        file = videoFile,
        fileName = videoFile.name,
        contentType = "video/mp4",
        onProgress = { uploaded, total ->
            val percent = (uploaded.toFloat() / total).coerceIn(0f, 1f)
            setProgress(workDataOf(
                KEY_UPLOAD_ID to uploadId,
                KEY_PROGRESS to percent,
                KEY_STATUS to "UPLOADING"
            ))
        }
    )
    setProgress(workDataOf(
        KEY_UPLOAD_ID to uploadId,
        KEY_PROGRESS to 1f,
        KEY_STATUS to "UPLOADED"
    ))
}
```

### UP-2: ProcessingScreen upload progress UI

**File:** `ProcessingScreen.kt`

Replace `UploadStatusContent` spinner with staged progress:

```kotlin
@Composable
private fun UploadStatusContent(entity: PendingUploadEntity) {
    // WorkManager unique work name = "upload-$uploadId"
    // Use getWorkInfosForUniqueWorkFlow to observe progress
    val progress by produceState(0f, entity.id) {
        WorkManager.getInstance(context)
            .getWorkInfosForUniqueWorkFlow("upload-${entity.id}")
            .collect { workInfos ->
                val info = workInfos.firstOrNull()
                value = info?.progress?.getFloat(KEY_PROGRESS, 0f) ?: 0f
            }
    }

    val statusLabel = when (entity.status) {
        "READY" -> stringResource(R.string.upload_status_ready)
        "UPLOADING" -> stringResource(R.string.upload_status_uploading)
        "PROCESSING" -> stringResource(R.string.upload_status_processing)
        else -> entity.status
    }

    LinearProgressIndicator(
        progress = { progress },
        modifier = Modifier.fillMaxWidth().testTag("uploadProgress"),
    )
    Spacer(Modifier.height(16.dp))
    Text(statusLabel, style = MaterialTheme.typography.bodyLarge)
    if (progress > 0f) {
        Text("${(progress * 100).toInt()}%", style = MaterialTheme.typography.headlineMedium)
    }
}
```

### UP-3: Processing phase progress UI (SSE)

Already implemented in `ProcessingContent` — `LinearProgressIndicator` with percent + message. Keep as-is, but add stage labels:

```kotlin
is ProcessingUiState.Progress -> {
    val stageLabel = when {
        state.percent < 0.1f -> "Queuing..."
        state.percent < 0.7f -> "Processing video..."
        state.percent < 0.9f -> "Computing metrics..."
        else -> "Finishing up..."
    }
    LinearProgressIndicator(progress = { state.percent }, ...)
    Text(stageLabel, style = MaterialTheme.typography.bodyLarge)
    Text("${(state.percent * 100).toInt()}%", style = MaterialTheme.typography.headlineMedium)
}
```

---

## Empty States

### ES-1: Progress tab empty state

**New composable** in `DashboardScreen.kt` or dedicated file:

When no sessions with status `PROCESSING` or `QUEUED` exist:
- Illustration icon (CloudUpload or similar Material icon)
- Headline: "No active processing"
- Body: "Upload a video from the Camera tab to start analysis"
- CTA button: "Go to Camera" → navigates to Camera tab

### ES-2: Sessions tab empty state

**Existing file:** `SessionListScreen.kt`

When no completed sessions:
- Illustration icon (Sports or similar)
- Headline: "No sessions yet"
- Body: "Your analyzed skating sessions will appear here"
- No CTA (Sessions is passive — user goes to Camera to create content)

### ES-3: Uploads empty state polish

**Existing file:** `UploadQueueScreen.kt`

Current "No uploads" text → expand to:
- Icon: CloudOff or similar
- Headline: "No uploads"
- Body: "Videos you upload will appear here for processing"
- Subtitle with pending count when there are queued items

---

## Error States

### ER-1: Upload network error

**File:** `UploadWorker.kt`

Already has retry logic (3 retries with exponential backoff). After 3 failures → status `FAILED`.

**File:** `ProcessingScreen.kt` — `UploadFailedContent` already exists with retry/back buttons. Polish:
- Show specific error type: "No internet connection" vs "Server error"
- Network error icon → `Icons.Default.CloudOff`
- Server error icon → `Icons.Default.ErrorOutline`
- Already partially implemented — ensure `AppError.Network` / `AppError.Timeout` vs other errors handled

### ER-2: Processing server error

**File:** `ProcessingScreen.kt` — `ProcessingContent` Failed state already shows error + retry/back. Enhance:
- Show server error message if available (from SSE event)
- Add "Try again" button that re-queues processing
- Add "Go back" button that returns to Camera tab

### ER-3: Stuck upload detection

**File:** `UploadWorker.kt` or new `UploadMonitorWorker`

If status stays `READY` for > 5 minutes (WorkManager constraints not met) or `UPLOADING` for > 30 minutes (stuck transfer):

In `UploadQueueScreen`:
- Show "Upload paused" label with explanation
- Add "Resume" button that re-enqueues with relaxed constraints
- Add "Cancel" button that deletes the upload

In `ProcessingScreen`:
- If `READY` status persists > 30 seconds, show "Waiting for network..." hint
- If `UPLOADING` progress stalls for > 60 seconds, show "Upload may be paused" hint

Implementation: Add `createdAt` timestamp to entity (already exists). In UploadQueueScreen, calculate elapsed time and show appropriate hint.

### ER-4: Invalid video error

**File:** `CameraViewModel.kt` — `createGalleryUpload()`

Before creating PendingUploadEntity:
1. Check file size ≤ max (100 MB configurable)
2. Check file extension is `.mp4` or `.mov`
3. If invalid → show error snackbar with clear message

Add validation function:
```kotlin
private fun validateVideoFile(path: String): String? {
    val file = File(path)
    if (!file.exists()) return "File not found"
    if (file.extension.lowercase() !in listOf("mp4", "mov", "3gp", "webm"))
        return "Unsupported format: .${file.extension}. Use MP4 or MOV."
    if (file.length() > 100 * 1024 * 1024)
        return "File too large (${file.length() / 1024 / 1024} MB). Max 100 MB."
    return null  // valid
}
```

Call in `createGalleryUpload()` — if validation fails, set `_galleryUploadError` and show snackbar.

---

## Room Migration

Add auto-migration for `r2Key` → `videoKey` rename:

**File:** `AppDatabase.kt`

Increment version, add migration:
```kotlin
val MIGRATION_R2KEY_TO_VIDEOKEY = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE pending_uploads ADD COLUMN videoKey TEXT")
        db.execSQL("UPDATE pending_uploads SET videoKey = r2Key")
        // Can't drop column in SQLite < 3.35, r2Key stays but unused
    }
}
```

Or use Room auto-migration if version supports it.

---

## String Resources

Add to `strings.xml`:
- `upload_status_ready` — "Preparing upload..."
- `upload_status_uploading` — "Uploading video..."
- `upload_status_processing` — "Starting analysis..."
- `upload_paused` — "Upload paused"
- `upload_waiting_network` — "Waiting for network..."
- `upload_file_too_large` — "File too large (%1$d MB). Max %2$d MB."
- `upload_unsupported_format` — "Unsupported format. Use MP4 or MOV."
- `empty_progress_title` — "No active processing"
- `empty_progress_body` — "Upload a video from the Camera tab to start analysis"
- `empty_sessions_title` — "No sessions yet"
- `empty_sessions_body` — "Your analyzed skating sessions will appear here"
- `empty_uploads_body` — "Videos you upload will appear here for processing"