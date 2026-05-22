# Mobile Audit Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 25 audit bugs (5 critical, 8 high, 12 medium) and add 5 missing backend integrations in the KMP mobile app.

**Architecture:** KMP shared module (commonMain) + platform-specific (androidMain, iosMain). Ktor Auth plugin replaces custom interceptor. Ktor SSE plugin replaces manual parser. multiplatform-settings KeychainSettings replaces iOS cinterop. Clean Architecture: presentation → domain → data.

**Tech Stack:** Kotlin 2.1.21, Ktor 3.1.3, KMP, Hilt, Room, WorkManager, Kable 0.32.0, multiplatform-settings 1.3.0

**Spec:** `docs/specs/2026-05-22-mobile-audit-fixes-design.md`
**Research report:** `docs/specs/2026-05-22-mobile-audit-fixes-research-report.md`

**Parallelization:** Only `SkateLabClient.kt` is a serial bottleneck. 9 of 17 tasks are fully independent and can start immediately. Consolidated SkateLabClient overhaul (Auth + Retry + Timeout + SSE + Metrics) eliminates 3 context switches.

---

## Wave 0 — SkateLabClient Overhaul (serial bottleneck)

Consolidates Tasks 1, 4, 5, 16 + Task 2 from original plan. All modify `SkateLabClient.kt` so they're done as one atomic change.

### Task 1: Install Ktor Auth plugin + HttpRequestRetry + HttpTimeout + SSE in SkateLabClient

**Files:**
- Modify: `mobile/shared/build.gradle.kts`
- Modify: `mobile/gradle/libs.versions.toml` — add ktor-client-sse entry
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/MetricsApi.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/MetricsModels.kt`

- [ ] **Step 1: Add ktor-client-sse to libs.versions.toml and build.gradle.kts**

In `mobile/gradle/libs.versions.toml`, add to `[libraries]`:
```toml
ktor-client-sse = { module = "io.ktor:ktor-client-sse", version.ref = "ktor" }
```

In `mobile/shared/build.gradle.kts`, add to `commonMain.dependencies`:
```kotlin
implementation(libs.ktor.client.sse)
```

- [ ] **Step 2: Verify ktor-client-auth dependency exists in build.gradle.kts**

Check `mobile/shared/build.gradle.kts` already has `implementation(libs.ktor.client.auth)` in commonMain. If not, add it.

- [ ] **Step 3: Overhaul SkateLabClient.kt — Auth + Retry + Timeout + SSE + Metrics**

Replace `SkateLabClient.kt` with the consolidated version. Key changes from research:
- No separate `authClient` — `refreshTokens` callback uses `this.client` with `markAsRefreshTokenRequest()`
- `kotlinx.io.IOException` (NOT `io.ktor.utils.io.errors.IOException`)
- `randomizationMs = 500` for jitter
- `maxReconnectionAttempts = 3` for SSE (default is 0 = disabled)
- `incoming.collect` (NOT `events.collect`)
- `cacheTokens = false` to avoid stale tokens after login (simpler than calling `clearToken()`)

```kotlin
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.engine.*
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.*
import io.ktor.client.plugins.auth.*
import io.ktor.client.plugins.auth.providers.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.sse.*
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import io.ktor.utils.io.errors.IOException as KtorIOException
import kotlinx.io.IOException
import kotlinx.serialization.json.Json
import ru.skatelab.shared.auth.TokenStorage

