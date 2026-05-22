# Mobile Audit Fixes — Design Spec

Date: 2026-05-22
Branch: docs/claude-md-cleanup (audit), implementation TBD
Scope: P0-P3 bug fixes + missing backend integrations

## Overview

Comprehensive fix plan for the KMP mobile app based on code audit. 5 critical, 8 high, 12 medium bugs, plus 4 groups of missing backend integrations.

**Research rounds incorporated:**
- Round 1 (5 agents): Ktor Auth plugin (C1), Ktor SSE plugin (C5), multiplatform-settings KeychainSettings (C3), HttpRequestRetry API corrections (H7), retry-before-timeout ordering (H7→H8), auto-reconnect preservation (H2), PendingUploadDao status values (M9), ImuStreamWriter fsync (M4).
- Round 2 (5 agents): logout requires refresh_token body (C4), SSE `incoming` vs `events` (C5), SSE maxReconnectionAttempts (C5), kotlinx.io.IOException (H7), no separate authClient needed (C1), cacheTokens stale after login (C1), MetricsApi model mismatches (5.4), backend missing session_id in SSE (M11), KeychainSettings iOS 16 crash + errSecInteractionNotAllowed (C3), jitter for backoff (H7), addressToSensorId no-op (H1).

## 1. Auth Fixes (P0)

### C1 — Replace AuthInterceptor with Ktor Auth Plugin

**Problem:** Custom `AuthInterceptor` has race condition on concurrent 401s. Mutex-based fix adds complexity and still requires manual retry logic.

**Fix:** Use Ktor Auth plugin with `BearerAuthProvider` — built-in concurrent 401 deduplication (via `AuthTokenHolder` Mutex + `tokenVersions` AtomicCounter) and automatic retry.

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
            // Use this.client — it has AuthCircuitBreaker set automatically.
            // No separate authClient needed. markAsRefreshTokenRequest() prevents 401 loops.
            val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
            val response = client.post("$baseUrl/auth/refresh") {
                markAsRefreshTokenRequest()
                contentType(ContentType.Application.Json)
                setBody(mapOf("refresh_token" to refreshToken))
            }.body<TokenResponse>()
            tokenStorage.saveTokens(response.accessToken, response.refreshToken)
            BearerTokens(response.accessToken, response.refreshToken)
        }
    }
}
```

**No separate `authClient` needed.** The `refreshTokens` callback's `this.client` is the same HttpClient with `AuthCircuitBreaker` set, preventing infinite 401 loops. Login/register work without tokens (Auth plugin is a no-op when `loadTokens` returns null).

**cacheTokens handling:** After login/register, call `httpClient.authProvider<BearerAuthProvider>()?.clearToken()` to invalidate the in-memory cache so `loadTokens` re-reads from `TokenStorage`. Alternatively, set `cacheTokens = false` (simpler, slight perf cost).

**Delete** `AuthInterceptor.kt` entirely — Ktor Auth plugin handles everything (token injection, 401 detection, refresh, retry).

**Test:** `AuthRepositoryTest` — concurrent 401s → single refresh, token corruption prevention. `SkateLabClientTest` — 401 → auto-refresh → retry.

### C2 — Clear Tokens on Refresh Failure

**Problem:** `refreshIfNeeded()` returns null on failure but doesn't clear stale tokens. User stays "logged in" with invalid tokens → infinite 401 loop.

**Fix:** Clear both tokens on refresh failure (handled in C1's `refreshTokens` block — on exception, `refreshTokens` returns null which triggers Ktor Auth to call `clearTokens()` in the `onFailure` path. Alternatively, wrap the `client.post` in `runCatching` and call `tokenStorage.clearTokens()` on failure before returning null).

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
// TokenStorage — platform-agnostic, takes Settings
class TokenStorage(private val settings: Settings) {
    suspend fun saveAccessToken(token: String) { settings.putString("access_token", token) }
    suspend fun getAccessToken(): String? = settings.getStringOrNull("access_token")
    suspend fun saveRefreshToken(token: String) { settings.putString("refresh_token", token) }
    suspend fun getRefreshToken(): String? = settings.getStringOrNull("refresh_token")
    suspend fun clearTokens() { settings.remove("access_token"); settings.remove("refresh_token") }
}

// shared/src/iosMain — KeychainSettings with fallback
actual val settings: Settings by lazy {
    try {
        KeychainSettings(
            service = "ru.skatelab.auth",
            kSecAttrAccessible to kSecAttrAccessibleAfterFirstUnlock
        )
    } catch (e: Exception) {
        Settings()  // Fallback to in-memory MapSettings on Keychain failure
    }
}

// shared/src/androidMain — EncryptedSharedPreferences via SharedPreferencesSettings
fun createAndroidSettings(context: Context): Settings {
    val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
    val prefs = EncryptedSharedPreferences.create(
        context, "skatelab_tokens", masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    return SharedPreferencesSettings(prefs)
}
```

