# Mobile Audit Fixes — Design Spec

Date: 2026-05-22
Branch: docs/claude-md-cleanup (audit), implementation TBD
Scope: P0-P3 bug fixes + missing backend integrations

## Overview

Comprehensive fix plan for the KMP mobile app based on code audit. 5 critical, 8 high, 12 medium bugs, plus 4 groups of missing backend integrations.

## 1. Auth Fixes (P0)

### C1 — AuthInterceptor Race Condition

**Problem:** Multiple concurrent 401 responses trigger parallel `refreshIfNeeded()` calls. Tokens overwrite each other, user loses auth.

**Current code** (`shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthInterceptor.kt`):
```kotlin
onResponse { response ->
    if (response.status == HttpStatusCode.Unauthorized) {
        repo.refreshIfNeeded()  // No lock — concurrent calls corrupt tokens
    }
}
```

**Fix:** Add `Mutex`-based refresh lock in `AuthRepository`. First 401 acquires lock and refreshes. Subsequent 401s wait for the same refresh result.

```kotlin
class AuthRepository(private val authApi: AuthApi, private val tokenStorage: TokenStorage) {
    private val refreshMutex = Mutex()
    private var lastRefreshResult: Result<String?>? = null

    suspend fun refreshIfNeeded(): String? = refreshMutex.withLock {
        // Check if tokens were already refreshed by another coroutine
        val currentToken = tokenStorage.getAccessToken()
        if (currentToken != null && !isTokenExpired(currentToken)) {
            return currentToken
        }
        val refresh = tokenStorage.getRefreshToken() ?: return null
        runCatching { authApi.refresh(refresh) }
            .onSuccess { tokenStorage.saveTokens(it.accessToken, it.refreshToken) }
            .onFailure {
                tokenStorage.clearTokens()  // C2 fix: clear on failure
            }
            .getOrNull()
            ?.accessToken
    }
}
```

**Interceptor update:**
```kotlin
onResponse { response ->
    if (response.status == HttpStatusCode.Unauthorized) {
        val newToken = repo.refreshIfNeeded()
        if (newToken != null) {
            // Retry original request with new token
            return@onResponse response.request.newBuilder()
                .header("Authorization", "Bearer $newToken")
                .build()
        }
    }
}
```

**Test:** `AuthRepositoryTest` — concurrent 401s, single refresh call, token corruption prevention.

### C2 — Clear Tokens on Refresh Failure

**Problem:** `refreshIfNeeded()` returns null on failure but doesn't clear stale tokens. User stays "logged in" with invalid tokens → infinite 401 loop.

**Fix:** Clear both tokens on refresh failure (shown in C1 code above — `onFailure { tokenStorage.clearTokens() }`).

**Test:** `AuthRepositoryTest` — refresh failure clears tokens, UI shows login screen.

### C3 — iOS TokenStorage Encryption

**Problem:** `IosTokenStorage` stores JWT in `NSUserDefaults` (plaintext). When iOS launches, tokens are exposed.

**Current code** (`shared/src/iosMain/kotlin/ru/skatelab/shared/auth/IosTokenStorage.kt`):
```kotlin
actual class TokenStorage {
    private val defaults = NSUserDefaults.standardUserDefaults
    // Tokens stored as plaintext strings
}
```

**Fix:** Use iOS Keychain via platform-specific implementation.

```kotlin
actual class TokenStorage {
    private val keychain = Keychain()

    actual suspend fun saveAccessToken(token: String) {
        keychain.set(token, Key.ACCESS_TOKEN)
    }

    actual suspend fun getAccessToken(): String? {
        return keychain.get(Key.ACCESS_TOKEN)
    }

    actual suspend fun clearTokens() {
        keychain.delete(Key.ACCESS_TOKEN)
        keychain.delete(Key.REFRESH_TOKEN)
    }

    private object Key {
        const val ACCESS_TOKEN = "ru.skatelab.auth.access_token"
        const val REFRESH_TOKEN = "ru.skatelab.auth.refresh_token"
    }
}
```

Implementation uses `Security` framework (`SecItemAdd`/`SecItemCopyMatching`/`SecItemDelete`) via `kotlinx.cinterop`. Add `iosSecurity` framework dependency in `shared/build.gradle.kts`.

**Test:** `IosTokenStorageTest` (iosTest) — save, get, clear roundtrip.

### C4 — Call `/auth/logout` on Sign-Out

**Problem:** Mobile only clears local storage on logout. Backend refresh token stays valid → token reuse vulnerability.

**Current code** (`shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt`):
```kotlin
suspend fun logout() {
    tokenStorage.clearTokens()
    // No API call to revoke token on server
}
```

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

**Fix:** Add `HttpRequestRetry` plugin to `SkateLabClient`.

```kotlin
install(HttpRequestRetry) {
    maxRetries = 3
    retryIf { request, response ->
        response.status.value.let { it >= 500 || it == 429 }
    }
    retryOnExceptionIf { request, cause ->
        cause is java.net.SocketTimeoutException ||
        cause is java.net.UnknownHostException ||
        cause is java.io.IOException
    }
    exponentialDelay(
        base = 1.0,
        maxDelay = 8.0,
        respectRetryAfter = true  // Honor Retry-After header for 429
    )
}
```

