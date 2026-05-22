# Mobile Audit Fixes — Research Agent Report

Date: 2026-05-22
Agents: 5 specialized (Auth+Security, Network+SSE, BLE+Camera+Data, Architecture+Parallelism, ViewModel+API)

## Executive Summary

5 research agents reviewed the implementation plan and design spec. Found **13 corrections** (3 critical bugs, 4 important, 6 improvements) and **1 major parallelization optimization** (9 of 17 tasks can start immediately, not after Auth).

---

## Critical Bugs (must fix before implementation)

### C-1: Logout requires refresh token in body + markAsRefreshTokenRequest

**Plan's code:**
```kotlin
suspend fun logout() {
    runCatching { authApi.logout() }  // sends POST with NO body
    tokenStorage.clearTokens()
}
```

**Bug:** Backend `/auth/logout` requires `RefreshRequest` body with `refresh_token`. Also, if `clearTokens()` runs before logout completes, Ktor Auth won't send auth headers.

**Fix:**
```kotlin
suspend fun logout() {
    val refreshToken = tokenStorage.getRefreshToken()
    if (refreshToken != null) {
        runCatching { authApi.logout(refreshToken) }
    }
    tokenStorage.clearTokens()
}

// AuthApi.kt
suspend fun logout(refreshToken: String) {
    client.post("/auth/logout") {
        markAsRefreshTokenRequest()  // skip Auth plugin for this request
        contentType(ContentType.Application.Json)
        setBody(mapOf("refresh_token" to refreshToken))
    }
}
```

### C-2: SSE `events.collect` does not exist — must use `incoming.collect`

**Plan's code:**
```kotlin
client.sse("/process/$taskId/stream") {
    events.collect { event -> ... }  // BUG: events is not a property
}
```

**Fix:**
```kotlin
client.sse("/process/$taskId/stream") {
    incoming.collect { event -> ... }  // Correct: incoming is the Flow<ClientSSEEvent>
}
```

### C-3: SSE auto-reconnect is DISABLED by default — must set maxReconnectionAttempts

**Plan's code:**
```kotlin
install(SSE) {
    reconnectionTime = 5000  // Only sets delay between attempts
}
```

**Fix:**
```kotlin
install(SSE) {
    reconnectionTime = 5000
    maxReconnectionAttempts = 3  // REQUIRED — default is 0 (disabled)
}
```

---

## Important Corrections

### I-1: Use kotlinx.io.IOException, not io.ktor.utils.io.errors.IOException

Ktor 3.x migrated to `kotlinx.io.IOException`. The old package still exists but is for POSIX-specific errors. All Ktor exception types (SocketTimeoutException, ConnectTimeoutException, HttpRequestTimeoutException) extend `kotlinx.io.IOException`.

```kotlin
// WRONG:
cause is io.ktor.utils.io.errors.IOException

// CORRECT:
cause is kotlinx.io.IOException
```

### I-2: No separate authClient needed — use Ktor's built-in refreshTokens client

The plan creates a separate `authClient` (no-auth) for AuthApi. This is unnecessary. Ktor's `refreshTokens` callback provides `this.client` which is the same HttpClient but with `AuthCircuitBreaker` set, preventing infinite 401 loops.

**Simplified approach:**
```kotlin
install(Auth) {
    bearer {
        loadTokens { ... }
        refreshTokens {
            val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
            client.post("$baseUrl/auth/refresh") {
                markAsRefreshTokenRequest()
                contentType(ContentType.Application.Json)
                setBody(mapOf("refresh_token" to refreshToken))
            }.body<TokenResponse>()
        }
    }
}
```

This eliminates the separate `authClient` in AppModule and simplifies DI.

### I-3: cacheTokens = true causes stale tokens after login

By default, `BearerAuthProvider` caches `loadTokens()` result in memory. After login/register, new tokens saved to `TokenStorage` won't be picked up because the cached `null` is still valid.

**Fix:** Either:
- Set `cacheTokens = false` (simpler, slight perf cost of reading from Settings on every request), OR
- Call `httpClient.authProvider<BearerAuthProvider>()?.clearToken()` after login/register

### I-4: MetricsApi models don't match backend — 9 mismatches

| Field in plan | Backend actual | Fix |
|---|---|---|
| `MetricsRegistryResponse.metrics: List<MetricDefinition>` | Dict keyed by metric name | Change to `Map<String, MetricDefinition>` |
| `TrendResponse.metricId` | `metric_name` | `@SerialName("metric_name") val metricName` |
| `TrendPoint` (date, value) | `TrendDataPoint` (session_id, value, is_pr, date) | Add missing fields |
| `TrendResponse` missing fields | `element_type`, `current_pr`, `reference_range` | Add with defaults |
| `PersonalRecord.metricId` | `metric_name` | `@SerialName("metric_name") val metricName` |
| `PersonalRecord.achievedAt` | Does not exist | Remove |
| `DiagnosticCheck` (name, status, message) | `DiagnosticsFinding` (severity, element, metric, message, detail) | Fix field names |
| `DiagnosticsResponse.sessionId` | `user_id` | `@SerialName("user_id") val userId` |
| `SummaryResponse` shape | Different structure with `element`, `period`, `findings` | Rebuild from backend schema |