**KeychainSettings mitigations:**
- `kSecAttrAccessible = kSecAttrAccessibleAfterFirstUnlock` — allows Keychain access after device reboot without UI unlock (critical for background refresh). Prevents `errSecInteractionNotAllowed` (-25308) which occurs when Keychain is accessed before first unlock.
- Try-catch fallback to `Settings()` (in-memory) — mitigates iOS 16 crash (GitHub issue #144) and any future Keychain failures.
- Delete manual cinterop code in `IosTokenStorage.kt`. Remove `iosSecurity` framework dependency.

**Test:** `IosTokenStorageTest` (iosTest) — save, get, clear roundtrip. Verify Keychain usage via device console.

### C4 — Call `/auth/logout` on Sign-Out

**Problem:** Mobile only clears local storage on logout. Backend refresh token stays valid → token reuse vulnerability.

**Fix:**
```kotlin
// AuthRepository.kt
suspend fun logout() {
    val refreshToken = tokenStorage.getRefreshToken()
    if (refreshToken != null) {
        runCatching { authApi.logout(refreshToken) }  // Best-effort — send refresh token
    }
    tokenStorage.clearTokens()
    // Invalidate Ktor's in-memory token cache
    httpClient.authProvider<BearerAuthProvider>()?.clearToken()
}
```

**Backend requires `RefreshRequest` body** with `refresh_token` field (see `backend/app/routes/auth.py` → `logout(data: RefreshRequest)`). The `markAsRefreshTokenRequest()` in `AuthApi.logout()` prevents Auth plugin from adding expired access token headers:

```kotlin
// AuthApi.kt
suspend fun logout(refreshToken: String) {
    client.post("/auth/logout") {
        markAsRefreshTokenRequest()  // Skip Auth plugin — logout with refresh token only
        contentType(ContentType.Application.Json)
        setBody(mapOf("refresh_token" to refreshToken))
    }
}
```

**Key:** `tokenStorage.clearTokens()` runs AFTER `authApi.logout()` so the refresh token is available for the API call. `clearToken()` on the Auth provider invalidates the in-memory cache so subsequent requests don't use stale tokens.

**Test:** `AuthApiTest` — logout sends refresh_token in body. `AuthRepositoryTest` — logout clears tokens even if API fails.

---

## 2. Network Resilience (P1)

### H7 — Retry with Exponential Backoff

**Problem:** Ktor client has no retry. Transient network failures (mobile, elevator, tunnel) cause immediate failure.

**Fix:** Add `HttpRequestRetry` plugin to `SkateLabClient`. Use KMP-compatible exception types.

```kotlin
install(HttpRequestRetry) {
    maxRetries = 3
    retryIf { request, response ->
        response.status.value.let { it >= 500 || it == 429 }
    }
    retryOnExceptionIf { request, cause ->
        cause is io.ktor.client.network.sockets.SocketTimeoutException ||
        cause is io.ktor.client.plugins.HttpRequestTimeoutException ||
        cause is kotlinx.io.IOException  // Ktor 3.x uses kotlinx.io, NOT io.ktor.utils.io.errors
    }
    exponentialDelay(
        base = 2.0,           // 2^n: 500ms, 1s, 2s, 4s, 8s
        baseDelayMs = 500,
        maxDelayMs = 8_000,
        randomizationMs = 500,   // Jitter prevents thundering herd
        respectRetryAfter = true  // Honor Retry-After header for 429
    )
}
```

**Not retried:** 401 (handled by Ktor Auth plugin), 4xx client errors.

**CRITICAL: Install order matters** — `HttpRequestRetry` MUST be installed BEFORE `HttpTimeout` so retries execute before timing out. If installed after, timeout exceptions arrive wrapped in `CancellationException` and `isTimeoutException()` returns false, making timeout detection unreliable (Ktor Slack confirmed, 2023-08-08).

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

Upload endpoint gets longer timeouts — per-request timeout resets on each retry:
```kotlin
// In UploadWorker, override per-request:
client.put(presign.url) {
    timeout { requestTimeoutMillis = 120_000 }  // 2min for large uploads, resets on retry
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

**Fix:** After successful login/register, fetch user profile via `UsersApi.getMe()` (verified exists at line 10-11 of `UsersApi.kt`, returns `UserResponse` with `id` and `displayName`).

```kotlin
suspend fun login(email: String, password: String) {
    _uiState.value = AuthUiState.Loading
    authRepo.login(email, password)
        .onSuccess {
            val user = runCatching { usersApi.getMe() }.getOrNull()
            _uiState.value = AuthUiState.LoggedIn(user?.id ?: "new", user?.displayName)
        }
        .onFailure { e ->
            _uiState.value = AuthUiState.Error(e.message ?: "Login failed")
        }
}
```

Add `UsersApi` dependency to `AuthViewModel`.

### C5 — Replace Manual SSE Parser with Ktor SSE Plugin

**Problem:** `ProcessApi.stream()` uses manual line-by-line parsing. Doesn't handle comment lines (`:`), empty lines, multi-line data, or reconnection. Current `callbackFlow` reads one line and exits — doesn't loop.

**Fix:** Use Ktor SSE plugin — built-in comment/empty line handling, auto-reconnect, proper event parsing, `Last-Event-ID` support.

Add dependency in `shared/build.gradle.kts`:
```kotlin
commonMain {
    implementation("io.ktor:ktor-client-sse:3.1.3")
}
```

```kotlin
// SkateLabClient.kt
install(SSE) {
    reconnectionTime = 5000          // Delay between reconnection attempts
    maxReconnectionAttempts = 3       // REQUIRED — default is 0 (disabled). Without this, no auto-reconnect.
}

// ProcessApi.kt
fun stream(taskId: String): Flow<ProcessEvent> = callbackFlow {
    client.sse("/process/$taskId/stream") {
        incoming.collect { event ->   // NOT events.collect — incoming is the correct Flow<ClientSSEEvent>
            val data = event.data ?: return@collect
            val processEvent = sseJson.decodeFromString<ProcessEvent>(data)
            trySend(processEvent)
        }
    }
    awaitClose()
}
```

**Delete** manual line-by-line parsing code. Ktor SSE handles: comment lines, empty lines, multi-line `data:` fields, `event:`/`id:` fields, auto-reconnect (when `maxReconnectionAttempts > 0`), `Last-Event-ID` header on reconnect, `retry:` field from server.

**KMP compatibility verified:** SSE plugin works on iOS/Darwin via NSURLSession streaming delegates. `ClientSSESession.incoming` is a `Flow<ClientSSEEvent>` in commonMain.

**Test:** `ProcessApiTest` — comment lines, empty lines, multi-line data, reconnection.

### H4 — UploadWorker Race Condition

**Problem:** Multiple workers can process the same pending upload simultaneously.

**Fix:** Use `ExistingWorkPolicy.KEEP` for scheduling + database-level locking.

```kotlin
// UploadScheduler.kt
fun enqueue(context: Context, uploadId: String) {
    val request = OneTimeWorkRequestBuilder<UploadWorker>()
        .setInputData(UploadWorker.inputData(uploadId))
        .setConstraints(Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build())
        .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
        .build()

    WorkManager.getInstance(context)
        .enqueueUniqueWork(
            "upload-$uploadId",          // Unique per session
            ExistingWorkPolicy.KEEP,      // Don't re-enqueue if running (REPLACE would cancel mid-transfer)
            request
        )
}
```

In `UploadWorker`, add atomic lock:
```kotlin
val locked = pendingUploadDao.tryLockForUpload(uploadId)
if (locked == 0) return Result.success()  // Another worker already processing
val entity = pendingUploadDao.getById(uploadId) ?: return Result.failure()
```

---

## 4. BLE / Camera / Data Stability (P2+P3)

### H1 — BleManager Thread Safety

**Problem:** `parsers` ConcurrentHashMap accessed from Binder thread and workHandler thread without synchronization.

**Fix:** Use `ConcurrentHashMap.computeIfAbsent()` instead of `getOrPut()`:
```kotlin
// BleManager.kt line ~402
val parser = parsers.computeIfAbsent(address) {
    Wt901Parser().also {
        it.logTag = "Wt901Parse-${address.takeLast(5)}"
        it.onRegisterRead = { result ->
            _registerReadResults.tryEmit(address to result)
        }
    }
}
```

`addressToSensorId[address]` on `ConcurrentHashMap` already returns null for missing keys — the existing `?: return@onCharacteristicChanged` pattern is correct. No change needed there.

### H2 — KableBleRepository Job Accumulation (Corrected)

**Problem:** After a successful `connect()`, stale `reconnectJobs` from a previous auto-reconnect attempt are never cancelled. They could fire concurrently with the explicit connect.

**Fix:** Cancel `reconnectJobs` on successful connect. Do NOT cancel `stateMonitorJobs` — they detect disconnections and trigger auto-reconnect.

```kotlin
// In connect(), after successful connection:
reconnectJobs[sensorId]?.cancel()
reconnectJobs.remove(sensorId)
// stateMonitorJobs[sensorId] stays running — monitors for future disconnections
```

**Current code does NOT cancel stateMonitorJobs on successful connect** (verified at line 180 — it only cancels the OLD stateMonitorJob before creating a new one). The fix is only for `reconnectJobs`.

**Future:** Kable 0.35+ provides `peripheral.connect()` returning `CoroutineScope`, eliminating manual job management. Deferred — 0.35.0-rc is not stable. Apply patch now, migrate later.

### H3 — CameraXRecorder Resource Leak

**Problem:** If `pendingRecording.start()` throws, `timestampTracker` (which starts a background Thread in `open()`) is never closed. The `VideoRecordEvent.Finalize` callback that normally closes it never fires.

**Fix:**
```kotlin
try {
    activeRecording = pendingRecording.start(cameraExecutor) { event -> ... }
} catch (e: Exception) {
    timestampTracker?.close()
    timestampTracker = null
    throw e
}
```

### M1 — Wt901Parser Frame Stats Reset

Add `reset()` method:
```kotlin
fun reset() {
    frameCounts.clear()
    logSeq.clear()
    buffer.clear()
    imuPacketCount = 0L
    bitmaskSample = null
}
```

### M2 — FrameTimestampTracker Queue Offer

Check `offer()` return value:
```kotlin
if (!queue.offer(index to timestampNs)) {
    Log.w("FrameTimestampTracker", "Queue full, dropping frame $index")
}
```

### M3 — ImuCollector Write Error Notification

Propagate write errors to UI via `StateFlow`:
```kotlin
private val _writeError = MutableStateFlow<Throwable?>(null)
val writeError: StateFlow<Throwable?> = _writeError.asStateFlow()

// In write loop catch block:
_writeError.value = e
```

### M4 — ImuStreamWriter Flush/Close (Defense-in-Depth)

**Current code** already has `fsync` via `fd.sync()` and `@Synchronized` prevents double-close. Fix adds null-first pattern + try-finally for extra safety:

```kotlin
@Synchronized
fun close() {
    val fos = fileOutputStream
    fileOutputStream = null
    val fd = fos?.fd
    try {
        stream?.flush()
        fd?.sync()
    } finally {
        stream?.close()
        stream = null
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

`runBlocking` in `onCleared()` is acceptable since the ViewModel is being destroyed. Document the pattern. No change needed.

### M7 — SensorRecordingService Lifecycle

Use `START_NOT_STICKY` instead of `START_STICKY`:
```kotlin
return START_NOT_STICKY
```

### M8 — Room Schema Export

Enable schema export for migration tracking:
```kotlin
@Database(
    entities = [CachedSessionEntity::class, PendingUploadEntity::class],
    version = 1,
    exportSchema = true
)
```

Add to `build.gradle.kts`:
```kotlin
ksp {
    arg("room.schemaLocation", "${projectDir}/schemas")
}
```

### M9 — PendingUploadDao Race (Corrected)

Add conditional UPDATE for optimistic locking. Use `status = 'READY'` (actual enum value in `PendingUploadEntity`), not `'PENDING'`.

```kotlin
@Query("UPDATE pending_uploads SET status = 'UPLOADING' WHERE id = :id AND status = 'READY'")
suspend fun tryLockForUpload(id: String): Int  // Returns rows affected (1 = locked, 0 = already taken)
```

`@Transaction` is technically unnecessary for a single UPDATE (SQLite serializes writes), but harmless. The two-step lock-then-read (`tryLockForUpload` + `getById`) is safe because after locking, the only state transitions are forward (UPLOADING→PROCESSING→COMPLETED/FAILED).

### M10 — ZipExporter Partial ZIP

Use atomic file write:
```kotlin
val tempFile = File(zipFile.absolutePath + ".tmp")
try {
    ZipOutputStream(BufferedOutputStream(tempFile.outputStream(), BUFFER_SIZE)).use { zos ->
        // ... write entries
    }
    tempFile.renameTo(zipFile)  // Atomic on POSIX
} catch (e: Exception) {
    tempFile.delete()
    throw e
}
```

### M11 — ProcessingViewModel taskId vs sessionId

**Bug confirmed:** Current code at line 36 emits `taskId` instead of `sessionId` on COMPLETED.

**Mobile fix:** Add `session_id` field to `ProcessEvent` with fallback:
```kotlin
@Serializable
data class ProcessEvent(
    val progress: Float = 0f,
    val message: String = "",
    val status: String = "running",
    @SerialName("session_id") val sessionId: String? = null,  // Not yet sent by backend
) {
    val parsedStatus: ProcessStatus
        get() = when (status) {
            "running" -> ProcessStatus.RUNNING
            "completed" -> ProcessStatus.COMPLETED
            "failed" -> ProcessStatus.FAILED
            "cancelled" -> ProcessStatus.CANCELLED
            else -> ProcessStatus.UNKNOWN
        }
}

// ProcessingViewModel
ProcessStatus.COMPLETED -> {
    _uiState.value = ProcessingUiState.Completed(event.sessionId ?: taskId)  // Fallback until backend sends session_id
}
```

**Backend gap:** The backend's `publish_task_event()` does NOT include `session_id` in the completed SSE event. It only sends `{"status": "completed", "progress": 1.0, "message": "Done"}`. The `create_task_state()` Valkey hash stores `task_id`, `video_key`, `user_id`, but not `session_id`. A separate backend PR is needed to:
1. Add `session_id` to `create_task_state()` fields when `session_id` is provided
2. Include `session_id` in the completed `publish_task_event()` call

The mobile fallback (`event.sessionId ?: taskId`) ensures the app works before and after the backend fix.

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
suspend fun verifyEmail(token: String) {
    client.post("/auth/verify-email") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("token" to token))
    }
}

suspend fun resendVerification(email: String) {
    client.post("/auth/resend-verification") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("email" to email))
    }
}