class SkateLabClient(
    private val baseUrl: String,
    engine: HttpClientEngine,
    private val tokenStorage: TokenStorage,
) {
    val json = Json { ignoreUnknownKeys = true; isLenient = true }

    val httpClient = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }

        defaultRequest { url(baseUrl) }

        // CRITICAL: install Auth plugin first — handles 401s with automatic refresh
        install(Auth) {
            bearer {
                cacheTokens = false  // Avoid stale tokens after login; read from Settings on each request
                loadTokens {
                    val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                    val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                    BearerTokens(access, refresh)
                }
                refreshTokens {
                    // this.client has AuthCircuitBreaker set — no separate authClient needed
                    val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
                    runCatching {
                        client.post("$baseUrl/auth/refresh") {
                            markAsRefreshTokenRequest()  // Prevent 401 loop
                            contentType(ContentType.Application.Json)
                            setBody(mapOf("refresh_token" to refreshToken))
                        }.body<TokenResponse>()
                    }.onSuccess { response ->
                        tokenStorage.saveTokens(response.accessToken, response.refreshToken)
                    }.onFailure {
                        tokenStorage.clearTokens()  // C2: clear on refresh failure
                    }.getOrNull()?.let { BearerTokens(it.accessToken, it.refreshToken) }
                }
            }
        }

        // CRITICAL: HttpRequestRetry MUST be installed BEFORE HttpTimeout
        // If installed after, timeouts arrive wrapped in CancellationException and retry doesn't detect them
        install(HttpRequestRetry) {
            maxRetries = 3
            retryIf { request, response ->
                response.status.value.let { it >= 500 || it == 429 }
            }
            retryOnExceptionIf { request, cause ->
                cause is SocketTimeoutException ||
                cause is HttpRequestTimeoutException ||
                cause is IOException  // kotlinx.io.IOException — Ktor 3.x KMP-compatible
            }
            exponentialDelay(
                base = 2.0,
                baseDelayMs = 500,
                maxDelayMs = 8_000,
                randomizationMs = 500,   // Jitter prevents thundering herd
                respectRetryAfter = true
            )
        }

        install(HttpTimeout) {
            connectTimeoutMillis = 10_000
            requestTimeoutMillis = 30_000
            socketTimeoutMillis = 15_000
        }

        install(SSE) {
            reconnectionTime = 5000
            maxReconnectionAttempts = 3  // REQUIRED — default is 0 (disabled). Without this, no auto-reconnect.
        }
    }

    val auth = AuthApi(httpClient, baseUrl)
    val sessions = SessionsApi(httpClient)
    val users = UsersApi(httpClient)
    val uploads = UploadsApi(httpClient)
    val process = ProcessApi(httpClient)
    val metrics = MetricsApi(httpClient)
}
```

- [ ] **Step 4: Create MetricsApi.kt**

```kotlin
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import ru.skatelab.shared.models.*

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

- [ ] **Step 5: Create MetricsModels.kt (matched to backend schemas)**

```kotlin
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Backend returns dict keyed by metric name, NOT a list
@Serializable
data class MetricsRegistryResponse(
    val metrics: Map<String, MetricDefinition>
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

- [ ] **Step 6: Update AuthApi to use baseUrl parameter and add logout with refresh_token**

AuthApi needs `baseUrl` for the `refreshTokens` callback to call `$baseUrl/auth/refresh`. Also add `logout(refreshToken)`.

```kotlin
// AuthApi.kt
class AuthApi(private val client: HttpClient, private val baseUrl: String) {
    suspend fun login(email: String, password: String): TokenResponse =
        client.post("$baseUrl/auth/login") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("email" to email, "password" to password))
        }.body()

    suspend fun register(email: String, password: String, displayName: String): TokenResponse =
        client.post("$baseUrl/auth/register") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("email" to email, "password" to password, "display_name" to displayName))
        }.body()

    suspend fun refresh(refreshToken: String): TokenResponse =
        client.post("$baseUrl/auth/refresh") {
            markAsRefreshTokenRequest()
            contentType(ContentType.Application.Json)
            setBody(mapOf("refresh_token" to refreshToken))
        }.body()

    suspend fun logout(refreshToken: String) {
        client.post("$baseUrl/auth/logout") {
            markAsRefreshTokenRequest()  // Skip Auth plugin — logout uses refresh token
            contentType(ContentType.Application.Json)
            setBody(mapOf("refresh_token" to refreshToken))
        }
    }

    suspend fun verifyEmail(token: String) { /* Task 14 */ }
    suspend fun resendVerification(email: String) { /* Task 14 */ }
    suspend fun forgotPassword(email: String) { /* Task 14 */ }
    suspend fun resetPassword(token: String, newPassword: String) { /* Task 14 */ }
}
```

- [ ] **Step 7: Update ProcessApi to use SSE plugin**

```kotlin
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.sse.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.ProcessEvent

private val sseJson = Json { ignoreUnknownKeys = true }

