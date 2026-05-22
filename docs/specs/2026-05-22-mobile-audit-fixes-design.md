# Mobile Audit Fixes — Design Spec

Date: 2026-05-22
Branch: docs/claude-md-cleanup (audit), implementation TBD
Scope: P0-P3 bug fixes + missing backend integrations

## Overview

Comprehensive fix plan for the KMP mobile app based on code audit. 5 critical, 8 high, 12 medium bugs, plus 4 groups of missing backend integrations.

Research agent findings incorporated: Ktor Auth plugin (C1), Ktor SSE plugin (C5), multiplatform-settings KeychainSettings (C3), HttpRequestRetry API corrections (H7), retry-before-timeout ordering (H7→H8), auto-reconnect preservation (H2), PendingUploadDao status values (M9), ImuStreamWriter fsync (M4).

## 1. Auth Fixes (P0)

### C1 — Replace AuthInterceptor with Ktor Auth Plugin

**Problem:** Custom `AuthInterceptor` has race condition on concurrent 401s. Mutex-based fix adds complexity and still requires manual retry logic.

**Fix:** Use Ktor Auth plugin with `BearerAuthProvider` — built-in concurrent 401 deduplication and automatic retry.

```kotlin
// SkateLabClient.kt — replace AuthInterceptor with Auth plugin
install(Auth) {
    bearer {
        loadTokens {
            val access = tokenStorage.getAccessToken() ?: return@loadTokens null
            val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
            BearerTokens(access, refresh)
        }
        refreshTokens {
            val refreshToken = tokenStorage.getRefreshToken() ?: return@refreshTokens null
            runCatching {
                authApi.refresh(refreshToken)
            }.onSuccess { response ->
                tokenStorage.saveTokens(response.accessToken, response.refreshToken)
            }.onFailure {
                tokenStorage.clearTokens()  // C2 fix: clear on failure
            }.getOrNull()?.let {
                BearerTokens(it.accessToken, it.refreshToken)
            }
        }
    }
}
```

**Delete** `AuthInterceptor.kt` entirely — Ktor Auth plugin handles everything (token injection, 401 detection, refresh, retry).

**Test:** `AuthRepositoryTest` — concurrent 401s → single refresh, token corruption prevention. `SkateLabClientTest` — 401 → auto-refresh → retry.

### C2 — Clear Tokens on Refresh Failure

**Problem:** `refreshIfNeeded()` returns null on failure but doesn't clear stale tokens. User stays "logged in" with invalid tokens → infinite 401 loop.

**Fix:** Clear both tokens on refresh failure (shown in C1 code above — `onFailure { tokenStorage.clearTokens() }` in `refreshTokens` block).

**Test:** `AuthRepositoryTest` — refresh failure clears tokens, UI shows login screen.

### C3 — iOS TokenStorage via multiplatform-settings KeychainSettings

**Problem:** `IosTokenStorage` stores JWT in `NSUserDefaults` (plaintext). When iOS launches, tokens are exposed.

**Fix:** Use `multiplatform-settings` with `KeychainSettings` — cross-platform API, iOS uses Keychain automatically.

Add dependency in `shared/build.gradle.kts`:
```kotlin
commonMain {
    implementation("com.russhwolf:multiplatform-settings:1.3.0")
}
iosMain {
    implementation("com.russhwolf:multiplatform-settings-keychain:1.3.0")
}
```

```kotlin
// shared/src/commonMain — expect declaration
expect val settings: Settings

// shared/src/iosMain
actual val settings: Settings by lazy { KeychainSettings(service = "ru.skatelab.auth") }

// TokenStorage — now platform-agnostic
class TokenStorage(private val settings: Settings) {
    suspend fun saveAccessToken(token: String) { settings.putString("access_token", token) }
    suspend fun getAccessToken(): String? = settings.getStringOrNull("access_token")
    suspend fun saveRefreshToken(token: String) { settings.putString("refresh_token", token) }
    suspend fun getRefreshToken(): String? = settings.getStringOrNull("refresh_token")
    suspend fun clearTokens() { settings.remove("access_token"); settings.remove("refresh_token") }
}
```