// AuthRepository.kt
suspend fun verifyEmail(token: String): Result<Unit> = runCatching { authApi.verifyEmail(token) }
suspend fun resendVerification(email: String): Result<Unit> = runCatching { authApi.resendVerification(email) }
```

**Deep links:** Use Compose Navigation 2.9.2+ built-in `navDeepLink` in shared module. Register `skatelab://` scheme in `AndroidManifest.xml` intent filter. No external library needed.

**Flow:**
1. User registers → `AuthUiState.NeedsVerification(email)`
2. User clicks email link → deep link opens app → `verifyEmail(token)`
3. On success → `AuthUiState.LoggedIn`

### 5.2 — Password Reset

**Backend endpoints:** `/auth/forgot-password`, `/auth/reset-password`

**Shared module additions:**
```kotlin
// AuthApi.kt
suspend fun forgotPassword(email: String) {
    client.post("/auth/forgot-password") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("email" to email))
    }
}

suspend fun resetPassword(token: String, newPassword: String) {
    client.post("/auth/reset-password") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("token" to token, "new_password" to newPassword))
    }
}

// AuthRepository.kt
suspend fun forgotPassword(email: String): Result<Unit> = runCatching { authApi.forgotPassword(email) }
suspend fun resetPassword(token: String, newPassword: String): Result<Unit> = runCatching { authApi.resetPassword(token, newPassword) }
```