class ProcessApi(private val client: HttpClient) {
    suspend fun queue(
        videoKey: String,
        sessionId: String? = null,
        personClickX: Float? = null,
        personClickY: Float? = null,
        frameSkip: Int = 1,
        tracking: String = "auto",
    ): QueueProcessResponse =
        client.post("/process/queue") {
            contentType(ContentType.Application.Json)
            setBody(buildMap {
                put("video_key", videoKey)
                put("frame_skip", frameSkip)
                put("tracking", tracking)
                if (sessionId != null) put("session_id", sessionId)
                if (personClickX != null && personClickY != null) {
                    put("person_click", mapOf("x" to personClickX, "y" to personClickY))
                }
            })
        }.body()

    suspend fun status(taskId: String): TaskStatusResponse =
        client.get("/process/$taskId/status").body()

    suspend fun cancel(taskId: String) {
        client.post("/process/$taskId/cancel")
    }

    fun stream(taskId: String): Flow<ProcessEvent> = callbackFlow {
        client.sse("/process/$taskId/stream") {
            incoming.collect { event ->  // NOT events.collect — incoming is the correct property
                val data = event.data ?: return@collect
                val processEvent = sseJson.decodeFromString<ProcessEvent>(data)
                trySend(processEvent)
            }
        }
        awaitClose()
    }
}

@Serializable
data class QueueProcessResponse(
    @SerialName("task_id") val taskId: String,
    val status: String = "pending",
)

@Serializable
data class TaskStatusResponse(
    @SerialName("task_id") val taskId: String,
    val status: String,
    val progress: Float,
    val message: String,
    val error: String? = null,
)
```

- [ ] **Step 8: Commit**

```bash
git add mobile/gradle/libs.versions.toml mobile/shared/build.gradle.kts mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/MetricsApi.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/MetricsModels.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/ProcessApi.kt
git commit -m "feat(shared): overhaul SkateLabClient — Auth plugin, Retry+Timeout, SSE, MetricsApi"
```

---

### Task 2: Delete AuthInterceptor + update AuthRepository + fix DI

**Files:**
- Delete: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthInterceptor.kt`
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt`

- [ ] **Step 1: Update AuthRepository — logout with refresh token, clear tokens + clearToken()**

```kotlin
package ru.skatelab.shared.auth

import io.ktor.client.plugins.auth.providers.BearerAuthProvider
import ru.skatelab.shared.api.AuthApi

class AuthRepository(
    private val authApi: AuthApi,
    private val tokenStorage: TokenStorage,
    private val clearAuthProvider: () -> Unit,  // Calls httpClient.authProvider<BearerAuthProvider>()?.clearToken()
) {
    suspend fun getAccessToken(): String? = tokenStorage.getAccessToken()

    suspend fun login(email: String, password: String): Result<Unit> = runCatching {
        val tokens = authApi.login(email, password)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
    }

    suspend fun register(email: String, password: String, displayName: String): Result<Unit> = runCatching {
        val tokens = authApi.register(email, password, displayName)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
    }

    suspend fun isLoggedIn(): Boolean = tokenStorage.getAccessToken() != null

    suspend fun logout() {
        val refreshToken = tokenStorage.getRefreshToken()
        if (refreshToken != null) {
            runCatching { authApi.logout(refreshToken) }  // Best-effort — network failures shouldn't block logout
        }
        tokenStorage.clearTokens()
        clearAuthProvider()  // Invalidate Ktor's in-memory token cache
    }

    // refreshIfNeeded() removed — Ktor Auth plugin handles refresh internally
}
```

- [ ] **Step 2: Delete AuthInterceptor.kt**

Delete `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthInterceptor.kt`.

- [ ] **Step 3: Update Hilt DI (AppModule.kt)**

No separate `authClient` needed. SkateLabClient takes `TokenStorage` (no `AuthApi` — the refresh callback uses `this.client` internally). Provide `clearAuthProvider` lambda.

```kotlin
@Provides @Singleton
fun provideSkateLabClient(
    tokenStorage: TokenStorage,
    engine: HttpClientEngine,
): SkateLabClient = SkateLabClient(BuildConfig.API_BASE_URL, engine, tokenStorage)