**Delete** manual cinterop code in `IosTokenStorage.kt`. Remove `iosSecurity` framework dependency — `KeychainSettings` handles it internally.

**Test:** `IosTokenStorageTest` (iosTest) — save, get, clear roundtrip. Verify Keychain usage via device console.

### C4 — Call `/auth/logout` on Sign-Out

**Problem:** Mobile only clears local storage on logout. Backend refresh token stays valid → token reuse vulnerability.

**Fix:**
```kotlin
suspend fun logout() {
    runCatching { authApi.logout() }  // Best-effort — network failures shouldn't block logout
    tokenStorage.clearTokens()
}
```

Add `logout()` to `AuthApi.kt`:
```kotlin
suspend fun logout() {
    client.post("${baseUrl}/auth/logout")
}
```

**Test:** `AuthApiTest` — logout sends POST, `AuthRepositoryTest` — logout clears tokens even if API fails.

---

## 2. Network Resilience (P1)

### H7 — Retry with Exponential Backoff

**Problem:** Ktor client has no retry. Transient network failures (mobile, elevator, tunnel) cause immediate failure.

**Fix:** Add `HttpRequestRetry` plugin to `SkateLabClient`. Use KMP-compatible exception types (not JVM-specific).

```kotlin
install(HttpRequestRetry) {
    maxRetries = 3
    retryIf { request, response ->
        response.status.value.let { it >= 500 || it == 429 }
    }
    retryOnExceptionIf { request, cause ->
        cause is io.ktor.client.network.sockets.SocketTimeoutException ||
        cause is io.ktor.client.plugins.HttpRequestTimeoutException ||
        cause is io.ktor.utils.io.errors.IOException
    }
    exponentialDelay(
        base = 2.0,           // 2^n: 500ms, 1s, 2s, 4s, 8s
        baseDelayMs = 500,
        maxDelayMs = 8_000,
        respectRetryAfter = true  // Honor Retry-After header for 429
    )
}
```

**Not retried:** 401 (handled by Ktor Auth plugin), 4xx client errors.

**CRITICAL: Install order matters** — `HttpRequestRetry` MUST be installed BEFORE `HttpTimeout` so retries execute before timing out.

### H8 — Timeout Configuration

**Problem:** Default Ktor timeouts are too long for mobile (60s+). User sees frozen UI on bad connections.

**Fix:** Configure `HttpTimeout` plugin. Install AFTER `HttpRequestRetry`.

```kotlin
// Install AFTER HttpRequestRetry — ordering matters
install(HttpTimeout) {
    connectTimeoutMillis = 10_000   // 10s to establish connection
    requestTimeoutMillis = 30_000    // 30s for full request
    socketTimeoutMillis = 15_000     // 15s between data chunks
}
```

Upload endpoint gets longer timeouts:
```kotlin
// In UploadsApi, override per-request:
client.put(url) {
    timeout { requestTimeoutMillis = 120_000 }  // 2min for large uploads
}
```

---

## 3. UI Error Handling (P1)

### H5 — Propagate Errors in SessionsViewModel

**Problem:** `loadSession(id)` catches and swallows all exceptions.

**Fix:**
```kotlin
suspend fun loadSession(id: String) {
    _selectedSession.value = null
    try {
        _selectedSession.value = sessionsApi.get(id)
    } catch (e: Exception) {
        _uiState.value = SessionsUiState.Error(e.message ?: "Failed to load session")
    }
}
```

### H6 — Load User Profile After Login

**Problem:** After login, `AuthViewModel.checkLogin()` sets `AuthUiState.LoggedIn("cached", null)` with hardcoded placeholder and no display name.

**Fix:** After successful login/register, fetch user profile.