**Android UI:** `ForgotPasswordScreen` + `ResetPasswordScreen`. Deep link for password reset via same `navDeepLink` pattern.

### 5.3 — Session CRUD

**Backend endpoints:** `PATCH /sessions/{id}`, `DELETE /sessions/{id}`, `DELETE /sessions/bulk`

**Shared module additions:**
```kotlin
// SessionsApi.kt
suspend fun update(id: String, request: SessionUpdateRequest): SessionResponse =
    client.patch("/sessions/$id") {
        contentType(ContentType.Application.Json)
        setBody(request)
    }.body()

suspend fun bulkDelete(ids: List<String>) {
    client.delete("/sessions/bulk") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("session_ids" to ids))
    }
}

// Models
@Serializable
data class SessionUpdateRequest(
    @SerialName("element_type") val elementType: String? = null,
    val notes: String? = null,
)
```

**Android UI:** Add delete button to `SessionDetailScreen`, multi-select delete in `SessionListScreen`.

### 5.4 — Metrics API

**Backend endpoints:** `/metrics/registry`, `/metrics/trend`, `/metrics/prs`, `/metrics/diagnostics`, `/metrics/element-summary`

**Shared module additions:**
```kotlin
// MetricsApi.kt (new file)
class MetricsApi(private val client: HttpClient) {
    suspend fun getRegistry(): MetricsRegistryResponse =
        client.get("/metrics/registry").body()

    suspend fun getTrend(metricName: String, period: String? = null): TrendResponse =
        client.get("/metrics/trend") {
            parameter("metric_name", metricName)
            if (period != null) parameter("period", period)
        }.body()

    suspend fun getPersonalRecords(): PRsResponse =
        client.get("/metrics/prs").body()

    suspend fun getDiagnostics(sessionId: String): DiagnosticsResponse =
        client.get("/metrics/diagnostics") {
            parameter("session_id", sessionId)
        }.body()

    suspend fun getSummary(elementType: String, period: String): SummaryResponse =
        client.get("/metrics/element-summary") {
            parameter("element_type", elementType)
            parameter("period", period)
        }.body()
}
```