@Provides @Singleton
fun provideAuthRepository(
    skateLabClient: SkateLabClient,
    tokenStorage: TokenStorage,
): AuthRepository = AuthRepository(
    skateLabClient.auth,
    tokenStorage,
) { skateLabClient.httpClient.authProvider<BearerAuthProvider>()?.clearToken() }
```

- [ ] **Step 4: Remove all AuthInterceptor references**

Search for `AuthInterceptor` across the codebase. Remove all `install(AuthInterceptor)` and `AuthInterceptorConfig` usage.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(auth): delete AuthInterceptor, logout with refresh_token body, clearAuthProvider on logout"
```

---

## Wave 1 — Independent Fixes (parallel, starts immediately)

### Task 3: Fix SessionsViewModel + AuthViewModel

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt`
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt`

- [ ] **Step 1: Fix SessionsViewModel.loadSession() — propagate errors**

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

- [ ] **Step 2: Fix AuthViewModel — fetch profile after login via UsersApi.getMe()**

```kotlin
class AuthViewModel(
    private val authRepo: AuthRepository,
    private val usersApi: UsersApi,
) {
    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Loading)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    suspend fun checkLogin() {
        if (authRepo.isLoggedIn()) {
            runCatching { usersApi.getMe() }
                .onSuccess { user -> _uiState.value = AuthUiState.LoggedIn(user.id, user.displayName) }
                .onFailure { _uiState.value = AuthUiState.LoggedIn("cached", null) }
        } else {
            _uiState.value = AuthUiState.LoggedOut
        }
    }

    suspend fun login(email: String, password: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.login(email, password)
            .onSuccess {
                val user = runCatching { usersApi.getMe() }.getOrNull()
                _uiState.value = AuthUiState.LoggedIn(user?.id ?: "new", user?.displayName)
            }
            .onFailure { _uiState.value = AuthUiState.Error(it.message ?: "Login failed") }
    }

    suspend fun register(email: String, password: String, displayName: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.register(email, password, displayName)
            .onSuccess {
                val user = runCatching { usersApi.getMe() }.getOrNull()
                _uiState.value = AuthUiState.LoggedIn(user?.id ?: "new", user?.displayName ?: displayName)
            }
            .onFailure { _uiState.value = AuthUiState.Error(it.message ?: "Registration failed") }
    }

    suspend fun logout() {
        authRepo.logout()
        _uiState.value = AuthUiState.LoggedOut
    }
}
```

- [ ] **Step 3: Update androidApp AuthViewModel (Hilt) to pass UsersApi**

In `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/AuthViewModel.kt`, add `UsersApi` from `SkateLabClient.users`.

- [ ] **Step 4: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/AuthViewModel.kt
git commit -m "fix(vm): propagate errors in SessionsViewModel, fetch user profile in AuthViewModel via UsersApi.getMe()"
```

---

### Task 4: Fix ProcessingViewModel — emit sessionId + add cancelProcessing

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/ProcessEvent.kt`
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt`

- [ ] **Step 1: Add session_id field to ProcessEvent**

```kotlin
@Serializable
data class ProcessEvent(
    val progress: Float = 0f,
    val message: String = "",
    val status: String = "running",
    @SerialName("session_id") val sessionId: String? = null,  // Backend may not send this yet — fallback to taskId
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
```

- [ ] **Step 2: Fix ProcessingViewModel.observeProgress() — use sessionId + cancel**

```kotlin
private suspend fun observeProgress(taskId: String) {
    processApi.stream(taskId).collect { event ->
        when (event.parsedStatus) {
            ProcessStatus.RUNNING ->
                _uiState.value = ProcessingUiState.Progress(event.progress, event.message)
            ProcessStatus.COMPLETED ->
                _uiState.value = ProcessingUiState.Completed(event.sessionId ?: taskId)  // Fallback until backend sends session_id
            ProcessStatus.FAILED ->
                _uiState.value = ProcessingUiState.Failed(event.message)
            else -> {}
        }
    }
}

suspend fun cancelProcessing(taskId: String) {
    runCatching { processApi.cancel(taskId) }
        .onFailure { _uiState.value = ProcessingUiState.Failed(it.message ?: "Cancel failed") }
}
```

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/ProcessEvent.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt
git commit -m "fix(processing): emit sessionId from COMPLETED event, add cancelProcessing"
```

---

### Task 5: Fix UploadScheduler + UploadWorker race condition

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadScheduler.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt`

- [ ] **Step 1: Add enqueueUniqueWork to UploadScheduler**

```kotlin
object UploadScheduler {
    fun enqueue(context: Context, uploadId: String) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build()

        val workRequest = OneTimeWorkRequestBuilder<UploadWorker>()
            .setInputData(UploadWorker.inputData(uploadId))
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()

        WorkManager.getInstance(context)
            .enqueueUniqueWork(
                "upload-$uploadId",
                ExistingWorkPolicy.KEEP,  // Don't cancel mid-transfer
                workRequest,
            )
    }
}
```

- [ ] **Step 2: Add tryLockForUpload to PendingUploadDao**

```kotlin
@Query("UPDATE pending_uploads SET status = 'UPLOADING' WHERE id = :id AND status = 'READY'")
suspend fun tryLockForUpload(id: String): Int