```kotlin
suspend fun login(email: String, password: String) {
    _uiState.value = AuthUiState.Loading
    authRepo.login(email, password)
        .onSuccess { token ->
            val user = usersApi.getProfile()  // Fetch actual profile
            _uiState.value = AuthUiState.LoggedIn(user.id, user.displayName)
        }
        .onFailure { e ->
            _uiState.value = AuthUiState.Error(e.message ?: "Login failed")
        }
}
```

Add `UsersApi` dependency to `AuthViewModel`.

### C5 — Replace Manual SSE Parser with Ktor SSE Plugin

**Problem:** `ProcessApi.stream()` uses manual line-by-line parsing. Doesn't handle comment lines (`:`), empty lines, multi-line data, or reconnection. Current `callbackFlow` reads one line and exits — doesn't loop.

**Fix:** Use Ktor SSE plugin — built-in comment/empty line handling, auto-reconnect, proper event parsing.

Add dependency in `shared/build.gradle.kts`:
```kotlin
commonMain {
    implementation("io.ktor:ktor-client-sse:3.1.3")
}
```

```kotlin
// SkateLabClient.kt
install(SSE) {
    reconnectionTime = 5000  // Auto-reconnect on disconnect
}

// ProcessApi.kt
suspend fun stream(taskId: String): Flow<ProcessEvent> = callbackFlow {
    client.sse("$baseUrl/process/$taskId/stream") {
        events.collect { event ->
            val data = event.data ?: return@collect
            val processEvent = Json.decodeFromString<ProcessEvent>(data)
            trySend(processEvent)
        }
    }
    awaitClose()
}
```

**Delete** manual line-by-line parsing code. Ktor SSE handles: comment lines, empty lines, multi-line `data:` fields, `event:`/`id:` fields, auto-reconnect.

**Test:** `ProcessApiTest` — comment lines, empty lines, multi-line data, reconnection.

### H4 — UploadWorker Race Condition

**Problem:** Multiple workers can process the same pending upload simultaneously.

**Fix:** Use `UniqueWorkPolicy.KEEP` for scheduling + database-level locking.

```kotlin
// UploadScheduler.kt
fun scheduleUpload(sessionId: String) {
    val request = OneTimeWorkRequestBuilder<UploadWorker>()
        .setInputData(workDataOf("sessionId" to sessionId))
        .build()

    WorkManager.getInstance(context)
        .enqueueUniqueWork(
            "upload-$sessionId",          // Unique per session
            ExistingWorkPolicy.KEEP,       // Don't re-enqueue if running
            request
        )
}
```

In `UploadWorker`, add row-level lock:
```kotlin
@WorkerThread
private fun processUpload(sessionId: String): Result {
    val entity = pendingUploadDao.getAndLock(sessionId) ?: return Result.success()
    // ... upload logic
}
```

Add `getAndLock()` DAO method that sets `status = UPLOADING` atomically.

---

## 4. BLE / Camera / Data Stability (P2+P3)

### H1 — BleManager Thread Safety

**Problem:** `parsers` ConcurrentHashMap accessed from Binder thread and workHandler thread without synchronization.

**Fix:** Use `ConcurrentHashMap.computeIfAbsent()` instead of `getOrPut()`:
```kotlin
// BleManager.kt line 384
val parser = parsers.computeIfAbsent(sensorId) { Wt901Parser(it) }
```

Also fix `addressToSensorId` access — make it `ConcurrentHashMap` and use `getOrDefault()`:
```kotlin
val sensorId = addressToSensorId[address] ?: return@onCharacteristicChanged
```

### H2 — KableBleRepository Job Accumulation (Corrected)

**Problem:** `stateMonitorJob` not cancelled on successful connect.

**Fix:** ONLY cancel `reconnectJobs`. Do NOT cancel `stateMonitorJobs` — they detect disconnections and trigger auto-reconnect. Cancelling them breaks the auto-reconnect mechanism.