**Models — matched to actual backend schemas:**
```kotlin
// Backend returns dict keyed by metric name, NOT a list
@Serializable
data class MetricsRegistryResponse(
    val metrics: Map<String, MetricDefinition>  // Key = metric name
)

@Serializable
data class MetricDefinition(
    val name: String,
    @SerialName("label_ru") val labelRu: String? = null,
    val unit: String,
    val format: String? = null,
    val direction: String? = null,
    @SerialName("element_types") val elementTypes: List<String>? = null,
    @SerialName("ideal_range") val idealRange: Map<String, Double>? = null,
)

@Serializable
data class TrendResponse(
    @SerialName("metric_name") val metricName: String,
    @SerialName("element_type") val elementType: String,
    @SerialName("data_points") val dataPoints: List<TrendDataPoint>,
    val trend: String? = null,
    @SerialName("current_pr") val currentPr: Double? = null,
    @SerialName("reference_range") val referenceRange: Map<String, Double>? = null,
)

@Serializable
data class TrendDataPoint(
    @SerialName("session_id") val sessionId: String,
    val value: Double,
    @SerialName("is_pr") val isPr: Boolean = false,
    val date: String? = null,
)

@Serializable
data class PRsResponse(
    val prs: List<PersonalRecord>
)

@Serializable
data class PersonalRecord(
    @SerialName("element_type") val elementType: String? = null,
    @SerialName("metric_name") val metricName: String,
    val value: Double,
    @SerialName("session_id") val sessionId: String,
)

@Serializable
data class DiagnosticsResponse(
    @SerialName("user_id") val userId: String,
    val findings: List<DiagnosticsFinding>
)

@Serializable
data class DiagnosticsFinding(
    val severity: String,
    val element: String? = null,
    val metric: String? = null,
    val message: String,
    val detail: String? = null,
)

@Serializable
data class SummaryResponse(
    val element: String,
    val period: String,
    val trend: String? = null,
    val findings: List<DiagnosticsFinding>? = null,
    @SerialName("metric_defs") val metricDefs: Map<String, MetricDefinition>? = null,
    @SerialName("personal_records") val personalRecords: List<PersonalRecord>? = null,
)
```