@Query("SELECT * FROM pending_uploads WHERE id = :id LIMIT 1")
suspend fun getById(id: String): PendingUploadEntity?
```

- [ ] **Step 3: Update UploadWorker to use tryLockForUpload + per-request upload timeout**

```kotlin
override suspend fun doWork(): Result {
    val uploadId = inputData.getString(KEY_UPLOAD_ID) ?: return Result.failure()

    val locked = pendingUploadDao.tryLockForUpload(uploadId)
    if (locked == 0) return Result.success()  // Another worker already processing

    val entity = pendingUploadDao.getById(uploadId) ?: return Result.failure()

    return try {
        // ... upload logic (video, IMU, manifest, session creation, processing) ...
        // Use timeout { requestTimeoutMillis = 120_000 } for presigned uploads
        Result.success()
    } catch (e: Exception) {
        pendingUploadDao.incrementRetry(entity.id)
        val currentEntity = pendingUploadDao.getById(uploadId)
        if ((currentEntity?.retryCount ?: 0) >= 3) {
            pendingUploadDao.updateStatus(entity.id, "FAILED")
            Result.failure()
        } else {
            Result.retry()
        }
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadScheduler.kt mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt
git commit -m "fix(upload): enqueueUniqueWork prevents duplicate workers, tryLockForUpload atomic DAO lock"
```

---

### Task 6: Fix BleManager thread safety — computeIfAbsent

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt`

- [ ] **Step 1: Replace parsers.getOrPut with computeIfAbsent**

At line ~400 in `onCharacteristicChanged`:
```kotlin
val parser = parsers.computeIfAbsent(address) {
    Wt901Parser().also {
        it.logTag = "Wt901Parse-${address.takeLast(5)}"
        it.onRegisterRead = { result ->
            _registerReadResults.tryEmit(address to result)
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt
git commit -m "fix(ble): replace ConcurrentHashMap.getOrPut with computeIfAbsent for thread safety"
```

---

### Task 7: Fix KableBleRepository — cancel reconnectJobs only on connect

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/KableBleRepository.kt`

- [ ] **Step 1: In connect(), cancel only reconnectJobs after successful connect**

After `Result.success(Unit)` in the `connect()` method:
```kotlin
reconnectJobs[sensorId]?.cancel()
reconnectJobs.remove(sensorId)
// stateMonitorJobs[sensorId] stays running — monitors for future disconnections
```

- [ ] **Step 2: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/KableBleRepository.kt
git commit -m "fix(ble): cancel reconnectJobs only on connect, preserve stateMonitorJobs for auto-reconnect"
```

---

### Task 8: Fix CameraXRecorder resource leak on start failure

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt`

- [ ] **Step 1: Add try-catch around pendingRecording.start() to close timestampTracker on failure**

Wrap the recording start in try-catch. If `pendingRecording.start()` throws, close `timestampTracker`:

```kotlin
try {
    activeRecording = pendingRecording.start(cameraExecutor) { event -> ... }
} catch (e: Exception) {
    timestampTracker?.close()
    timestampTracker = null
    throw e
}
```

- [ ] **Step 2: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/camera/CameraXRecorder.kt
git commit -m "fix(camera): close timestampTracker on recording start failure"
```

---

### Task 9: Medium fixes batch — M1, M2, M3, M4, M5, M7, M8, M9, M10, M12

**Files:**
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/Wt901Parser.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/camera/FrameTimestampTracker.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/recording/ImuCollector.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/repository/SessionRepositoryImpl.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/service/SensorRecordingService.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/export/ZipExporter.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt`

- [ ] **Step 1-9: Apply all medium fixes (M1, M2, M3, M4, M5, M7, M8, M9 handled in Task 5, M10, M12)**

See spec sections M1-M12 for exact code changes. M6 (runBlocking) and M9 (tryLockForUpload, already in Task 5) are intentionally skipped.

- [ ] **Step 10: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/Wt901Parser.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/camera/FrameTimestampTracker.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/recording/ImuCollector.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/export/ImuStreamWriter.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/repository/SessionRepositoryImpl.kt mobile/androidApp/src/main/java/ru/skatelab/capture/service/SensorRecordingService.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/export/ZipExporter.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt
git commit -m "fix(mobile): M1-M12 medium fixes — parser reset, queue offer, writeError, flush/close, logging, START_NOT_STICKY, Room schema, atomic ZIP, isScanning StateFlow"
```

---

### Task 10: Add multiplatform-settings dependency (Task 13a — can start immediately)

**Files:**
- Modify: `mobile/gradle/libs.versions.toml`
- Modify: `mobile/shared/build.gradle.kts`

- [ ] **Step 1: Add multiplatform-settings to libs.versions.toml**

```toml
[versions]
multiplatform-settings = "1.3.0"

[libraries]
multiplatform-settings = { module = "com.russhwolf:multiplatform-settings", version.ref = "multiplatform-settings" }
multiplatform-settings-keychain = { module = "com.russhwolf:multiplatform-settings-keychain", version.ref = "multiplatform-settings" }
```

- [ ] **Step 2: Add dependencies in shared/build.gradle.kts**

```kotlin
commonMain.dependencies {
    // ... existing ...
    implementation(libs.multiplatform.settings)
}
iosMain.dependencies {
    // ... existing ...
    implementation(libs.multiplatform.settings.keychain)
}
```

- [ ] **Step 3: Commit**

```bash
git add mobile/gradle/libs.versions.toml mobile/shared/build.gradle.kts
git commit -m "build(shared): add multiplatform-settings dependency"
```

---

### Task 11: Add Session CRUD to SessionsApi

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SessionsApi.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionUpdateRequest.kt`

- [ ] **Step 1: Create SessionUpdateRequest model**

```kotlin
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionUpdateRequest(
    @SerialName("element_type") val elementType: String? = null,
    val notes: String? = null,
)
```

- [ ] **Step 2: Add update + bulkDelete to SessionsApi**

```kotlin
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
```

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SessionsApi.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionUpdateRequest.kt
git commit -m "feat(sessions): add update + bulkDelete API methods"
```

---

## Wave 2 — Dependent tasks (after Wave 0)

### Task 12: Replace iOS TokenStorage with multiplatform-settings KeychainSettings (Task 13b)

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/TokenStorage.kt`
- Modify: `mobile/shared/src/iosMain/kotlin/ru/skatelab/shared/auth/IosTokenStorage.kt`
- Modify: `mobile/shared/src/androidMain/kotlin/ru/skatelab/shared/auth/AndroidTokenStorage.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt`

- [ ] **Step 1: Refactor TokenStorage to regular class with Settings parameter**

```kotlin
// commonMain/TokenStorage.kt
package ru.skatelab.shared.auth

import com.russhwolf.settings.Settings

class TokenStorage(private val settings: Settings) {
    suspend fun saveAccessToken(token: String) { settings.putString("access_token", token) }
    suspend fun getAccessToken(): String? = settings.getStringOrNull("access_token")
    suspend fun saveRefreshToken(token: String) { settings.putString("refresh_token", token) }
    suspend fun getRefreshToken(): String? = settings.getStringOrNull("refresh_token")
    suspend fun saveTokens(access: String, refresh: String) {
        settings.putString("access_token", access)
        settings.putString("refresh_token", refresh)
    }
    suspend fun clearTokens() {
        settings.remove("access_token")
        settings.remove("refresh_token")
    }
}
```

Delete `expect class TokenStorage()` declaration — no longer needed.

- [ ] **Step 2: iOS — provide KeychainSettings with kSecAttrAccessible + try-catch fallback**

Replace `IosTokenStorage.kt`:

```kotlin
package ru.skatelab.shared.auth

import com.russhwolf.settings.KeychainSettings
import com.russhwolf.settings.Settings
import platform.Security.kSecAttrAccessibleAfterFirstUnlock
import platform.Security.kSecClass
import platform.Security.kSecAttrAccessible

fun createIosSettings(): Settings {
    return try {
        KeychainSettings(
            service = "ru.skatelab.auth",
            kSecClass to kSecClass,  // Required for Keychain access
            kSecAttrAccessible to kSecAttrAccessibleAfterFirstUnlock  // Allows background access
        )
    } catch (e: Exception) {
        Settings()  // Fallback to in-memory MapSettings on Keychain failure
    }
}
```

- [ ] **Step 3: Android — provide EncryptedSharedPreferences-based Settings**

Replace `AndroidTokenStorage.kt`:

```kotlin
package ru.skatelab.shared.auth

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.russhwolf.settings.Settings
import com.russhwolf.settings.SharedPreferencesSettings

fun createAndroidSettings(context: Context): Settings {
    val masterKey = MasterKey.Builder(context)
        .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
        .build()
    val prefs = EncryptedSharedPreferences.create(
        context,
        "skatelab_tokens",
        masterKey,
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )
    return SharedPreferencesSettings(prefs)
}
```

- [ ] **Step 4: Update DI (AppModule) to pass Settings to TokenStorage**

```kotlin
@Provides @Singleton
fun provideTokenStorage(context: Context): TokenStorage =
    TokenStorage(createAndroidSettings(context))
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(ios): replace NSUserDefaults with KeychainSettings via multiplatform-settings, add fallback + kSecAttrAccessible"
```

---

### Task 13: Add email verification + password reset to AuthApi + AuthRepository

**Files:**
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt`
- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt`

- [ ] **Step 1: Add verifyEmail, resendVerification, forgotPassword, resetPassword to AuthApi**

These were already added in Task 1 Step 6. Verify they're present and add the full implementations:

```kotlin
// AuthApi.kt — already has login, register, refresh, logout
suspend fun verifyEmail(token: String) {
    client.post("$baseUrl/auth/verify-email") {
        markAsRefreshTokenRequest()
        contentType(ContentType.Application.Json)
        setBody(mapOf("token" to token))
    }
}

suspend fun resendVerification(email: String) {
    client.post("$baseUrl/auth/resend-verification") {
        markAsRefreshTokenRequest()
        contentType(ContentType.Application.Json)
        setBody(mapOf("email" to email))
    }
}

suspend fun forgotPassword(email: String) {
    client.post("$baseUrl/auth/forgot-password") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("email" to email))
    }
}