```kotlin
suspend fun connect(sensorId: String, address: String): Result<Unit> {
    // ... existing connection logic
    reconnectJobs[sensorId]?.cancel()  // Cancel reconnect attempts (connection succeeded)
    // stateMonitorJobs[sensorId] stays running — monitors for future disconnections
}
```

**Future:** Consider migrating to Kable 0.35+ which provides connection-scoped coroutines via `peripheral.connect()` returning `CoroutineScope`. This would eliminate manual job management entirely.

### H3 — CameraXRecorder Resource Leak

**Problem:** If `start()` fails, `timestampTracker` is never closed.

**Fix:**
```kotlin
fun start(outputPath: String): Result<Unit> {
    return try {
        val pendingRecording = recorder.createRecording(...)
        timestampTracker = FrameTimestampTracker(outputPath.replace(".mp4", "_timestamps.csv"))
        pendingRecording.start()
        Result.success(Unit)
    } catch (e: Exception) {
        timestampTracker?.close()
        timestampTracker = null
        Result.failure(e)
    }
}
```

### M1 — Wt901Parser Frame Stats Reset

Add `reset()` method and call it from `ImuCollector.startStreaming()`:
```kotlin
fun reset() {
    frameCounts.clear()
    logSeq.clear()
}
```

### M2 — FrameTimestampTracker Queue Offer

Check `offer()` return value:
```kotlin
if (!queue.offer(frameData)) {
    Log.w(TAG, "Timestamp queue full, dropping frame ${frameData.frameIndex}")
}
```

### M3 — ImuCollector Write Error Notification

Propagate write errors to UI via `StateFlow`:
```kotlin
private val _writeError = MutableStateFlow<Throwable?>(null)
val writeError: StateFlow<Throwable?> = _writeError.asStateFlow()

// In write loop:
catch (e: Exception) {
    _writeError.value = e
}
```

### M4 — ImuStreamWriter Flush/Close (Corrected)

**Current code** already has `fsync` via `fd.sync()`. Fix: ensure `close()` always runs even if `flush()` throws, and null refs first to prevent double-close.

```kotlin
fun close() {
    val fos = fileOutputStream
    fileOutputStream = null  // Null first — prevents double-close
    val fd = fileDescriptor
    fileDescriptor = null
    try {
        fos?.flush()
        fd?.sync()            // fsync to disk
    } finally {
        fos?.close()
    }
}
```

### M5 — SessionRepositoryImpl Null Logging

Log warning instead of silent null:
```kotlin
private fun jsonToSession(json: String, file: File): CaptureSession? {
    return try {
        Json.decodeFromString<CaptureSession>(json)
    } catch (e: Exception) {
        logger.w("SessionRepository", "Failed to parse session from ${file.name}: ${e.message}")
        null
    }
}
```

### M6 — RecordingViewModel runBlocking

Replace `runBlocking(Dispatchers.IO)` in `onCleared()` with structured cleanup:
```kotlin
override fun onCleared() {
    super.onCleared()
    // Cancel all jobs — they handle cleanup in their finally blocks
    cameraJob?.cancel()
    reconnectJob?.cancel()
    batteryJob?.cancel()
    timerJob?.cancel()
    runBlocking { cameraRepository.release() }  // Last-resort blocking for cleanup
}
```

This is acceptable in `onCleared()` since the ViewModel is being destroyed. Document the pattern.

### M7 — SensorRecordingService Lifecycle

Use `START_NOT_STICKY` instead of `START_STICKY` for foreground service that should die with the app:
```kotlin
return START_NOT_STICKY
```

### M8 — Room Schema Export

Enable schema export for migration tracking:
```kotlin
@Database(
    entities = [CachedSessionEntity::class, PendingUploadEntity::class],
    version = 1,
    exportSchema = true  // Changed from false
)
```

Add to `build.gradle.kts`:
```kotlin
ksp {
    arg("room.schemaLocation", "${projectDir}/schemas")
}
```