**Android UI:** `MetricsScreen` with tabs (Summary, Trends, PRs). Show metric registry, trends chart, personal records.

### 5.5 — Cancel Processing

**Backend endpoint:** `POST /process/{id}/cancel`

`ProcessApi.cancel()` already exists at line 47. Add to `ProcessingViewModel`:
```kotlin
suspend fun cancelProcessing(taskId: String) {
    runCatching { processApi.cancel(taskId) }
        .onFailure { _uiState.value = ProcessingUiState.Failed(it.message ?: "Cancel failed") }
}
```

**Android UI:** Add "Cancel" button in `ProcessingScreen`. Confirmation dialog → `cancelProcessing(taskId)`.

---

## 6. Parallelization Strategy

### Dependency Graph

Only `SkateLabClient.kt` is a serial bottleneck. 9 of 17 tasks are fully independent of Auth.

```
Serial (SkateLabClient.kt modifications):
  Task 1+4+5+16 (consolidated): Auth + Retry + Timeout + SSE + Metrics
  → These all modify SkateLabClient.kt and MUST be sequential

Depends on Task 1+4+5+16:
  Task 2 (Delete AuthInterceptor + AuthRepository.logout)
  Task 13b (TokenStorage refactor — TokenStorage interface changes)
  Task 14 (Email verify + password reset — AuthApi additions)
  Task 17 (Cancel processing — ProcessingViewModel)

Fully independent (can start immediately):
  Task 6 (SessionsViewModel + AuthViewModel)
  Task 7 (ProcessingViewModel sessionId)
  Task 8 (UploadWorker race)
  Task 9 (BleManager thread safety)
  Task 10 (KableBleRepository)
  Task 11 (CameraXRecorder leak)
  Task 12 (Medium fixes batch)
  Task 13a (multiplatform-settings dependency addition)
  Task 15 (Session CRUD)
```