### I-5: Backend does NOT send session_id in SSE completed event

The SSE stream sends `{"status": "completed", "progress": 1.0, "message": "Done"}` — no `session_id`. The mobile `ProcessEvent` fallback `event.sessionId ?: taskId` is correct for backward compatibility, but the backend needs a separate PR to add `session_id` to the task state and completed event.

### I-6: KeychainSettings has known iOS 16 crash + errSecInteractionNotAllowed

Add `kSecAttrAccessible` and try-catch fallback:
```kotlin
actual val settings: Settings by lazy {
    try {
        KeychainSettings(
            service = "ru.skatelab.auth",
            kSecAttrAccessible to kSecAttrAccessibleAfterFirstUnlock
        )
    } catch (e: Exception) {
        Settings()  // Falls back to in-memory MapSettings
    }
}
```

---

## Improvements

### P-1: Add jitter to exponential backoff

```kotlin
exponentialDelay(
    base = 2.0,
    baseDelayMs = 500,
    maxDelayMs = 8_000,
    randomizationMs = 500,  // Prevent thundering herd
    respectRetryAfter = true
)
```

### P-2: addressToSensorId change is a no-op

`addressToSensorId[address]` on ConcurrentHashMap already returns null for missing keys. The `?: return@onCharacteristicChanged` pattern handles it. No change needed.

### P-3: ImuStreamWriter.close() fix is defense-in-depth, not critical

Current code uses `@Synchronized` which already prevents double-close. The null-first + try-finally pattern adds safety but isn't fixing a real bug.

### P-4: Kable 0.35 migration deferred

Kable 0.35.0-rc eliminates the entire manual job management pattern (5 ConcurrentHashMaps). Migrate after stable release, not in this bug-fix cycle.

### P-5: Deep links — Compose Navigation has built-in KMP support

No external library needed. Use `navDeepLink` in shared module + `AndroidManifest.xml` intent filter.

### P-6: Mokkery + Turbine for KMP testing

Add `org.mokkery:mokkery` and `app.cash.turbine:turbine` to commonTest for proper ViewModel and Flow testing.

---

## Parallelization Optimization

### Original plan: 5 sequential waves (Auth blocks everything)

### Revised: Only SkateLabClient.kt is a serial bottleneck

**9 of 17 tasks are fully independent of Auth and can start immediately:**

| Task | Files | Dependency |
|---|---|---|
| Task 6 (ViewModels) | SessionsViewModel, AuthViewModel | None |
| Task 7 (ProcessingVM) | ProcessEvent, ProcessingViewModel | None |
| Task 8 (UploadWorker) | UploadScheduler, UploadWorker, PendingUploadDao | None |
| Task 9 (BleManager) | BleManager.kt | None |
| Task 10 (KableBle) | KableBleRepository.kt | None |
| Task 11 (Camera) | CameraXRecorder.kt | None |
| Task 12 (Medium fixes) | 9 androidApp files | None |
| Task 13a (Settings dep) | build.gradle.kts | None |
| Task 15 (Session CRUD) | SessionsApi, new model | None |

**Proposed consolidated task for SkateLabClient.kt:**

Collapse Tasks 1, 4, 5, 16 into one "network client overhaul" task that modifies SkateLabClient.kt once:
- Install Auth plugin (C1)
- Install HttpRequestRetry + HttpTimeout (H7+H8)
- Install SSE plugin (C5)
- Add metrics API reference (5.4)

This eliminates 3 context switches on the same file.

**Revised wave structure:**

```
Wave 0 (T1): SkateLabClient overhaul (Auth + Retry + Timeout + SSE + metrics) + Delete AuthInterceptor
Wave 1 (parallel, starts immediately):
  T-A: Task 13a (multiplatform-settings dependency)
  T-B: Task 9 + 10 + 11 (BLE + Camera)
  T-C: Task 12 (Medium fixes)
  T-D: Task 7 (ProcessingViewModel)
  T-E: Task 6 (ViewModels) — after T1 for UsersApi dep
  T-F: Task 8 (UploadWorker)
  T-G: Task 15 (Session CRUD)
Wave 2 (after Wave 0):
  T-H: Task 13b (TokenStorage refactor)
  T-I: Task 14 (Email verify + password reset)
  T-J: Task 17 (Cancel processing)
Wave 3: Task 3 (Auth tests)
```

**Estimated wall-clock reduction: ~40-50%**

---

## Rollback Safety

Use feature branches:
- `feature/mobile-bugfixes-independent` (Tasks 6-12, 13a, 15) — merges first, zero auth dependency
- `feature/mobile-auth-overhaul` (consolidated SkateLabClient + AuthInterceptor delete) — merges after testing
- `feature/mobile-new-integrations` (Tasks 13b, 14, 16, 17) — merges last, rebased onto auth

If auth breaks after merge, `git revert` the auth commit. BLE/Camera/Data fixes are untouched.