### M9 — PendingUploadDao Race (Corrected)

Add `@Transaction` + conditional UPDATE for optimistic locking. Use `status = 'READY'` (actual enum value in `PendingUploadEntity`), not `'PENDING'`.

```kotlin
@Transaction
@Query("UPDATE pending_uploads SET status = 'UPLOADING' WHERE id = :id AND status = 'READY'")
suspend fun tryLockForUpload(id: String): Int  // Returns rows affected (1 = locked, 0 = already taken)

@Query("SELECT * FROM pending_uploads WHERE id = :id LIMIT 1")
suspend fun getById(id: String): PendingUploadEntity?
```

Usage in `UploadWorker`:
```kotlin
val locked = pendingUploadDao.tryLockForUpload(sessionId)
if (locked == 0) return Result.success()  // Another worker already processing
val entity = pendingUploadDao.getById(sessionId) ?: return Result.success()
```

### M10 — ZipExporter Partial ZIP

Use atomic file write:
```kotlin
fun export(session: CaptureSession, outputStream: OutputStream) {
    val tempFile = File(outputPath + ".tmp")
    try {
        ZipOutputStream(BufferedOutputStream(FileOutputStream(tempFile))).use { zipOut ->
            // ... write entries
        }
        tempFile.renameTo(File(outputPath))  // Atomic on POSIX
    } catch (e: Exception) {
        tempFile.delete()
        throw e
    }
}
```

### M11 — ProcessingViewModel taskId vs sessionId

Fix: emit `sessionId` from `ProcessEvent.COMPLETED` instead of `taskId`:
```kotlin
ProcessStatus.COMPLETED -> {
    val sessionId = event.sessionId  // Backend must return sessionId in SSE event
    _uiState.value = ProcessingUiState.Completed(sessionId)
}
```

Verify backend `ProcessEvent` includes `sessionId` field. If not, add it to `ProcessEvent.kt`:
```kotlin
@Serializable
data class ProcessEvent(
    val task_id: String,
    val status: ProcessStatus,
    val progress: Double? = null,
    val error: String? = null,
    val session_id: String? = null  // New field
)
```

### M12 — BleScanViewModel isScanning StateFlow

Convert to `MutableStateFlow<Boolean>`:
```kotlin
private val _isScanning = MutableStateFlow(false)
val isScanning: StateFlow<Boolean> = _isScanning.asStateFlow()
```

---

## 5. New Features — Missing Backend Integrations

### 5.1 — Email Verification

**Backend endpoints:** `/auth/verify-email`, `/auth/resend-verification`

**Shared module additions:**
```kotlin
// AuthApi.kt
suspend fun verifyEmail(token: String): Result<Unit>
suspend fun resendVerification(email: String): Result<Unit>

// AuthRepository.kt
suspend fun verifyEmail(token: String): Result<Unit>
suspend fun resendVerification(email: String): Result<Unit>
```

**Android UI:** Add `VerifyEmailScreen` composable with deep link handling. After register, show "Check your email" screen with resend button.

**Flow:**
1. User registers → `AuthUiState.NeedsVerification(email)`
2. User clicks email link → deep link opens app → `verifyEmail(token)`
3. On success → `AuthUiState.LoggedIn`

### 5.2 — Password Reset

**Backend endpoints:** `/auth/forgot-password`, `/auth/reset-password`

**Shared module additions:**
```kotlin
// AuthApi.kt
suspend fun forgotPassword(email: String): Result<Unit>
suspend fun resetPassword(token: String, newPassword: String): Result<Unit>
```

**Android UI:** `ForgotPasswordScreen` + `ResetPasswordScreen`. Link from `LoginScreen`.

**Flow:**
1. User taps "Forgot password" → enter email → `forgotPassword(email)`
2. Email sent → show confirmation
3. Deep link → `resetPassword(token, newPassword)`

### 5.3 — Session CRUD