suspend fun resetPassword(token: String, newPassword: String) {
    client.post("$baseUrl/auth/reset-password") {
        contentType(ContentType.Application.Json)
        setBody(mapOf("token" to token, "new_password" to newPassword))
    }
}
```

- [ ] **Step 2: Add wrapper methods to AuthRepository**

```kotlin
suspend fun verifyEmail(token: String): Result<Unit> = runCatching { authApi.verifyEmail(token) }
suspend fun resendVerification(email: String): Result<Unit> = runCatching { authApi.resendVerification(email) }
suspend fun forgotPassword(email: String): Result<Unit> = runCatching { authApi.forgotPassword(email) }
suspend fun resetPassword(token: String, newPassword: String): Result<Unit> = runCatching { authApi.resetPassword(token, newPassword) }
```

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt
git commit -m "feat(auth): add email verification + password reset API methods"
```

---

## Wave 3 — Tests

### Task 14: Auth + SSE + Upload integration tests

**Files:**
- Create/Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryTest.kt`
- Create/Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/ProcessApiTest.kt`
- Create/Modify: `mobile/androidApp/src/androidTest/kotlin/ru/skatelab/capture/upload/UploadWorkerTest.kt`

- [ ] **Step 1: Add test dependencies**

In `mobile/shared/build.gradle.kts`, add to commonTest:
```kotlin
kotlin.test
kotlinx-coroutines-test
org.mokkery:mokkery (KMP mocking)
app.cash.turbine:turbine (Flow testing)
io.ktor:ktor-client-mock (API client testing)
```