### Revised Wave Structure

```
Wave 0 — SkateLabClient overhaul (serial bottleneck)
  Consolidated Task: Auth plugin + HttpRequestRetry + HttpTimeout + SSE plugin + MetricsApi
  + Delete AuthInterceptor, update AuthRepository.logout with refresh_token body

Wave 1 — Independent fixes (parallel, starts immediately)
  T-A: Task 13a (multiplatform-settings dependency)
  T-B: Task 9 + 10 + 11 (BLE + Camera)
  T-C: Task 12 (Medium fixes batch)
  T-D: Task 7 (ProcessingViewModel sessionId)
  T-E: Task 8 (UploadWorker race)
  T-F: Task 15 (Session CRUD)
  T-G: Task 6 (ViewModels — after Wave 0 for UsersApi dep)

Wave 2 — Dependent tasks (after Wave 0)
  T-H: Task 13b (TokenStorage refactor)
  T-I: Task 14 (Email verify + password reset)
  T-J: Task 17 (Cancel processing)

Wave 3 — Tests
  Task 3 (Auth tests)
```

### Estimated wall-clock reduction: ~40-50%

Original: 5 sequential waves. Revised: Wave 0 + Wave 1 run nearly simultaneously (only Wave 0's SkateLabClient change must land first, but Wave 1 tasks don't touch that file).

### Rollback Safety

Feature branches:
- `feature/mobile-bugfixes-independent` (Tasks 6-12, 13a, 15) — merges first, zero auth dependency
- `feature/mobile-auth-overhaul` (consolidated SkateLabClient + AuthInterceptor delete) — merges after testing
- `feature/mobile-new-integrations` (Tasks 13b, 14, 17) — merges last, rebased onto auth