**Backend endpoints:** `PATCH /sessions/{id}`, `DELETE /sessions/{id}`, `DELETE /sessions/bulk`

**Shared module additions:**
```kotlin
// SessionsApi.kt
suspend fun update(id: String, request: SessionUpdateRequest): Result<SessionResponse>
suspend fun delete(id: String): Result<Unit>
suspend fun bulkDelete(ids: List<String>): Result<Unit>
```

**Models:**
```kotlin
@Serializable
data class SessionUpdateRequest(
    val element_type: String? = null,
    val notes: String? = null
)
```

**Android UI:** Add delete button to `SessionDetailScreen`, multi-select delete in `SessionListScreen`.

### 5.4 — Metrics API

**Backend endpoints:** `/metrics/registry`, `/metrics/trend`, `/metrics/prs`, `/metrics/diagnostics`, `/metrics/summary`

**Shared module additions:**
```kotlin
// MetricsApi.kt (new file)
class MetricsApi(private val client: HttpClient, private val baseUrl: String) {
    suspend fun getRegistry(): Result<MetricsRegistryResponse>
    suspend fun getTrend(metricId: String, period: String?): Result<TrendResponse>
    suspend fun getPersonalRecords(): Result<PRsResponse>
    suspend fun getDiagnostics(sessionId: String): Result<DiagnosticsResponse>
    suspend fun getSummary(): Result<SummaryResponse>
}
```

**Models:** Match backend `schemas.py` response models.

**Android UI:** `MetricsScreen` with tabs (Summary, Trends, PRs). Show metric registry, trends chart, personal records.

### 5.5 — Cancel Processing

**Backend endpoint:** `POST /process/{id}/cancel`

**Shared module additions:**
```kotlin
// ProcessApi.kt
suspend fun cancel(taskId: String): Result<Unit>
```

**Android UI:** Add "Cancel" button in `ProcessingScreen`. On cancel, show confirmation dialog, then call `processApi.cancel(taskId)`.

---

## 6. Parallelization Strategy

### Thread Assignment

Up to 5 concurrent threads across 3 phases:

| Thread | Area | Phase 1 (Auth) | Phase 2 (Network) | Phase 3 (Data+Features) |
|--------|------|----------------|--------------------|------------------------|
| T1 | Auth | C1 (Ktor Auth), C2, C4 | — | 5.1 Email verify, 5.2 Password reset |
| T2 | Network | — | H7 (Retry), H8 (Timeout), H7→H8 ordering | C5 (SSE), 5.5 Cancel processing |
| T3 | UI/VM | — | H5, H6 | H4 (UploadWorker), M11 |
| T4 | BLE/Camera | — | H1, H2, H3 | M1-M8, M9-M12 |
| T5 | iOS + New APIs | C3 (Keychain) | — | 5.3 Session CRUD, 5.4 Metrics API |

### Dependencies

- C1 (Ktor Auth) blocks T1 Phase 2+ work (Auth must be stable first)
- H7→H8 ordering: Retry installed before Timeout (same `SkateLabClient.kt` file → single thread T2)
- C5 (SSE) depends on H7 (retry) — same thread T2
- M9 depends on H4 (UploadWorker uses DAO lock) — T3 then T4
- iOS C3 independent — T5 can start immediately

### Critical Ordering

1. **C1 → everything**: Ktor Auth plugin replaces AuthInterceptor — all API calls depend on this
2. **H7 before H8**: `install(HttpRequestRetry)` before `install(HttpTimeout)` — file ordering
3. **C5 after H7**: SSE plugin needs retry for reconnection resilience

---

## 7. Test Plan

### Unit Tests to Add