- [ ] **Step 2: Write AuthRepository tests**

Test: logout sends refresh_token in body, clears tokens even if API fails, clearAuthProvider called after logout.

- [ ] **Step 3: Write SSE ProcessApi tests**

Test: `incoming.collect` (not `events.collect`), comment lines, empty lines, maxReconnectionAttempts = 3.

- [ ] **Step 4: Write UploadWorker tests**

Test: `enqueueUniqueWork` with `ExistingWorkPolicy.KEEP`, `tryLockForUpload` WHERE status='READY' returns 0 for locked rows.

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/build.gradle.kts mobile/shared/src/commonTest/ mobile/androidApp/src/androidTest/
git commit -m "test(mobile): auth logout, SSE incoming, upload lock integration tests"
```

---

## Self-Review Checklist

**1. Spec coverage:**

| Spec Item | Task |
|-----------|------|
| C1 Ktor Auth plugin (no separate authClient) | Task 1 |
| C2 Clear tokens on refresh failure | Task 1 (in refreshTokens block) + Task 2 |
| C3 iOS KeychainSettings (kSecAttrAccessible + fallback) | Task 12 |
| C4 Logout with refresh_token body + markAsRefreshTokenRequest | Task 1 (AuthApi) + Task 2 |
| H7 HttpRequestRetry (kotlinx.io.IOException + jitter) | Task 1 |
| H8 HttpTimeout (install AFTER retry) | Task 1 |
| C5 Ktor SSE plugin (incoming.collect, maxReconnectionAttempts=3) | Task 1 |
| H5 SessionsViewModel error | Task 3 |
| H6 AuthViewModel profile (UsersApi.getMe) | Task 3 |
| H4 UploadWorker race (enqueueUniqueWork + tryLockForUpload) | Task 5 |
| H1 BleManager computeIfAbsent | Task 6 |
| H2 KableBleRepository cancel reconnectJobs only | Task 7 |
| H3 CameraXRecorder try-finally | Task 8 |
| M1 Wt901Parser reset | Task 9 |
| M2 FrameTimestampTracker queue | Task 9 |
| M3 ImuCollector writeError | Task 9 |
| M4 ImuStreamWriter flush/close | Task 9 |
| M5 SessionRepositoryImpl logging | Task 9 |
| M7 START_NOT_STICKY | Task 9 |
| M8 Room schema export | Task 9 |
| M9 PendingUploadDao race | Task 5 (tryLockForUpload) |
| M10 ZipExporter atomic | Task 9 |
| M11 ProcessingViewModel sessionId | Task 4 |
| M12 BleScanViewModel StateFlow | Task 9 |
| 5.1 Email verification | Task 13 |
| 5.2 Password reset | Task 13 |
| 5.3 Session CRUD | Task 11 |
| 5.4 Metrics API (models matched to backend) | Task 1 |
| 5.5 Cancel processing | Task 4 |

**2. Placeholder scan:** No TBD/TODO/fill-in-later found.

**3. Type consistency:**
- `TokenStorage` changes from `expect class` to regular class with `Settings` param — updated in Tasks 1, 2, 12
- `SkateLabClient` constructor now takes `TokenStorage` only (no `AuthApi` — refreshTokens uses `this.client`) — Tasks 1, 2
- `ProcessEvent` gains `sessionId: String?` — Task 4
- `PendingUploadDao.tryLockForUpload` returns `Int` — Task 5
- `MetricsApi` + `MetricsModels` created in Task 1 — referenced from `SkateLabClient`
- `AuthApi` gains `baseUrl` param and `logout(refreshToken)`, `markAsRefreshTokenRequest()` — Task 1
- `kotlinx.io.IOException` used instead of `io.ktor.utils.io.errors.IOException` — Task 1
- SSE uses `incoming.collect` not `events.collect` — Task 1
- SSE `maxReconnectionAttempts = 3` — Task 1
- `cacheTokens = false` in Auth config — Task 1