---

## 7. Test Plan

### Testing Infrastructure

Add to commonTest:
- `org.mokkery:mokkery` — KMP-native mocking (unlike MockK which is JVM-only)
- `app.cash.turbine:turbine` — StateFlow assertion
- `io.ktor:ktor-client-mock` — API client testing without real server

### Unit Tests to Add

| Area | Test | Priority |
|------|------|----------|
| Auth | `Ktor Auth plugin concurrent 401s` — verify single refresh | P0 |
| Auth | `AuthRepository logout sends refresh_token, clears tokens even if API fails` | P0 |
| Auth | `cacheTokens invalidated after login — clearToken() called` | P0 |
| SSE | `ProcessApi stream via SSE plugin` — incoming.collect, comments, empty lines | P1 |
| SSE | `SSE auto-reconnect` — maxReconnectionAttempts = 3 | P1 |
| Upload | `UploadWorker unique work` — no duplicate processing | P1 |
| Upload | `PendingUploadDao.tryLockForUpload` — WHERE status='READY' | P1 |
| API | `SkateLabClient retry on 5xx` — 3 retries then fail | P1 |
| API | `SkateLabClient timeout` — connect, request, socket | P1 |
| Models | `MetricsRegistryResponse parsing` — Map not List | P2 |
| Models | `TrendResponse parsing` — all fields from backend | P2 |
| Models | `ProcessEvent with sessionId` — backward compat (null fallback) | P2 |
| Auth | `Email verification deep link` — token parsing | P2 |
| Auth | `Password reset flow` — token + new password | P2 |

### Integration Test Priorities

| Flow | What to verify |
|------|---------------|
| Login → 401 → Ktor Auth refresh → retry | Full auth recovery (plugin-managed) |
| Login → refresh fails → tokens cleared → logout | Token clearing + provider clearToken() |
| Upload → 429 → backoff + jitter → success | Rate limit recovery |
| SSE stream → disconnect → auto-reconnect (3 attempts) | Reconnection with maxReconnectionAttempts |
| SSE stream → completed → navigate with sessionId | Full processing flow |
| BLE connect → disconnect → auto-reconnect | Sensor lifecycle (stateMonitorJob preserved) |

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Ktor Auth plugin migration breaks existing login flow | Medium | High | Comprehensive auth tests before merge; delete AuthInterceptor only after tests pass |
| cacheTokens = true causes stale tokens after login | High | High | Call `clearToken()` after login/register, or set `cacheTokens = false` |
| SSE plugin API mismatch with backend SSE format | Low | High | Test with real SSE stream; verify backend sends standard SSE format |
| SSE maxReconnectionAttempts = 0 (disabled) | High | Medium | Must explicitly set `maxReconnectionAttempts = 3` |
| Backend doesn't send session_id in SSE completed event | High | Medium | Mobile fallback `event.sessionId ?: taskId`; backend PR needed separately |
| KeychainSettings crash on iOS 16 (issue #144) | Low | High | Try-catch fallback to `Settings()` (in-memory); set `kSecAttrAccessibleAfterFirstUnlock` |
| IOException import wrong (io.ktor.utils.io vs kotlinx.io) | High | High | Use `kotlinx.io.IOException` — Ktor 3.x standard |
| HttpRequestRetry before HttpTimeout ordering | Medium | High | Add code comment referencing Ktor docs; install order enforced by spec |
| MetricsApi models don't match backend | High | Medium | Models verified against backend schemas.py; all field names match |
| BLE thread safety fix introduces new race | Low | Medium | BLE unit tests with concurrent access |
| Cancelling stateMonitorJob breaks auto-reconnect | High | High | Only cancel reconnectJobs; stateMonitorJob stays running |
| PendingUploadDao status mismatch | Medium | Medium | Use 'READY' not 'PENDING' per actual entity enum |
| Kable 0.35 migration attempted in bug-fix cycle | Medium | High | Defer — 0.35.0-rc is not stable. Apply H2 patch now, migrate later |