| Area | Test | Priority |
|------|------|----------|
| Auth | `Ktor Auth plugin concurrent 401s` — verify single refresh | P0 |
| Auth | `AuthRepository refresh failure clears tokens` | P0 |
| Auth | `AuthRepository logout calls API then clears` | P0 |
| Auth | `AuthApi.logout()` — request serialization | P0 |
| SSE | `ProcessApi stream via SSE plugin` — comments, empty lines, multi-line data | P1 |
| Upload | `UploadWorker unique work` — no duplicate processing | P1 |
| Upload | `PendingUploadDao.tryLockForUpload` — WHERE status='READY' | P1 |
| API | `SkateLabClient retry on 5xx` — 3 retries then fail | P1 |
| API | `SkateLabClient timeout` — connect, request, socket | P1 |
| Models | `SessionUpdateRequest serialization` | P2 |
| Models | `MetricsRegistryResponse parsing` | P2 |
| Models | `ProcessEvent with sessionId` — backward compat | P2 |
| Auth | `Email verification deep link` — token parsing | P2 |
| Auth | `Password reset flow` — token + new password | P2 |

### Integration Test Priorities

| Flow | What to verify |
|------|---------------|
| Login → 401 → Ktor Auth refresh → retry | Full auth recovery (plugin-managed) |
| Login → refresh fails → tokens cleared → logout | Token clearing |
| Upload → 429 → backoff → success | Rate limit recovery |
| SSE stream → completed → navigate | Full processing flow |
| BLE connect → disconnect → auto-reconnect | Sensor lifecycle (stateMonitorJob preserved) |

### Instrumented Tests

| Test | What to verify |
|------|---------------|
| `LoginScreen → enter credentials → tap login → navigate to camera` | Auth flow |
| `SessionList → swipe to delete → confirm` | Session CRUD |
| `ProcessingScreen → cancel button → confirmation → status updates` | Cancel processing |

---

## 8. Implementation Order

Phase 1 — Auth (blocks everything else):
1. C1: Ktor Auth plugin (replace AuthInterceptor)
2. C2: Clear tokens on refresh failure (in Ktor Auth refreshTokens block)
3. C4: Call `/auth/logout`

Phase 2 — Network resilience:
4. H7: HttpRequestRetry with exponential backoff (install BEFORE H8)
5. H8: HttpTimeout configuration (install AFTER H7)
6. C5: Ktor SSE plugin (replace manual parser)

Phase 3 — UI error handling:
7. H5: SessionsViewModel error propagation
8. H6: Load profile after login
9. H4: UploadWorker race fix (enqueueUniqueWork + tryLockForUpload)
10. M11: ProcessingViewModel sessionId

Phase 4 — Data stability:
11. H1: BleManager thread safety
12. H2: KableBleRepository — cancel reconnectJobs only, preserve stateMonitorJobs
13. H3: CameraXRecorder try-finally
14. M1-M12: All medium fixes

Phase 5 — iOS:
15. C3: multiplatform-settings KeychainSettings

Phase 6 — New features:
16. Email verification
17. Password reset
18. Session CRUD
19. Metrics API
20. Cancel processing

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Ktor Auth plugin migration breaks existing login flow | Medium | High | Comprehensive auth tests before merge; delete AuthInterceptor only after tests pass |
| SSE plugin API mismatch with backend SSE format | Low | High | Test with real SSE stream; verify backend sends standard SSE format |
| BLE thread safety fix introduces new race | Low | Medium | BLE unit tests with concurrent access |
| KeychainSettings availability on older iOS | Low | Low | Min iOS 15+, Keychain available since iOS 2 |
| Retry backoff causes UI sluggishness | Low | Medium | Cancel retry on ViewModel clear |
| HttpRequestRetry before HttpTimeout ordering | Medium | High | Add code comment + build-time check if possible |
| New API endpoints don't match backend yet | Medium | Medium | Verify against backend schemas.py before implementing |
| Cancelling stateMonitorJob breaks auto-reconnect | High | High | Only cancel reconnectJobs; stateMonitorJob stays running |
| PendingUploadDao status mismatch | Medium | Medium | Use 'READY' not 'PENDING' per actual entity enum |