**Not retried:** 401 (handled by AuthInterceptor), 4xx client errors.

### H8 — Timeout Configuration

**Problem:** Default Ktor timeouts are too long for mobile (60s+). User sees frozen UI on bad connections.

**Fix:** Configure `HttpTimeout` plugin.

```kotlin
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

**Current code** (`shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt`):
```kotlin
suspend fun loadSession(id: String) {
    try {
        _selectedSession.value = sessionsApi.get(id)
    } catch (_: Exception) { }  // Empty catch
}
```

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

### C5 — SSE Stream Parsing

**Problem:** `ProcessApi.stream()` doesn't handle SSE comment lines (`:`) or empty lines.

**Fix:** Filter lines before parsing:
```kotlin
suspend fun stream(taskId: String): Flow<ProcessEvent> = callbackFlow {
    client.get("$baseUrl/process/$taskId/stream") {
        accept(ContentType.Text.EventStream)
    }.bodyAsChannel().readUTF8Line()?.let { line ->
        if (line.startsWith(":") || line.isBlank()) return@let  // Skip comments & empty
        if (line.startsWith("data:")) {
            val data = line.removePrefix("data:").trim()
            Json.decodeFromString<ProcessEvent>(data)
        }
    }
}
```

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

### H2 — KableBleRepository Job Accumulation

**Problem:** `stateMonitorJob` not cancelled on successful connect.

**Fix:**
```kotlin
suspend fun connect(sensorId: String, address: String): Result<Unit> {
    // ... existing connection logic
    stateMonitorJobs[sensorId]?.cancel()  // Cancel monitor after successful connect
    reconnectJobs[sensorId]?.cancel()
    // ...
}
```

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

### M4 — ImuStreamWriter Flush/Close

Use try-finally:
```kotlin
fun close() {
    try {
        flush()
    } finally {
        fileOutputStream?.close()
        fileOutputStream = null
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

### M9 — PendingUploadDao Race

Add `@Transaction` + atomic status update to prevent concurrent processing:
```kotlin
@Transaction
@Query("UPDATE pending_uploads SET status = 'UPLOADING' WHERE id = :id AND status = 'PENDING'")
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

## 6. Test Plan

### Unit Tests to Add

| Area | Test | Priority |
|------|------|----------|
| Auth | `AuthInterceptor concurrent 401s` — verify single refresh | P0 |
| Auth | `AuthRepository refresh failure clears tokens` | P0 |
| Auth | `AuthRepository logout calls API then clears` | P0 |
| Auth | `AuthApi.logout()` — request serialization | P0 |
| SSE | `ProcessApi stream parsing` — comments, empty lines, data | P1 |
| Upload | `UploadWorker unique work` — no duplicate processing | P1 |
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
| Login → 401 → refresh → retry | Full auth recovery |
| Login → refresh fails → logout | Token clearing |
| Upload → 429 → backoff → success | Rate limit recovery |
| SSE stream → completed → navigate | Full processing flow |
| BLE connect → disconnect → reconnect | Sensor lifecycle |

### Instrumented Tests

| Test | What to verify |
|------|---------------|
| `LoginScreen → enter credentials → tap login → navigate to camera` | Auth flow |
| `SessionList → swipe to delete → confirm` | Session CRUD |
| `ProcessingScreen → cancel button → confirmation → status updates` | Cancel processing |

---

## 7. Implementation Order

Phase 1 — Auth (blocks everything else):
1. C1: AuthInterceptor Mutex
2. C2: Clear tokens on refresh failure
3. C4: Call `/auth/logout`
4. H8: Timeout configuration

Phase 2 — Network resilience:
5. H7: Retry with exponential backoff
6. C5: SSE stream parsing fix

Phase 3 — UI error handling:
7. H5: SessionsViewModel error propagation
8. H6: Load profile after login
9. H4: UploadWorker race fix
10. M11: ProcessingViewModel sessionId

Phase 4 — Data stability:
11. H1: BleManager thread safety
12. H2: KableBleRepository job cleanup
13. H3: CameraXRecorder try-finally
14. M1-M12: All medium fixes

Phase 5 — iOS:
15. C3: Keychain TokenStorage

Phase 6 — New features:
16. Email verification
17. Password reset
18. Session CRUD
19. Metrics API
20. Cancel processing

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Auth refactor breaks existing login flow | Medium | High | Comprehensive auth tests before merge |
| SSE parsing change breaks processing | Low | High | Test with real SSE stream |
| BLE thread safety fix introduces new race | Low | Medium | BLE unit tests with concurrent access |
| Keychain API availability on older iOS | Low | Low | Min iOS 15+, Keychain available since iOS 2 |
| Retry backoff causes UI sluggishness | Low | Medium | Cancel retry on ViewModel clear |
| New API endpoints don't match backend yet | Medium | Medium | Verify against backend schemas.py before implementing |