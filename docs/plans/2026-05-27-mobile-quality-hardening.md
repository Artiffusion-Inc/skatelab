# Mobile Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden SkateLab Android app for production: sealed error hierarchy, i18n extraction (EN default + RU locale), accessibility semantics, security (ProGuard + network config + cert pinning).

**Architecture:** Phase 1 builds the AppError sealed interface in shared/commonMain — unblocks all subsequent work. Phase 2 runs 3 parallel streams (i18n, accessibility, security). Each stream is further parallelizable by file/task. BleScanStatus enum replaces ViewModel status strings.

**Tech Stack:** Kotlin Multiplatform, Jetpack Compose M3, Hilt, Room, Ktor, Kable BLE, Android string resources (R.string), ProGuard/R8, Network Security Config.

**Specs:** `docs/specs/2026-05-27-mobile-quality-hardening-design.md`, `docs/specs/2026-05-27-mobile-quality-hardening-parallelization-report.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/AppError.kt` | Sealed error hierarchy (commonMain) |
| `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/utils/ExceptionMapping.kt` | Throwable → AppError, HttpStatusCode → AppError |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt` | Tests for exception mapping |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt` | Tests for AppError in SessionsViewModel |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/domain/model/BleScanStatus.kt` | Enum for BLE scan status strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/utils/AppErrorExt.kt` | AppError.asString() Composable extension |
| `mobile/androidApp/src/main/res/values-ru/strings.xml` | Russian locale strings (copy from values/) |
| `mobile/androidApp/src/main/res/xml/network_security_config.xml` | Certificate pinning config |
| `mobile/androidApp/src/main/res/xml/charts_a11y_test.xml` | (if needed for accessibility test configs) |

### Modified files

| File | Changes |
|------|---------|
| `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt` | `Error(val error: AppError)` instead of `Error(val message: String)` |
| `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt` | Same pattern |
| `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt` | `Failed(val error: AppError)` instead of `Failed(val message: String)` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt` | Guard `fallbackToDestructiveMigration` with `BuildConfig.DEBUG` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt` | `StateFlow<BleScanStatus?>` instead of `StateFlow<String?>` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt` | Map BleScanStatus → stringResource, extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt` | Use AppError.asString(), extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/LoginScreen.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt` | Extract hardcoded strings, add semantics |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt` | Extract hardcoded strings, add chart semantics |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationScreen.kt` | Extract hardcoded strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/MoreScreen.kt` | Add contentDescription, extract strings |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt` | Add contentDescription |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/skeleton/SkeletonOverlay.kt` | Add clearAndSetSemantics |
| `mobile/androidApp/src/main/AndroidManifest.xml` | Add `android:networkSecurityConfig` |
| `mobile/androidApp/proguard-rules.pro` | Replace with narrow keeps |
| `mobile/androidApp/src/main/res/values/strings.xml` | English as default, add new keys |
| `mobile/androidApp/build.gradle.kts` | Add BuildConfig feature flag |

---

## Phase 1 — Foundation (Sequential, ~30 min)

These tasks MUST complete before Phase 2 starts. They create the AppError hierarchy that all i18n error strings depend on.

---

### Task 1: Create AppError sealed interface

**Files:**

- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/AppError.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt`

- [ ] **Step 1: Write the failing test**

```kotlin
// mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt
package ru.skatelab.shared.models

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class AppErrorTest {

    @Test
    fun appErrorSubtypesHaveCorrectMessageKeys() {
        assertEquals("error_network", AppError.Network().messageKey)
        assertEquals("error_auth", AppError.Auth().messageKey)
        assertEquals("error_not_found", AppError.NotFound().messageKey)
        assertEquals("error_server", AppError.Server().messageKey)
        assertEquals("error_timeout", AppError.Timeout().messageKey)
        assertEquals("error_unknown", AppError.Unknown().messageKey)
    }

    @Test
    fun appErrorSubtypesAreDataClasses() {
        val err = AppError.Network()
        assertIs<AppError.Network>(err)
        // Data class equality
        assertEquals(AppError.Network(), AppError.Network())
        assertEquals(AppError.Auth(), AppError.Auth())
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest --tests "ru.skatelab.shared.models.AppErrorTest" 2>&1 | tail -5`
Expected: FAIL — `Unresolved reference: AppError`

- [ ] **Step 3: Write the implementation**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/AppError.kt
package ru.skatelab.shared.models

sealed interface AppError {
    val messageKey: String

    data class Network(override val messageKey: String = "error_network") : AppError
    data class Auth(override val messageKey: String = "error_auth") : AppError
    data class NotFound(override val messageKey: String = "error_not_found") : AppError
    data class Server(override val messageKey: String = "error_server") : AppError
    data class Timeout(override val messageKey: String = "error_timeout") : AppError
    data class Unknown(override val messageKey: String = "error_unknown") : AppError
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest --tests "ru.skatelab.shared.models.AppErrorTest" 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/AppError.kt mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt
git commit -m "feat(shared): add AppError sealed interface for typed error hierarchy"
```

---

### Task 2: Create ExceptionMapping utility

**Files:**

- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/utils/ExceptionMapping.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt` (extend existing)

- [ ] **Step 1: Write the failing test**

Add to `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt`:

```kotlin
import ru.skatelab.shared.utils.toAppError
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.http.HttpStatusCode
import kotlinx.io.IOException

    @Test
    fun toAppError_mapsTimeoutExceptions() {
        assertIs<AppError.Timeout>(SocketTimeoutException("timeout").toAppError())
        assertIs<AppError.Timeout>(HttpRequestTimeoutException().toAppError())
    }

    @Test
    fun toAppError_mapsIOExceptionToNetwork() {
        assertIs<AppError.Network>(IOException().toAppError())
    }

    @Test
    fun toAppError_mapsUnknownToUnknown() {
        assertIs<AppError.Unknown>(RuntimeException("boom").toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps401ToAuth() {
        assertIs<AppError.Auth>(HttpStatusCode.Unauthorized.toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps404ToNotFound() {
        assertIs<AppError.NotFound>(HttpStatusCode.NotFound.toAppError())
    }

    @Test
    fun httpStatusCodeToAppError_maps5xxToServer() {
        assertIs<AppError.Server>(HttpStatusCode.InternalServerError.toAppError())
        assertIs<AppError.Server>(HttpStatusCode(503).toAppError())
    }
```

Note: imports for `IOException`, `SocketTimeoutException`, `HttpRequestTimeoutException` come from Ktor dependencies already in shared module. If `kotlinx.io.IOException` doesn't resolve, use `java.io.IOException` in `jvmAndroidMain` with expect/actual. For commonTest on JVM, `kotlinx.io.IOException` should work since Ktor brings it in.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest --tests "ru.skatelab.shared.models.AppErrorTest" 2>&1 | tail -5`
Expected: FAIL — `Unresolved reference: toAppError`

- [ ] **Step 3: Write the implementation**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/utils/ExceptionMapping.kt
package ru.skatelab.shared.utils

import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.http.HttpStatusCode
import kotlinx.io.IOException
import ru.skatelab.shared.models.AppError

fun Throwable.toAppError(): AppError = when (this) {
    is SocketTimeoutException, is HttpRequestTimeoutException -> AppError.Timeout()
    is IOException -> AppError.Network()
    else -> AppError.Unknown()
}

fun HttpStatusCode.toAppError(): AppError = when (value) {
    401 -> AppError.Auth()
    404 -> AppError.NotFound()
    in 500..599 -> AppError.Server()
    else -> AppError.Unknown()
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest --tests "ru.skatelab.shared.models.AppErrorTest" 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/utils/ExceptionMapping.kt mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/AppErrorTest.kt
git commit -m "feat(shared): add ExceptionMapping — Throwable/HttpStatusCode → AppError"
```

---

### Task 3: Refactor SessionsViewModel to use AppError

**Files:**

- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt`

- [ ] **Step 1: Write the failing test**

```kotlin
// mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt
package ru.skatelab.shared.state

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import ru.skatelab.shared.models.AppError

class SessionsViewModelTest {

    @Test
    fun errorStateCarriesAppErrorNotString() {
        val state = SessionsUiState.Error(AppError.Network())
        assertIs<AppError.Network>((state as SessionsUiState.Error).error)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest --tests "ru.skatelab.shared.state.SessionsViewModelTest" 2>&1 | tail -5`
Expected: FAIL — `Unresolved reference: error` (field is `message`, not `error`)

- [ ] **Step 3: Refactor SessionsViewModel**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt
package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.utils.toAppError

sealed interface SessionsUiState {
    data object Loading : SessionsUiState
    data class Loaded(val sessions: List<SessionResponse>, val total: Int, val page: Int) : SessionsUiState
    data class Error(val error: AppError) : SessionsUiState
}

class SessionsViewModel(private val sessionsApi: SessionsApi) {
    private val _uiState = MutableStateFlow<SessionsUiState>(SessionsUiState.Loading)
    val uiState: StateFlow<SessionsUiState> = _uiState.asStateFlow()

    private val _selectedSession = MutableStateFlow<SessionResponse?>(null)
    val selectedSession: StateFlow<SessionResponse?> = _selectedSession.asStateFlow()

    suspend fun loadSessions(page: Int = 1, limit: Int = 20) {
        _uiState.value = SessionsUiState.Loading
        try {
            val offset = (page - 1) * limit
            val response = sessionsApi.list(limit, offset)
            _uiState.value = SessionsUiState.Loaded(response.sessions, response.total, response.page)
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }

    suspend fun loadSession(id: String) {
        _uiState.value = SessionsUiState.Loading
        try {
            _selectedSession.value = sessionsApi.get(id)
        } catch (e: Exception) {
            _uiState.value = SessionsUiState.Error(e.toAppError())
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest --tests "ru.skatelab.shared.state.SessionsViewModelTest" 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt
git commit -m "refactor(shared): SessionsViewModel.Error carries AppError instead of String"
```

---

### Task 4: Refactor AuthViewModel to use AppError

**Files:**

- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt`

- [ ] **Step 1: Refactor AuthViewModel**

Change `AuthUiState.Error(val message: String)` to `AuthUiState.Error(val error: AppError)`. Replace all `it.message ?: "..."` with `it.toAppError()`.

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt
package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.utils.toAppError

sealed interface AuthUiState {
    data object Loading : AuthUiState
    data object LoggedOut : AuthUiState
    data class LoggedIn(val userId: String, val displayName: String?) : AuthUiState
    data class Error(val error: AppError) : AuthUiState
}

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
            .onFailure { _uiState.value = AuthUiState.Error(it.toAppError()) }
    }

    suspend fun register(email: String, password: String, displayName: String) {
        _uiState.value = AuthUiState.Loading
        authRepo.register(email, password, displayName)
            .onSuccess {
                val user = runCatching { usersApi.getMe() }.getOrNull()
                _uiState.value = AuthUiState.LoggedIn(user?.id ?: "new", user?.displayName ?: displayName)
            }
            .onFailure { _uiState.value = AuthUiState.Error(it.toAppError()) }
    }

    suspend fun logout() {
        authRepo.logout()
        _uiState.value = AuthUiState.LoggedOut
    }
}
```

- [ ] **Step 2: Run shared tests to verify nothing is broken**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt
git commit -m "refactor(shared): AuthViewModel.Error carries AppError instead of String"
```

---

### Task 5: Refactor ProcessingViewModel to use AppError

**Files:**

- Modify: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt`

- [ ] **Step 1: Refactor ProcessingViewModel**

Change `ProcessingUiState.Failed(val message: String)` to `ProcessingUiState.Failed(val error: AppError)`. Replace all raw `e.message ?: "..."` with `e.toAppError()`. Keep `Progress(val percent: Float, val message: String)` — that `message` is a server progress message, not a user-facing error.

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt
package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.ProcessStatus
import ru.skatelab.shared.utils.toAppError

sealed interface ProcessingUiState {
    data object Idle : ProcessingUiState
    data class Progress(val percent: Float, val message: String) : ProcessingUiState
    data class Completed(val sessionId: String) : ProcessingUiState
    data class Failed(val error: AppError) : ProcessingUiState
}

class ProcessingViewModel(private val processApi: IProcessApi) {
    private val _uiState = MutableStateFlow<ProcessingUiState>(ProcessingUiState.Idle)
    val uiState: StateFlow<ProcessingUiState> = _uiState.asStateFlow()

    suspend fun startProcessing(videoKey: String, sessionId: String? = null) {
        _uiState.value = ProcessingUiState.Progress(0f, "Queuing...")
        try {
            val response = processApi.queue(videoKey, sessionId)
            observeProgress(response.taskId)
        } catch (e: Exception) {
            _uiState.value = ProcessingUiState.Failed(e.toAppError())
        }
    }

    private suspend fun observeProgress(taskId: String) {
        processApi.stream(taskId).collect { event ->
            when (event.parsedStatus) {
                ProcessStatus.RUNNING ->
                    _uiState.value = ProcessingUiState.Progress(event.progress, event.message)
                ProcessStatus.COMPLETED ->
                    _uiState.value = ProcessingUiState.Completed(event.sessionId ?: taskId)
                ProcessStatus.FAILED ->
                    _uiState.value = ProcessingUiState.Failed(AppError.Server())
                else -> {}
            }
        }
    }

    suspend fun cancelProcessing(taskId: String) {
        runCatching { processApi.cancel(taskId) }
            .onFailure { _uiState.value = ProcessingUiState.Failed(it.toAppError()) }
    }
}
```

Note: `ProcessStatus.FAILED` now maps to `AppError.Server()` — the server reported failure, not a client exception. Raw `event.message` is no longer leaked to the user.

- [ ] **Step 2: Run shared tests to verify nothing is broken**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt
git commit -m "refactor(shared): ProcessingUiState.Failed carries AppError instead of String"
```

---

### Task 6: Create AppError.asString() Android extension

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/utils/AppErrorExt.kt`

- [ ] **Step 1: Create the extension function**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/utils/AppErrorExt.kt
package ru.skatelab.capture.utils

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import ru.skatelab.capture.R
import ru.skatelab.shared.models.AppError

@Composable
fun AppError.asString(): String = stringResource(
    when (this) {
        is AppError.Network -> R.string.error_network
        is AppError.Auth -> R.string.error_auth
        is AppError.NotFound -> R.string.error_not_found
        is AppError.Server -> R.string.error_server
        is AppError.Timeout -> R.string.error_timeout
        is AppError.Unknown -> R.string.error_unknown
    }
)
```

- [ ] **Step 2: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS (error string keys don't exist yet in strings.xml — they'll be added in Phase 2)

Note: This will fail until string keys are added in Task 7. This is expected — the extension function and string resources are created in the same Phase 1 gate. Run compile after Task 7 completes.

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/utils/AppErrorExt.kt
git commit -m "feat(android): add AppError.asString() Composable extension"
```

---

### Task 7: Add error string keys to strings.xml

**Files:**

- Modify: `mobile/androidApp/src/main/res/values/strings.xml`

- [ ] **Step 1: Add error string keys to English strings.xml**

Add these keys after the existing `<!-- Results -->` section in `mobile/androidApp/src/main/res/values/strings.xml`:

```xml
    <!-- Error messages (AppError) -->
    <string name="error_network">Network error. Check your connection.</string>
    <string name="error_auth">Authentication error. Please log in again.</string>
    <string name="error_not_found">Not found.</string>
    <string name="error_server">Server error. Please try again later.</string>
    <string name="error_timeout">Request timed out. Please try again.</string>
    <string name="error_unknown">An unexpected error occurred.</string>
```

- [ ] **Step 2: Compile check (verify AppErrorExt.kt resolves)**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/res/values/strings.xml
git commit -m "feat(android): add AppError string keys (English default)"
```

---

### Task 8: Guard fallbackToDestructiveMigration with BuildConfig.DEBUG

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt`
- Modify: `mobile/androidApp/build.gradle.kts`

- [ ] **Step 1: Enable BuildConfig in build.gradle.kts**

Add `buildConfig = true` to the `buildFeatures` block in `mobile/androidApp/build.gradle.kts`:

```kotlin
    buildFeatures {
        compose = true
        buildConfig = true
    }
```

- [ ] **Step 2: Refactor DatabaseModule.kt**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt
package ru.skatelab.capture.di

import android.content.Context
import androidx.room.Room
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton
import ru.skatelab.capture.BuildConfig
import ru.skatelab.capture.data.db.AppDatabase
import ru.skatelab.capture.data.db.CachedSessionDao
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.upload.ChunkedUploader

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(
        @ApplicationContext context: Context,
    ): AppDatabase {
        val builder = Room.databaseBuilder(context, AppDatabase::class.java, "skatelab.db")
        if (BuildConfig.DEBUG) {
            builder.fallbackToDestructiveMigration(true)
        }
        return builder.build()
    }

    @Provides
    fun providePendingUploadDao(db: AppDatabase): PendingUploadDao = db.pendingUploadDao()

    @Provides
    fun provideCachedSessionDao(db: AppDatabase): CachedSessionDao = db.cachedSessionDao()

    @Provides
    @Singleton
    fun provideChunkedUploader(skateLabClient: ru.skatelab.shared.api.SkateLabClient): ChunkedUploader =
        ChunkedUploader(skateLabClient.uploads, skateLabClient.httpClient)
}
```

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt mobile/androidApp/build.gradle.kts
git commit -m "fix(android): guard fallbackToDestructiveMigration with BuildConfig.DEBUG"
```

---

### Task 9: Create BleScanStatus enum

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/domain/model/BleScanStatus.kt`

- [ ] **Step 1: Create the enum**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/domain/model/BleScanStatus.kt
package ru.skatelab.capture.domain.model

enum class BleScanStatus {
    IDLE,
    RESETTING_LEFT,
    RESETTING_RIGHT,
    RESET_OK_LEFT,
    RESET_OK_RIGHT,
    RESET_FAILED,
    CALIBRATING_LEFT,
    CALIBRATING_RIGHT,
    CALIBRATION_OK_LEFT,
    CALIBRATION_OK_RIGHT,
    CALIBRATION_FAILED,
}
```

- [ ] **Step 2: Add BLE status string keys to strings.xml**

Add to `mobile/androidApp/src/main/res/values/strings.xml` in the `<!-- BLE Scan -->` section:

```xml
    <string name="ble_status_idle">Ready</string>
    <string name="ble_status_resetting_left">Resetting left sensor…</string>
    <string name="ble_status_resetting_right">Resetting right sensor…</string>
    <string name="ble_status_reset_ok_left">Left sensor reset OK</string>
    <string name="ble_status_reset_ok_right">Right sensor reset OK</string>
    <string name="ble_status_reset_failed">Reset failed</string>
    <string name="ble_status_calibrating_left">Calibrating left sensor… Place horizontally!</string>
    <string name="ble_status_calibrating_right">Calibrating right sensor… Place horizontally!</string>
    <string name="ble_status_calibration_ok_left">Left sensor calibrated OK</string>
    <string name="ble_status_calibration_ok_right">Right sensor calibrated OK</string>
    <string name="ble_status_calibration_failed">Calibration failed</string>
    <string name="ble_connected">Connected</string>
    <string name="ble_rssi">RSSI: %1$d</string>
    <string name="ble_reset_left">Reset left</string>
    <string name="ble_reset_right">Reset right</string>
    <string name="ble_acc_left">ACC left</string>
    <string name="ble_acc_right">ACC right</string>
```

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/domain/model/BleScanStatus.kt mobile/androidApp/src/main/res/values/strings.xml
git commit -m "feat(android): add BleScanStatus enum and BLE string resources"
```

---

### Task 10: Refactor BleScanViewModel to use BleScanStatus

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt`

- [ ] **Step 1: Refactor the ViewModel**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt
package ru.skatelab.capture.presentation.ble

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.BleScanStatus
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.usecase.AccCalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase
import ru.skatelab.capture.domain.usecase.FactoryResetSensorUseCase

@HiltViewModel
class BleScanViewModel
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val connectSensorUseCase: ConnectSensorUseCase,
        private val factoryResetSensorUseCase: FactoryResetSensorUseCase,
        private val accCalibrateSensorUseCase: AccCalibrateSensorUseCase,
        private val appLogger: Logger,
    ) : ViewModel() {
        private val tag = "BleScanVM"

        val scanResults: StateFlow<List<ScanDevice>> =
            bleRepository.scanResults
                .combine(bleRepository.connectionState) { scanned, stateMap ->
                    val connected = bleRepository.getConnectedDevices()
                    val scanByAddr = scanned.associateBy { it.address }
                    val mergedByAddr = scanByAddr + connected.associateBy { it.address }
                    mergedByAddr.values.toList()
                }
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

        val connectionState =
            bleRepository.connectionState
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyMap())

        private val _scanStatus = MutableStateFlow<BleScanStatus?>(null)
        val scanStatus: StateFlow<BleScanStatus?> = _scanStatus.asStateFlow()

        private val _isScanning = MutableStateFlow(false)
        val isScanning: StateFlow<Boolean> = _isScanning.asStateFlow()

        fun startScan() {
            if (_isScanning.value) return
            _isScanning.value = true
            appLogger.i(tag, "startScan() called")
            bleRepository.startScan()
        }

        fun stopScan() {
            _isScanning.value = false
            bleRepository.stopScan()
        }

        fun connectSensor(
            sensorId: SensorId,
            address: String,
        ) {
            viewModelScope.launch {
                appLogger.i(tag, "connectSensor: $sensorId -> $address")
                val result = connectSensorUseCase(sensorId, address)
                if (result.isFailure) {
                    appLogger.e(tag, "connectSensor failed: ${result.exceptionOrNull()?.message}")
                } else {
                    appLogger.i(tag, "connectSensor success: $sensorId")
                }
            }
        }

        fun factoryResetSensor(sensorId: SensorId) {
            viewModelScope.launch {
                _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.RESETTING_LEFT else BleScanStatus.RESETTING_RIGHT
                appLogger.i(tag, "factoryResetSensor: $sensorId")
                val result = factoryResetSensorUseCase(sensorId)
                if (result.isSuccess) {
                    _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.RESET_OK_LEFT else BleScanStatus.RESET_OK_RIGHT
                    appLogger.i(tag, "factoryReset success: $sensorId")
                } else {
                    _scanStatus.value = BleScanStatus.RESET_FAILED
                    appLogger.e(tag, "factoryReset failed: ${result.exceptionOrNull()?.message}")
                }
            }
        }

        fun accCalibrateSensor(sensorId: SensorId) {
            viewModelScope.launch {
                _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.CALIBRATING_LEFT else BleScanStatus.CALIBRATING_RIGHT
                appLogger.i(tag, "accCalibrateSensor: $sensorId")
                val result = accCalibrateSensorUseCase(sensorId)
                if (result.isSuccess) {
                    _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.CALIBRATION_OK_LEFT else BleScanStatus.CALIBRATION_OK_RIGHT
                    appLogger.i(tag, "accCalibrate success: $sensorId")
                } else {
                    _scanStatus.value = BleScanStatus.CALIBRATION_FAILED
                    appLogger.e(tag, "accCalibrate failed: ${result.exceptionOrNull()?.message}")
                }
            }
        }

        fun getAddressForSensor(sensorId: SensorId): String? = bleRepository.getAddressForSensor(sensorId)

        override fun onCleared() {
            super.onCleared()
            if (_isScanning.value) bleRepository.stopScan()
        }
    }
```

- [ ] **Step 2: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt
git commit -m "refactor(android): BleScanViewModel uses BleScanStatus enum instead of String"
```

---

### Phase 1 Gate: Verify

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/shared commonTest 2>&1 | tail -5`
Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`

Both must PASS before proceeding to Phase 2.

---

## Phase 2 — Parallel Streams

Three streams run in parallel. Within each stream, tasks can also be parallelized by agent.

**Stream A: i18n** (Tasks 11-18) — string resource extraction
**Stream B: Accessibility** (Tasks 19-25) — semantics, contentDescription, touch targets
**Stream C: Security** (Tasks 26-30) — ProGuard, network config, API key audit

---

### Stream A: i18n — String Resource Extraction

**Prerequisite:** Complete i18n string inventory first (Task 11), then extract per-screen in parallel (Tasks 12-18).

---

#### Task 11: Restructure strings.xml (EN default + RU locale)

**Files:**

- Modify: `mobile/androidApp/src/main/res/values/strings.xml`
- Create: `mobile/androidApp/src/main/res/values-ru/strings.xml`

- [ ] **Step 1: Convert values/strings.xml to English defaults**

Replace all Russian values in `mobile/androidApp/src/main/res/values/strings.xml` with English equivalents. The file must contain ALL keys (existing + new from Phase 1). Here is the complete English default file:

```xml
<resources>
    <string name="app_name">SkateLab Capture</string>

    <!-- Recording notification -->
    <string name="recording_notification_channel">Sensor recording</string>
    <string name="recording_notification_title">Recording in progress</string>

    <!-- BLE Scan -->
    <string name="ble_scan_title">Find sensors</string>
    <string name="ble_scan_button">Scan</string>
    <string name="ble_scan_stop">Stop</string>
    <string name="ble_proceed_calibration">Next: Calibration</string>
    <string name="ble_left">Left</string>
    <string name="ble_right">Right</string>
    <string name="ble_status_idle">Ready</string>
    <string name="ble_status_resetting_left">Resetting left sensor…</string>
    <string name="ble_status_resetting_right">Resetting right sensor…</string>
    <string name="ble_status_reset_ok_left">Left sensor reset OK</string>
    <string name="ble_status_reset_ok_right">Right sensor reset OK</string>
    <string name="ble_status_reset_failed">Reset failed</string>
    <string name="ble_status_calibrating_left">Calibrating left sensor… Place horizontally!</string>
    <string name="ble_status_calibrating_right">Calibrating right sensor… Place horizontally!</string>
    <string name="ble_status_calibration_ok_left">Left sensor calibrated OK</string>
    <string name="ble_status_calibration_ok_right">Right sensor calibrated OK</string>
    <string name="ble_status_calibration_failed">Calibration failed</string>
    <string name="ble_connected">Connected</string>
    <string name="ble_rssi">RSSI: %1$d</string>
    <string name="ble_reset_left">Reset left</string>
    <string name="ble_reset_right">Reset right</string>
    <string name="ble_acc_left">ACC left</string>
    <string name="ble_acc_right">ACC right</string>

    <!-- Calibration -->
    <string name="calibration_title">Calibrate sensors</string>
    <string name="calibration_instruction">Place sensors on a flat surface and do not move them.</string>
    <string name="calibration_left">Left sensor</string>
    <string name="calibration_right">Right sensor</string>
    <string name="calibration_calibrate">Calibrate</string>
    <string name="calibration_calibrate_both">Calibration</string>
    <string name="calibration_done">Calibrated</string>
    <string name="calibration_proceed">Next: Camera</string>
    <string name="calibration_skip">Skip</string>
    <string name="calibration_cancel">Cancel</string>

    <!-- Recording -->
    <string name="recording_preparing">Preparing camera…</string>
    <string name="recording_camera_ready">Camera ready</string>
    <string name="recording_active">Recording…</string>
    <string name="recording_start">Start recording</string>
    <string name="recording_stop">Stop recording</string>

    <!-- Export -->
    <string name="export_title">Export session</string>
    <string name="export_session">Session: %s</string>
    <string name="exporting">Exporting…</string>
    <string name="export_done">Export complete!</string>
    <string name="export_share">Share</string>
    <string name="export_share_title">Send session</string>

    <!-- Permissions -->
    <string name="permissions_required">Permissions are required for the app to work</string>

    <!-- Session List -->
    <string name="session_list_title">Sessions</string>
    <string name="session_date_format">dd.MM.yyyy HH:mm</string>
    <string name="session_duration">Duration: %d sec</string>
    <string name="session_complete">Completed</string>
    <string name="session_incomplete">Incomplete</string>
    <string name="session_no_sessions">No saved sessions</string>
    <string name="session_detail_title">Session</string>
    <string name="tab_video">Video</string>
    <string name="tab_charts">Charts</string>
    <string name="tab_details">Info</string>
    <string name="imu_loading">Loading data…</string>
    <string name="imu_no_data">No IMU data</string>
    <string name="label_acc_mag">|a| m/s²</string>
    <string name="label_ang_vel">|ω| °/s</string>
    <string name="label_rotation">Cumulative rotation</string>
    <string name="unit_mps2">m/s²</string>
    <string name="unit_dps">°/s</string>
    <string name="unit_rad">rad</string>
    <string name="charts_summary_title">Sensor data</string>
    <string name="charts_summary_hint">Scroll and zoom charts. Red line — video position.</string>
    <string name="detail_duration">Duration: %d s</string>
    <string name="detail_fps">FPS: %d</string>
    <string name="detail_resolution">Resolution: %dx%d</string>
    <string name="detail_status_complete">Completed</string>
    <string name="detail_status_incomplete">Incomplete</string>
    <string name="detail_video_size">Video: %s</string>
    <string name="detail_imu_left">Left sensor: %s</string>
    <string name="detail_imu_right">Right sensor: %s</string>
    <string name="detail_timestamp_source">Timestamps: %s</string>
    <string name="detail_fps_verified">FPS verified: %s</string>
    <string name="detail_file_absent">absent</string>
    <string name="detail_file_present">%s (%.1f KB)</string>
    <string name="detail_yes">yes</string>
    <string name="detail_no">no</string>
    <string name="session_export">Export</string>
    <string name="session_delete">Delete</string>
    <string name="session_delete_title">Delete session?</string>
    <string name="session_delete_confirm">Session and all files will be deleted.</string>
    <string name="session_delete_confirm_button">Delete</string>
    <string name="session_delete_cancel">Cancel</string>
    <string name="session_new_recording">New recording</string>

    <!-- Results (server sessions) -->
    <string name="results_title">Results</string>
    <string name="results_empty">No analysis results</string>
    <string name="results_loading">Loading…</string>
    <string name="results_error_prefix">Error: </string>
    <string name="results_pull_refresh">Pull down to refresh</string>
    <string name="result_detail_title">Result</string>
    <string name="metric_pr">PR</string>
    <string name="metric_reference">Reference:</string>
    <string name="metric_section_title">Metrics</string>
    <string name="recommendations_title">Recommendations</string>
    <string name="status_completed">Done</string>
    <string name="status_processing">Processing…</string>
    <string name="status_failed">Error</string>
    <string name="status_queued">Queued</string>
    <string name="score_label">score</string>
    <string name="ang_vel_avg">Average</string>
    <string name="ang_vel_max">Maximum</string>
    <string name="ang_vel_title">Angular velocity</string>

    <!-- Error messages (AppError) -->
    <string name="error_network">Network error. Check your connection.</string>
    <string name="error_auth">Authentication error. Please log in again.</string>
    <string name="error_not_found">Not found.</string>
    <string name="error_server">Server error. Please try again later.</string>
    <string name="error_timeout">Request timed out. Please try again.</string>
    <string name="error_unknown">An unexpected error occurred.</string>

    <!-- Auth -->
    <string name="auth_login_title">Log in to your account</string>
    <string name="auth_register_title">Create Account</string>
    <string name="auth_register_subtitle">Sign up to get started</string>
    <string name="auth_email">Email</string>
    <string name="auth_password">Password</string>
    <string name="auth_display_name">Display name</string>
    <string name="auth_login_button">Log in</string>
    <string name="auth_register_button">Register</string>
    <string name="auth_no_account">Don\'t have an account? Register</string>
    <string name="auth_has_account">Already have an account? Log in</string>
    <string name="auth_no_network">No internet connection. Check your network and try again.</string>
    <string name="auth_retry">Retry</string>

    <!-- Processing -->
    <string name="processing_preparing">Preparing…</string>
    <string name="processing_done">Done!</string>
    <string name="processing_no_connection">No connection</string>
    <string name="processing_check_network">Check your internet connection and try again.</string>
    <string name="processing_retry">Retry</string>
    <string name="processing_go_back">Go back</string>

    <!-- Session detail (presentation layer) -->
    <string name="session_detail_left_sensor">Left</string>
    <string name="session_detail_right_sensor">Right</string>
    <string name="session_detail_left_summary">L: peak %1$s, avg %2$s</string>
    <string name="session_detail_right_summary">R: peak %1$s, avg %2$s</string>
    <string name="session_detail_files">Files</string>
    <string name="session_detail_result_fallback">Result</string>

    <!-- Session list (presentation layer) -->
    <string name="session_list_results">Results</string>
    <string name="session_list_nav_back">Back</string>
    <string name="session_list_loading">Loading…</string>
    <string name="session_list_error">Error loading</string>
    <string name="session_list_retry">Retry</string>
    <string name="session_list_empty">No analysis results</string>

    <!-- Session detail (UI layer) -->
    <string name="session_ui_nav_back">Back</string>
    <string name="session_ui_error_loading">Error loading</string>
    <string name="session_ui_retry">Retry</string>
    <string name="session_ui_hide_skeleton">Hide skeleton</string>
    <string name="session_ui_show_skeleton">Show skeleton</string>
    <string name="session_ui_score_label">score</string>
    <string name="session_ui_metrics_title">Metrics</string>
    <string name="session_ui_recommendations_title">Recommendations</string>

    <!-- Metric names -->
    <string name="metric_jump_height">Jump height</string>
    <string name="metric_airtime">Air time</string>
    <string name="metric_angular_velocity">Angular velocity</string>
    <string name="metric_knee_angle_min">Min knee angle</string>
    <string name="metric_landing_quality">Landing quality</string>
    <string name="metric_rotation_count">Rotation count</string>
    <string name="metric_torso_lean">Torso lean</string>
    <string name="metric_approach_arc">Approach arc</string>
    <string name="metric_pre_rotation">Pre-rotation</string>
    <string name="metric_total_rotation">Total rotation</string>
    <string name="metric_speed_at_takeoff">Speed at takeoff</string>

    <!-- Figure skating elements -->
    <string name="element_axel">Axel</string>
    <string name="element_lutz">Lutz</string>
    <string name="element_flip">Flip</string>
    <string name="element_loop">Loop</string>
    <string name="element_salchow">Salchow</string>
    <string name="element_toe_loop">Toe loop</string>
    <string name="element_toe_loop_flip">Toe loop (flip)</string>
    <string name="element_cascade">Cascade</string>

    <!-- Recording -->
    <string name="recording_left_battery">L: %1$d%%</string>
    <string name="recording_right_battery">R: %1$d%%</string>
    <string name="recording_reconnecting">Reconnecting: %1$s</string>

    <!-- Profile -->
    <string name="profile_save">Save profile</string>
    <string name="profile_saved">Saved</string>
    <string name="profile_log_out">Log out</string>

    <!-- More -->
    <string name="more_title">More</string>
    <string name="more_sensors">Sensors</string>
    <string name="more_ble_scan">BLE Scan</string>
    <string name="more_about">About</string>
    <string name="more_app_version">App version</string>
    <string name="more_log_out">Log out</string>

    <!-- Camera -->
    <string name="camera_preparing">Preparing camera…</string>
    <string name="camera_reconnecting">Reconnecting: %1$s</string>

    <!-- Calibration countdown -->
    <string name="calibration_countdown">%1$d s</string>

    <!-- Navigation -->
    <string name="nav_back">Back</string>

    <!-- Content descriptions (accessibility) -->
    <string name="cd_ble_sensor">Connect BLE sensor</string>
    <string name="cd_app_info">App version info</string>
    <string name="cd_logout">Log out</string>
    <string name="cd_save_profile">Save profile</string>
    <string name="cd_export_session">Export session</string>
    <string name="cd_skeleton_overlay">Skeleton overlay visualization</string>
    <string name="cd_imu_chart">IMU chart: angular velocity. Left peak %1$s, right peak %2$s</string>
    <string name="cd_loading">Loading</string>
    <string name="cd_error_icon">Error</string>
</resources>
```

- [ ] **Step 2: Create values-ru/strings.xml with Russian translations**

```xml
<!-- mobile/androidApp/src/main/res/values-ru/strings.xml -->
<resources>
    <string name="app_name">SkateLab Capture</string>

    <string name="recording_notification_channel">Запись датчиков</string>
    <string name="recording_notification_title">Идёт запись</string>

    <string name="ble_scan_title">Поиск датчиков</string>
    <string name="ble_scan_button">Сканировать</string>
    <string name="ble_scan_stop">Стоп</string>
    <string name="ble_proceed_calibration">Далее: Калибровка</string>
    <string name="ble_left">Левый</string>
    <string name="ble_right">Правый</string>
    <string name="ble_status_idle">Готов</string>
    <string name="ble_status_resetting_left">Сброс левого датчика…</string>
    <string name="ble_status_resetting_right">Сброс правого датчика…</string>
    <string name="ble_status_reset_ok_left">Сброс левого OK</string>
    <string name="ble_status_reset_ok_right">Сброс правого OK</string>
    <string name="ble_status_reset_failed">Ошибка сброса</string>
    <string name="ble_status_calibrating_left">Калибровка ACC левого… Датчик горизонтально!</string>
    <string name="ble_status_calibrating_right">Калибровка ACC правого… Датчик горизонтально!</string>
    <string name="ble_status_calibration_ok_left">ACC калибровка левого OK</string>
    <string name="ble_status_calibration_ok_right">ACC калибровка правого OK</string>
    <string name="ble_status_calibration_failed">Ошибка калибровки</string>
    <string name="ble_connected">Подключен</string>
    <string name="ble_rssi">RSSI: %1$d</string>
    <string name="ble_reset_left">Сброс лев.</string>
    <string name="ble_reset_right">Сброс прав.</string>
    <string name="ble_acc_left">ACC лев.</string>
    <string name="ble_acc_right">ACC прав.</string>

    <string name="calibration_title">Калибровка датчиков</string>
    <string name="calibration_instruction">Положите датчики на ровную поверхность и не двигайте.</string>
    <string name="calibration_left">Левый датчик</string>
    <string name="calibration_right">Правый датчик</string>
    <string name="calibration_calibrate">Калибровать</string>
    <string name="calibration_calibrate_both">Калибровка</string>
    <string name="calibration_done">Откалиброван</string>
    <string name="calibration_proceed">Далее: Камера</string>
    <string name="calibration_skip">Пропустить</string>
    <string name="calibration_cancel">Отменить</string>

    <string name="recording_preparing">Подготовка камеры…</string>
    <string name="recording_camera_ready">Камера готова</string>
    <string name="recording_active">Запись…</string>
    <string name="recording_start">Начать запись</string>
    <string name="recording_stop">Остановить запись</string>

    <string name="export_title">Экспорт сессии</string>
    <string name="export_session">Сессия: %s</string>
    <string name="exporting">Экспорт…</string>
    <string name="export_done">Экспорт завершён!</string>
    <string name="export_share">Поделиться</string>
    <string name="export_share_title">Отправить сессию</string>

    <string name="permissions_required">Разрешения необходимы для работы</string>

    <string name="session_list_title">Сессии</string>
    <string name="session_date_format">dd.MM.yyyy HH:mm</string>
    <string name="session_duration">Длительность: %d сек</string>
    <string name="session_complete">Завершена</string>
    <string name="session_incomplete">Незавершена</string>
    <string name="session_no_sessions">Нет сохранённых сессий</string>
    <string name="session_detail_title">Сессия</string>
    <string name="tab_video">Видео</string>
    <string name="tab_charts">Графики</string>
    <string name="tab_details">Информация</string>
    <string name="imu_loading">Загрузка данных…</string>
    <string name="imu_no_data">Нет данных IMU</string>
    <string name="label_acc_mag">|a| м/с²</string>
    <string name="label_ang_vel">|ω| °/с</string>
    <string name="label_rotation">Накопленный поворот</string>
    <string name="unit_mps2">м/с²</string>
    <string name="unit_dps">°/с</string>
    <string name="unit_rad">рад</string>
    <string name="charts_summary_title">Данные датчиков</string>
    <string name="charts_summary_hint">Листайте и масштабируйте графики. Красная линия — позиция видео.</string>
    <string name="detail_duration">Длительность: %d с</string>
    <string name="detail_fps">FPS: %d</string>
    <string name="detail_resolution">Разрешение: %dx%d</string>
    <string name="detail_status_complete">Завершена</string>
    <string name="detail_status_incomplete">Незавершена</string>
    <string name="detail_video_size">Видео: %s</string>
    <string name="detail_imu_left">Левый датчик: %s</string>
    <string name="detail_imu_right">Правый датчик: %s</string>
    <string name="detail_timestamp_source">Таймстемпы: %s</string>
    <string name="detail_fps_verified">FPS верифицирован: %s</string>
    <string name="detail_file_absent">отсутствует</string>
    <string name="detail_file_present">%s (%.1f КБ)</string>
    <string name="detail_yes">да</string>
    <string name="detail_no">нет</string>
    <string name="session_export">Экспорт</string>
    <string name="session_delete">Удалить</string>
    <string name="session_delete_title">Удалить сессию?</string>
    <string name="session_delete_confirm">Сессия и все файлы будут удалены.</string>
    <string name="session_delete_confirm_button">Удалить</string>
    <string name="session_delete_cancel">Отмена</string>
    <string name="session_new_recording">Новая запись</string>

    <string name="results_title">Результаты</string>
    <string name="results_empty">Нет результатов анализа</string>
    <string name="results_loading">Загрузка…</string>
    <string name="results_error_prefix">Ошибка: </string>
    <string name="results_pull_refresh">Потяните вниз, чтобы обновить</string>
    <string name="result_detail_title">Результат</string>
    <string name="metric_pr">PR</string>
    <string name="metric_reference">Референс:</string>
    <string name="metric_section_title">Метрики</string>
    <string name="recommendations_title">Рекомендации</string>
    <string name="status_completed">Готово</string>
    <string name="status_processing">Обработка…</string>
    <string name="status_failed">Ошибка</string>
    <string name="status_queued">В очереди</string>
    <string name="score_label">оценка</string>
    <string name="ang_vel_avg">Средняя</string>
    <string name="ang_vel_max">Максимальная</string>
    <string name="ang_vel_title">Угловая скорость</string>

    <string name="error_network">Ошибка сети. Проверьте подключение.</string>
    <string name="error_auth">Ошибка авторизации. Войдите заново.</string>
    <string name="error_not_found">Не найдено.</string>
    <string name="error_server">Ошибка сервера. Попробуйте позже.</string>
    <string name="error_timeout">Время запроса истекло. Попробуйте снова.</string>
    <string name="error_unknown">Произошла непредвиденная ошибка.</string>

    <string name="auth_login_title">Войдите в аккаунт</string>
    <string name="auth_register_title">Создать аккаунт</string>
    <string name="auth_register_subtitle">Зарегистрируйтесь, чтобы начать</string>
    <string name="auth_email">Email</string>
    <string name="auth_password">Пароль</string>
    <string name="auth_display_name">Имя</string>
    <string name="auth_login_button">Войти</string>
    <string name="auth_register_button">Зарегистрироваться</string>
    <string name="auth_no_account">Нет аккаунта? Зарегистрируйтесь</string>
    <string name="auth_has_account">Уже есть аккаунт? Войдите</string>
    <string name="auth_no_network">Нет подключения к интернету. Проверьте сеть и повторите.</string>
    <string name="auth_retry">Повторить</string>

    <string name="processing_preparing">Подготовка…</string>
    <string name="processing_done">Готово!</string>
    <string name="processing_no_connection">Нет подключения</string>
    <string name="processing_check_network">Проверьте подключение к интернету и повторите.</string>
    <string name="processing_retry">Повторить</string>
    <string name="processing_go_back">Назад</string>

    <string name="session_detail_left_sensor">Левый</string>
    <string name="session_detail_right_sensor">Правый</string>
    <string name="session_detail_left_summary">Л: пик %1$s, средн %2$s</string>
    <string name="session_detail_right_summary">П: пик %1$s, средн %2$s</string>
    <string name="session_detail_files">Файлы</string>
    <string name="session_detail_result_fallback">Результат</string>

    <string name="session_list_results">Результаты</string>
    <string name="session_list_nav_back">Назад</string>
    <string name="session_list_loading">Загрузка…</string>
    <string name="session_list_error">Ошибка загрузки</string>
    <string name="session_list_retry">Повторить</string>
    <string name="session_list_empty">Нет результатов анализа</string>

    <string name="session_ui_nav_back">Назад</string>
    <string name="session_ui_error_loading">Ошибка загрузки</string>
    <string name="session_ui_retry">Повторить</string>
    <string name="session_ui_hide_skeleton">Скрыть скелет</string>
    <string name="session_ui_show_skeleton">Показать скелет</string>
    <string name="session_ui_score_label">оценка</string>
    <string name="session_ui_metrics_title">Метрики</string>
    <string name="session_ui_recommendations_title">Рекомендации</string>

    <string name="metric_jump_height">Высота прыжка</string>
    <string name="metric_airtime">Время в воздухе</string>
    <string name="metric_angular_velocity">Угловая скорость</string>
    <string name="metric_knee_angle_min">Мин. угол колена</string>
    <string name="metric_landing_quality">Качество приземления</string>
    <string name="metric_rotation_count">Количество вращений</string>
    <string name="metric_torso_lean">Наклон корпуса</string>
    <string name="metric_approach_arc">Дуга разбега</string>
    <string name="metric_pre_rotation">Предварит. вращение</string>
    <string name="metric_total_rotation">Общее вращение</string>
    <string name="metric_speed_at_takeoff">Скорость на отрыве</string>

    <string name="element_axel">Аксель</string>
    <string name="element_lutz">Лутц</string>
    <string name="element_flip">Флип</string>
    <string name="element_loop">Риттбергер</string>
    <string name="element_salchow">Сальхов</string>
    <string name="element_toe_loop">Тулуп</string>
    <string name="element_toe_loop_flip">Тулуп (флип)</string>
    <string name="element_cascade">Каскад</string>

    <string name="recording_left_battery">Л: %1$d%%</string>
    <string name="recording_right_battery">П: %1$d%%</string>
    <string name="recording_reconnecting">Переподключение: %1$s</string>

    <string name="profile_save">Сохранить профиль</string>
    <string name="profile_saved">Сохранено</string>
    <string name="profile_log_out">Выйти</string>

    <string name="more_title">Ещё</string>
    <string name="more_sensors">Датчики</string>
    <string name="more_ble_scan">BLE Сканирование</string>
    <string name="more_about">О приложении</string>
    <string name="more_app_version">Версия приложения</string>
    <string name="more_log_out">Выйти</string>

    <string name="camera_preparing">Подготовка камеры…</string>
    <string name="camera_reconnecting">Переподключение: %1$s</string>

    <string name="calibration_countdown">%1$d с</string>

    <string name="nav_back">Назад</string>

    <string name="cd_ble_sensor">Подключить BLE датчик</string>
    <string name="cd_app_info">Информация о версии</string>
    <string name="cd_logout">Выйти</string>
    <string name="cd_save_profile">Сохранить профиль</string>
    <string name="cd_export_session">Экспорт сессии</string>
    <string name="cd_skeleton_overlay">Визуализация скелета</string>
    <string name="cd_imu_chart">График IMU: угловая скорость. Левый пик %1$s, правый пик %2$s</string>
    <string name="cd_loading">Загрузка</string>
    <string name="cd_error_icon">Ошибка</string>
</resources>
```

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS (string resource changes don't affect compilation — Kotlin code references R.string keys)

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/res/values/strings.xml mobile/androidApp/src/main/res/values-ru/strings.xml
git commit -m "feat(android): restructure strings.xml — EN default + values-ru/ locale"
```

---

#### Task 12: Extract BleScanScreen hardcoded strings

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt`

- [ ] **Step 1: Replace hardcoded strings with stringResource calls**

In `BleScanScreen.kt`, replace:
- Line 121: `"Подключен"` → `stringResource(R.string.ble_connected)`
- Line 123: `"RSSI: ${device.rssi}"` → `stringResource(R.string.ble_rssi, device.rssi)`
- Line 138: `"Сброс лев."` → `stringResource(R.string.ble_reset_left)`
- Line 141: `"ACC лев."` → `stringResource(R.string.ble_acc_left)`
- Line 146: `"Сброс прав."` → `stringResource(R.string.ble_reset_right)`
- Line 149: `"ACC прав."` → `stringResource(R.string.ble_acc_right)`

Also update the status display (lines 85-88) to map `BleScanStatus` to `stringResource`:

```kotlin
// Replace the factoryResetStatus display section:
factoryResetStatus?.let { statusText ->
    Spacer(modifier = Modifier.height(8.dp))
    Text(statusText, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
}
```

With:

```kotlin
scanStatus?.let { status ->
    Spacer(modifier = Modifier.height(8.dp))
    Text(
        status.asString(),
        style = MaterialTheme.typography.bodySmall,
        color = if (status.isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
    )
}
```

And add the BleScanStatus.asString() Composable function (can go in BleScanStatus.kt or a separate extension file):

```kotlin
// Add to BleScanStatus.kt or create BleScanStatusExt.kt
@Composable
fun BleScanStatus.asString(): String = when (this) {
    BleScanStatus.IDLE -> stringResource(R.string.ble_status_idle)
    BleScanStatus.RESETTING_LEFT -> stringResource(R.string.ble_status_resetting_left)
    BleScanStatus.RESETTING_RIGHT -> stringResource(R.string.ble_status_resetting_right)
    BleScanStatus.RESET_OK_LEFT -> stringResource(R.string.ble_status_reset_ok_left)
    BleScanStatus.RESET_OK_RIGHT -> stringResource(R.string.ble_status_reset_ok_right)
    BleScanStatus.RESET_FAILED -> stringResource(R.string.ble_status_reset_failed)
    BleScanStatus.CALIBRATING_LEFT -> stringResource(R.string.ble_status_calibrating_left)
    BleScanStatus.CALIBRATING_RIGHT -> stringResource(R.string.ble_status_calibrating_right)
    BleScanStatus.CALIBRATION_OK_LEFT -> stringResource(R.string.ble_status_calibration_ok_left)
    BleScanStatus.CALIBRATION_OK_RIGHT -> stringResource(R.string.ble_status_calibration_ok_right)
    BleScanStatus.CALIBRATION_FAILED -> stringResource(R.string.ble_status_calibration_failed)
}

val BleScanStatus.isError: Boolean
    get() = this == BleScanStatus.RESET_FAILED || this == BleScanStatus.CALIBRATION_FAILED
```

Also update the ViewModel reference from `factoryResetStatus` to `scanStatus` in the `collectAsState` call:
```kotlin
val scanStatus by viewModel.scanStatus.collectAsState()
```

- [ ] **Step 2: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/domain/model/BleScanStatus.kt
git commit -m "refactor(android): extract BleScanScreen hardcoded strings, use BleScanStatus.asString()"
```

---

#### Task 13: Extract ProcessingScreen + Auth screens strings

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/LoginScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt`

- [ ] **Step 1: Extract ProcessingScreen strings**

Replace in ProcessingScreen.kt:
- `"Preparing..."` → `stringResource(R.string.processing_preparing)`
- `"Done!"` → `stringResource(R.string.processing_done)`
- `"Нет подключения"` → `stringResource(R.string.processing_no_connection)`
- `"Проверьте подключение к интернету и повторите."` → `stringResource(R.string.processing_check_network)`
- `"Retry"` → `stringResource(R.string.processing_retry)`
- `"Go back"` → `stringResource(R.string.processing_go_back)`

For error states that use `UiState.Error(message)`, switch to `AppError.asString()`. If the current code accesses `(state as ProcessingUiState.Failed).message`, change to `(state as ProcessingUiState.Failed).error.asString()` (import `ru.skatelab.capture.utils.asString`).

- [ ] **Step 2: Extract LoginScreen strings**

Replace in LoginScreen.kt:
- `"OOFSkate"` → keep as-is (brand name, not translated)
- `"Log in to your account"` → `stringResource(R.string.auth_login_title)`
- `"Email"` → `stringResource(R.string.auth_email)`
- `"Password"` → `stringResource(R.string.auth_password)`
- `"Нет подключения к интернету. Проверьте сеть и повторите."` → `stringResource(R.string.auth_no_network)`
- `"Повторить"` → `stringResource(R.string.auth_retry)`
- `"Log in"` → `stringResource(R.string.auth_login_button)`
- `"Don't have an account? Register"` → `stringResource(R.string.auth_no_account)`

- [ ] **Step 3: Extract RegisterScreen strings**

Replace in RegisterScreen.kt:
- `"Create Account"` → `stringResource(R.string.auth_register_title)`
- `"Sign up to get started"` → `stringResource(R.string.auth_register_subtitle)`
- `"Display name"` → `stringResource(R.string.auth_display_name)`
- `"Email"` → `stringResource(R.string.auth_email)`
- `"Password"` → `stringResource(R.string.auth_password)`
- `"Нет подключения к интернету. Проверьте сеть и повторите."` → `stringResource(R.string.auth_no_network)`
- `"Повторить"` → `stringResource(R.string.auth_retry)`
- `"Register"` → `stringResource(R.string.auth_register_button)`
- `"Already have an account? Log in"` → `stringResource(R.string.auth_has_account)`

- [ ] **Step 4: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/LoginScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt
git commit -m "refactor(android): extract ProcessingScreen + Auth screens hardcoded strings"
```

---

#### Task 14: Extract MetricCard + session UI strings

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt`

- [ ] **Step 1: Extract MetricCard strings**

Replace in MetricCard.kt (lines 25-35):
- `"Высота прыжка"` → `stringResource(R.string.metric_jump_height)`
- `"Время в воздухе"` → `stringResource(R.string.metric_airtime)`
- `"Угловая скорость"` → `stringResource(R.string.metric_angular_velocity)`
- `"Мин. угол колена"` → `stringResource(R.string.metric_knee_angle_min)`
- `"Качество приземления"` → `stringResource(R.string.metric_landing_quality)`
- `"Количество вращений"` → `stringResource(R.string.metric_rotation_count)`
- `"Наклон корпуса"` → `stringResource(R.string.metric_torso_lean)`
- `"Дуга разбега"` → `stringResource(R.string.metric_approach_arc)`
- `"Предварит. вращение"` → `stringResource(R.string.metric_pre_rotation)`
- `"Общее вращение"` → `stringResource(R.string.metric_total_rotation)`
- `"Скорость на отрыве"` → `stringResource(R.string.metric_speed_at_takeoff)`
- `"Референс:"` → `stringResource(R.string.metric_reference)`

Create a mapping function in MetricCard:

```kotlin
@Composable
fun metricDisplayName(key: String): String = when (key) {
    "jump_height" -> stringResource(R.string.metric_jump_height)
    "airtime" -> stringResource(R.string.metric_airtime)
    "angular_velocity" -> stringResource(R.string.metric_angular_velocity)
    "knee_angle_min" -> stringResource(R.string.metric_knee_angle_min)
    "landing_quality" -> stringResource(R.string.metric_landing_quality)
    "rotation_count" -> stringResource(R.string.metric_rotation_count)
    "torso_lean" -> stringResource(R.string.metric_torso_lean)
    "approach_arc" -> stringResource(R.string.metric_approach_arc)
    "pre_rotation" -> stringResource(R.string.metric_pre_rotation)
    "total_rotation" -> stringResource(R.string.metric_total_rotation)
    "speed_at_takeoff" -> stringResource(R.string.metric_speed_at_takeoff)
    else -> key
}
```

- [ ] **Step 2: Extract SessionDetailScreen (ui/session) strings**

Replace:
- `"Результат"` → `stringResource(R.string.session_detail_result_fallback)`
- `"Назад"` → `stringResource(R.string.session_ui_nav_back)`
- `"Ошибка загрузки"` → `stringResource(R.string.session_ui_error_loading)`
- `"Повторить"` → `stringResource(R.string.session_ui_retry)`
- skeleton toggle: use `R.string.session_ui_hide_skeleton` / `R.string.session_ui_show_skeleton`
- `"оценка"` → `stringResource(R.string.session_ui_score_label)`
- `"Метрики"` → `stringResource(R.string.session_ui_metrics_title)`
- `"Рекомендации"` → `stringResource(R.string.session_ui_recommendations_title)`
- Status strings: `"Готово"` → `stringResource(R.string.status_completed)`, etc.
- Element types: create `formatElementType()` function:

```kotlin
@Composable
fun formatElementType(type: String): String = when (type.lowercase()) {
    "axel" -> stringResource(R.string.element_axel)
    "lutz" -> stringResource(R.string.element_lutz)
    "flip" -> stringResource(R.string.element_flip)
    "loop" -> stringResource(R.string.element_loop)
    "salchow" -> stringResource(R.string.element_salchow)
    "toe_loop" -> stringResource(R.string.element_toe_loop)
    "toe_loop_flip" -> stringResource(R.string.element_toe_loop_flip)
    "cascade" -> stringResource(R.string.element_cascade)
    else -> type
}
```

- [ ] **Step 3: Extract SessionListScreen (ui/session) strings**

Same pattern as SessionDetailScreen. Replace:
- `"Результаты"` → `stringResource(R.string.session_list_results)`
- `"Назад"` → `stringResource(R.string.session_list_nav_back)`
- `"Ошибка загрузки"` → `stringResource(R.string.session_list_error)`
- `"Повторить"` → `stringResource(R.string.session_list_retry)`
- `"Нет результатов анализа"` → `stringResource(R.string.session_list_empty)`
- Status and element type strings: same `formatElementType()` function

- [ ] **Step 4: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt
git commit -m "refactor(android): extract MetricCard + session UI hardcoded strings"
```

---

#### Task 15: Extract session detail (presentation) + session list (presentation) strings

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt`

- [ ] **Step 1: Extract SessionDetailScreen (presentation/sessiondetail) strings**

Replace:
- `"Левый"` → `stringResource(R.string.session_detail_left_sensor)`
- `"Правый"` → `stringResource(R.string.session_detail_right_sensor)`
- `"Л: пик ${leftPeak}$unit, средн ${leftAvg}$unit"` → `stringResource(R.string.session_detail_left_summary, leftPeak + unit, leftAvg + unit)`
- `"П: пик ${rightPeak}$unit, средн ${rightAvg}$unit"` → `stringResource(R.string.session_detail_right_summary, rightPeak + unit, rightAvg + unit)`
- `"Файлы"` → `stringResource(R.string.session_detail_files)`

- [ ] **Step 2: Extract SessionListScreen (presentation/session) strings**

Replace any remaining hardcoded strings using existing `R.string.session_list_*` keys.

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt
git commit -m "refactor(android): extract presentation layer session strings"
```

---

#### Task 16: Extract RecordingScreen + CalibrationScreen strings

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationScreen.kt`

- [ ] **Step 1: Extract RecordingScreen strings**

Replace:
- `"Л: ${battery}%"` → `stringResource(R.string.recording_left_battery, battery)`
- `"П: ${battery}%"` → `stringResource(R.string.recording_right_battery, battery)`
- `"Переподключение: ${reconnectingSensor?.name?.lowercase()}"` → `stringResource(R.string.recording_reconnecting, reconnectingSensor?.name?.lowercase() ?: "")`

- [ ] **Step 2: Extract CalibrationScreen strings**

Replace:
- `"$secondsLeft с"` → `stringResource(R.string.calibration_countdown, secondsLeft)`

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/recording/RecordingScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/calibration/CalibrationScreen.kt
git commit -m "refactor(android): extract RecordingScreen + CalibrationScreen hardcoded strings"
```

---

#### Task 17: Extract Profile + More + Camera strings

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/MoreScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt`

- [ ] **Step 1: Extract MoreScreen strings**

Replace:
- `"More"` → `stringResource(R.string.more_title)`
- `"Sensors"` → `stringResource(R.string.more_sensors)`
- `"BLE Scan"` → `stringResource(R.string.more_ble_scan)`
- `"About"` → `stringResource(R.string.more_about)`
- `"App version"` → `stringResource(R.string.more_app_version)`
- `"Log out"` → `stringResource(R.string.more_log_out)`

- [ ] **Step 2: Extract ProfileScreen strings**

Replace:
- `"Save profile"` → `stringResource(R.string.profile_save)`
- `"Saved"` → `stringResource(R.string.profile_saved)`
- `"Log out"` → `stringResource(R.string.profile_log_out)`

- [ ] **Step 3: Extract CameraScreen strings**

Replace:
- `"Preparing camera…"` → `stringResource(R.string.camera_preparing)`
- `"Reconnecting: ${reconnectingSensor?.name?.lowercase()}"` → `stringResource(R.string.camera_reconnecting, reconnectingSensor?.name?.lowercase() ?: "")`

- [ ] **Step 4: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/MoreScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt
git commit -m "refactor(android): extract Profile + More + Camera hardcoded strings"
```

---

#### Task 18: Final i18n verification — Lint + grep audit

**Files:**

- No new file changes — verification only

- [ ] **Step 1: Grep for remaining hardcoded Russian strings**

Run: `grep -rn '[а-яА-ЯёЁ]' mobile/androidApp/src/main/java/ru/skatelab/capture/ --include='*.kt' | grep -v '//.*[а-я]' | grep -v 'Log\.' | grep -v 'import' | grep -v 'package'`
Expected: 0 results (or only log/import/package lines)

- [ ] **Step 2: Verify all string keys exist in both values/ and values-ru/**

Run: `diff <(grep 'name=' mobile/androidApp/src/main/res/values/strings.xml | sed 's/.*name="\([^"]*\)".*/\1/' | sort) <(grep 'name=' mobile/androidApp/src/main/res/values-ru/strings.xml | sed 's/.*name="\([^"]*\)".*/\1/' | sort)`
Expected: No differences (both files have identical keys)

- [ ] **Step 3: Run Lint for missing translations (informational)**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp lint 2>&1 | grep -i "MissingTranslation" | head -5`
Expected: 0 missing translations

- [ ] **Step 4: Run unit tests**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp testDebugUnitTest 2>&1 | tail -5`
Expected: PASS

---

### Stream B: Accessibility

These tasks can run in parallel with Stream A. 70% of accessibility work has no i18n dependency. The remaining 30% (localized contentDescription) waits for Stream A to complete.

---

#### Task 19: Fix contentDescription = null on interactive icons

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/MoreScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt`

- [ ] **Step 1: Replace null contentDescription with stringResource**

ProcessingScreen.kt line 106:
```kotlin
// Before: Icon(..., contentDescription = null)
// After:
Icon(..., contentDescription = stringResource(R.string.cd_error_icon))
```

MoreScreen.kt line 99:
```kotlin
Icon(Icons.Default.Bluetooth, contentDescription = null)
// →
Icon(Icons.Default.Bluetooth, contentDescription = stringResource(R.string.cd_ble_sensor))
```

MoreScreen.kt line 131:
```kotlin
Icon(Icons.Default.Info, contentDescription = null)
// →
Icon(Icons.Default.Info, contentDescription = stringResource(R.string.cd_app_info))
```

MoreScreen.kt line 156:
```kotlin
Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null)
// →
Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = stringResource(R.string.cd_logout))
```

ProfileScreen.kt line 251:
```kotlin
Icon(Icons.Default.Save, contentDescription = null)
// →
Icon(Icons.Default.Save, contentDescription = stringResource(R.string.cd_save_profile))
```

SessionDetailScreen.kt (presentation) line 415:
```kotlin
Icon(Icons.Default.IosShare, contentDescription = null)
// →
Icon(Icons.Default.IosShare, contentDescription = stringResource(R.string.cd_export_session))
```

- [ ] **Step 2: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/MoreScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt
git commit -m "fix(a11y): replace null contentDescription on interactive icons"
```

---

#### Task 20: Add semantics to SkeletonOverlay

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/skeleton/SkeletonOverlay.kt`

- [ ] **Step 1: Add clearAndSetSemantics to SkeletonOverlay**

The SkeletonOverlay is a Canvas-based decorative composable. Add `Modifier.clearAndSetSemantics` so TalkBack announces it as an image and skips the internal Canvas nodes:

```kotlin
@Composable
fun SkeletonOverlay(
    modifier: Modifier = Modifier,
    // ... existing params
) {
    Canvas(
        modifier = modifier.clearAndSetSemantics {
            contentDescription = context.getString(R.string.cd_skeleton_overlay)
            role = Role.Image
        }
    ) {
        // ... existing drawing code
    }
}
```

Note: If `SkeletonOverlay` doesn't have a `context` parameter, use `LocalContext.current` inside the Composable or pass the string resource ID and resolve it in the semantics block.

- [ ] **Step 2: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/skeleton/SkeletonOverlay.kt
git commit -m "fix(a11y): add clearAndSetSemantics to SkeletonOverlay"
```

---

#### Task 21: Add semantics to IMU charts and progress indicators

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt`
- Modify: Various screens with CircularProgressIndicator (ProcessingScreen, RecordingScreen, SessionListScreen, ProfileScreen, LoginScreen, RegisterScreen, SplashScreen)

- [ ] **Step 1: Add semantics to Vico IMU chart sections**

In `SessionDetailScreen.kt` (presentation/sessiondetail), wrap the `CartesianChartHost` or chart Composable:

```kotlin
CartesianChartHost(
    modifier = Modifier.semantics(mergeDescendants = true) {
        contentDescription = context.getString(R.string.cd_imu_chart, leftPeak, rightPeak)
        role = Role.Image
    },
    // ... existing params
)
```

Note: `leftPeak` and `rightPeak` are existing local variables in the chart section. Use string interpolation or `formatArg` depending on how the chart section is structured.

- [ ] **Step 2: Add progress indicator semantics**

For each `CircularProgressIndicator` that appears during a loading state, wrap it in a Box with semantics:

```kotlin
Box(
    modifier = Modifier.semantics(mergeDescendants = true) {
        contentDescription = context.getString(R.string.cd_loading)
        role = Role.ProgressIndicator
    }
) {
    CircularProgressIndicator(modifier = Modifier.size(48.dp))
}
```

Apply to: ProcessingScreen, SessionListScreen (presentation), ProfileScreen loading state, LoginScreen, RegisterScreen.

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/LoginScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt
git commit -m "fix(a11y): add semantics to IMU charts and progress indicators"
```

---

#### Task 22: Add semantics to MetricCard and SessionCard (mergeDescendants)

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt`

- [ ] **Step 1: Add mergeDescendants to MetricCard**

```kotlin
@Composable
fun MetricCard(
    // ... existing params
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.semantics(mergeDescendants = true) {
            // MetricCard is read as a single entity by TalkBack
        }
    ) {
        // ... existing content
    }
}
```

- [ ] **Step 2: Add mergeDescendants to session list item cards**

In SessionListScreen (presentation), add `semantics(mergeDescendants = true)` to each session item Card.

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt
git commit -m "fix(a11y): add mergeDescendants semantics to MetricCard and SessionCard"
```

---

#### Task 23: Add liveRegion on error states

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt`

- [ ] **Step 1: Add LiveRegion.Polite to error containers**

In ProcessingScreen.kt, the error display section:

```kotlin
Column(
    modifier = Modifier.semantics {
        liveRegion = LiveRegion.Polite
        contentDescription = error.asString()
    }
) {
    // existing error UI
}
```

In BleScanScreen.kt, the scan status display:

```kotlin
Text(
    status.asString(),
    modifier = Modifier.semantics {
        liveRegion = LiveRegion.Polite
    },
    // ... existing style params
)
```

- [ ] **Step 2: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt
git commit -m "fix(a11y): add LiveRegion.Polite on error/status announcements"
```

---

#### Task 24: Fix touch target sizes

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt`

- [ ] **Step 1: Fix small IconButtons**

In SessionListScreen (ui/session), change:
```kotlin
// Before: modifier = Modifier.size(32.dp)
IconButton(onClick = ..., modifier = Modifier.size(32.dp)) { ... }

// After: Remove explicit size — IconButton defaults to 48dp minimum touch target
IconButton(onClick = ...) { ... }
```

For icons inside buttons that are 18dp:
```kotlin
// Before: modifier = Modifier.size(18.dp)
Icon(Icons.Default.IosShare, ..., modifier = Modifier.size(18.dp))

// After: Let icon use default size (24dp)
Icon(Icons.Default.IosShare, ..., modifier = Modifier.size(24.dp))
```

In MetricCard.kt, change 16dp icon to 24dp:
```kotlin
Icon(..., modifier = Modifier.size(16.dp))
// →
Icon(..., modifier = Modifier.size(24.dp))
```

In CameraScreen.kt, change 16dp BLE indicator to 24dp:
```kotlin
Icon(Icons.Default.Bluetooth, modifier = Modifier.size(16.dp))
// →
Icon(Icons.Default.Bluetooth, modifier = Modifier.size(24.dp))
```

- [ ] **Step 2: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt
git commit -m "fix(a11y): fix touch target sizes — minimum 48dp buttons, 24dp icons"
```

---

#### Task 25: Add enableAccessibilityChecks() to instrumented tests (AFTER Stream A completes)

**Files:**

- Modify: `mobile/androidApp/build.gradle.kts`
- Create or modify: instrumented test file for accessibility

This task depends on Stream A completing because accessibility checks validate string resources exist.

- [ ] **Step 1: Add ui-test-junit4-accessibility dependency**

In `mobile/androidApp/build.gradle.kts`, add:

```kotlin
androidTestImplementation("androidx.compose.ui:ui-test-junit4-accessibility:1.8.2")
```

- [ ] **Step 2: Create accessibility test**

```kotlin
// mobile/androidApp/src/androidTest/java/ru/skatelab/capture/AccessibilityTest.kt
package ru.skatelab.capture

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.junit4.enableAccessibilityChecks
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.tryPerformAccessibilityChecks
import org.junit.Rule
import org.junit.Test
import ru.skatelab.capture.MainActivity

class AccessibilityTest {

    @get:Rule
    val composeTestRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun mainScreenHasNoAccessibilityIssues() {
        composeTestRule.enableAccessibilityChecks()
        composeTestRule.onRoot().tryPerformAccessibilityChecks()
    }
}
```

Note: This test requires an emulator/CI with instrumented test support. It will not run in local unit tests. Run on GitHub Actions only.

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/build.gradle.kts mobile/androidApp/src/androidTest/java/ru/skatelab/capture/AccessibilityTest.kt
git commit -m "test(a11y): add enableAccessibilityChecks() instrumented test"
```

---

### Stream C: Security

These tasks are fully independent of each other and of Streams A/B.

---

#### Task 26: Replace ProGuard rules with narrow keeps

**Files:**

- Modify: `mobile/androidApp/proguard-rules.pro`

- [ ] **Step 1: Replace the entire proguard-rules.pro file**

The current file only has 4 lines (protobuf keep rules). Replace with the corrected rules from the parallelization report:

```proguard
# ============================================================
# SkateLab ProGuard Rules — R8 Full Mode
# Strategy: Minimize manual rules. Prefer library consumer rules.
# ============================================================

# === kotlinx.serialization ===
# Consumer rules bundled since v1.7+. Explicit safety net:
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    static ** Companion;
}
-if @kotlinx.serialization.Serializable class ** {
    static **$* *;
}
-keepclassmembers class <2>$<3> {
    kotlinx.serialization.KSerializer serializer(...);
}
-if @kotlinx.serialization.Serializable class ** {
    public static ** INSTANCE;
}
-keepclassmembers class <1> {
    public static <1> INSTANCE;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclassmembers public class **$$serializer {
    private ** descriptor;
}
-keepattributes RuntimeVisibleAnnotations, AnnotationDefault
-dontnote kotlinx.serialization.**
-dontwarn kotlinx.serialization.internal.ClassValueReferences

# === Ktor Client ===
# No consumer rules. Narrow keeps only — do NOT use -keep class io.ktor.**
-keep class io.ktor.client.plugins.** { *; }
-dontwarn io.ktor.**

# === OkHttp (consumer rules bundled, safety net) ===
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# === Room (consumer rules bundled, safety net) ===
-keep class * extends androidx.room.RoomDatabase { *; }

# === Hilt / Dagger (consumer rules bundled, safety net) ===
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }

# === Kable BLE (no consumer rules) ===
-keep class com.juul.kable.** { public *; }
-dontwarn com.juul.kable.**

# === SkateLab models (serialized) ===
-keep class ru.skatelab.shared.models.** { *; }
-keep class ru.skatelab.shared.api.** { *; }
-keep class ru.skatelab.shared.auth.** { *; }

# === Protobuf (existing) ===
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    *** dynamicMethod(com.google.protobuf.GeneratedMessageLite$MethodToInvoke, java.lang.Object, java.lang.Object);
}
-keep class ru.skatelab.capture.proto.** { *; }

# === Kotlin coroutines (consumer rules bundled, safety net) ===
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembers class kotlinx.coroutines.** {
    volatile <fields>;
}

# === General Android ===
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# === R8 diagnostics (CI review) ===
-printconfiguration build/outputs/mapping/release-configuration.txt
-printseeds build/outputs/mapping/release-seeds.txt
-printusage build/outputs/mapping/release-usage.txt
```

- [ ] **Step 2: Commit**

```bash
git add mobile/androidApp/proguard-rules.pro
git commit -m "fix(security): replace ProGuard rules with narrow keeps, add R8 diagnostics"
```

---

#### Task 27: Create Network Security Config

**Files:**

- Create: `mobile/androidApp/src/main/res/xml/network_security_config.xml`
- Modify: `mobile/androidApp/src/main/AndroidManifest.xml`

- [ ] **Step 1: Create the NSC file**

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Production: pin API certificate with backup for rotation -->
    <domain-config cleartextTrafficPermitted="false">
        <domain includeSubdomains="true">api.skatelab.com</domain>
        <pin-set expiration="2028-12-31">
            <!-- Primary: current production certificate SPKI hash -->
            <pin digest="SHA-256">PRODUCTION_PIN_BASE64_HERE</pin>
            <!-- Backup: different CA key for rotation (pre-pinned) -->
            <pin digest="SHA-256">BACKUP_PIN_BASE64_HERE</pin>
        </pin-set>
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </domain-config>

    <!-- Debug: trust user-added CAs for Charles/proxy tools -->
    <debug-overrides>
        <trust-anchors>
            <certificates src="system"/>
            <certificates src="user"/>
        </trust-anchors>
    </debug-overrides>
</network-security-config>
```

- [ ] **Step 2: Reference NSC in AndroidManifest.xml**

Add to the `<application>` tag in `mobile/androidApp/src/main/AndroidManifest.xml`:

```xml
<application
    android:name=".App"
    android:allowBackup="false"
    android:networkSecurityConfig="@xml/network_security_config"
    android:label="@string/app_name"
    android:supportsRtl="true"
    android:theme="@style/Theme.SkatelabCapture">
```

- [ ] **Step 3: Compile check**

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileDebugKotlin 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/res/xml/network_security_config.xml mobile/androidApp/src/main/AndroidManifest.xml
git commit -m "feat(security): add Network Security Config with certificate pinning"
```

---

#### Task 28: API key safety audit

**Files:**

- No code changes expected — audit only

- [ ] **Step 1: Grep for hardcoded API keys/tokens/secrets**

Run: `grep -rn -i 'api_key\|apikey\|secret\|token\|password' mobile/androidApp/src/main/java/ --include='*.kt' | grep -v 'import\|//\|Log\.\|TokenStorage\|BuildConfig\|fun \|val \[a-z].*: String' | grep -v 'R.string\|R.array'`
Expected: 0 results (all secrets should be in BuildConfig or env vars)

Run: `grep -rn 'hardcoded\|\"\b[a-zA-Z0-9]{32,}\b\"' mobile/androidApp/src/main/java/ --include='*.kt' | grep -v 'import\|//\|package'`
Expected: 0 results

- [ ] **Step 2: Verify BuildConfig fields for API keys**

Run: `grep -rn 'buildConfigField\|BuildConfig\.' mobile/androidApp/build.gradle.kts`
Expected: If any API keys exist, they must use `buildConfigField` from environment variables.

- [ ] **Step 3: Document findings**

If any hardcoded secrets found, create a fix task. Otherwise, report "No hardcoded API keys found."

---

#### Task 29: Add APK size monitoring CI step

**Files:**

- Modify: `.github/workflows/mobile.yml` (or the appropriate CI workflow)

- [ ] **Step 1: Add APK size check step**

After the APK build step in the mobile CI workflow, add:

```yaml
- name: Check APK size
  run: |
    APK_PATH=$(find mobile/androidApp/build/outputs/apk/debug -name '*.apk' | head -1)
    if [ -n "$APK_PATH" ]; then
      APK_SIZE=$(stat -c%s "$APK_PATH")
      echo "APK size: $APK_SIZE bytes ($(( APK_SIZE / 1048576 )) MB)"
      if [ $APK_SIZE -gt 52428800 ]; then
        echo "::warning::APK exceeds 50 MB ($(( APK_SIZE / 1048576 )) MB)"
      fi
    fi
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/mobile.yml
git commit -m "ci(mobile): add APK size monitoring step (warns > 50 MB)"
```

---

#### Task 30: Release build verification (after Tasks 26-27)

**Files:**

- No code changes — verification only

This task depends on Tasks 26 and 27 (ProGuard rules and NSC must be in place).

- [ ] **Step 1: Trigger release build on CI**

Push to a PR branch and check GitHub Actions `mobile.yml` workflow output. The release build must:
1. Compile with `isMinifyEnabled = true` + `isShrinkResources = true`
2. Pass all unit tests
3. Not crash on launch (verified by instrumented tests if available)

Run: `cd /home/dev/skatelab && ./gradlew -p mobile/androidApp compileReleaseKotlin 2>&1 | tail -10`
Expected: BUILD SUCCESSFUL

Note: Full `assembleRelease` requires signing config (not yet configured). `compileReleaseKotlin` verifies R8/ProGuard rules don't break compilation.

- [ ] **Step 2: Check R8 diagnostic output (if release build succeeds)**

Run: `ls -la mobile/androidApp/build/outputs/mapping/ 2>/dev/null`
Expected: `release-configuration.txt`, `release-seeds.txt`, `release-usage.txt` files exist

---

## Summary: Parallel Execution Map

| Task | Stream | Depends On | Can Parallel With |
|------|--------|-----------|-------------------|
| 1 | Phase 1 | — | Nothing (sequential foundation) |
| 2 | Phase 1 | Task 1 | Nothing |
| 3 | Phase 1 | Task 2 | Nothing |
| 4 | Phase 1 | Task 2 | Task 3 |
| 5 | Phase 1 | Task 2 | Tasks 3-4 |
| 6 | Phase 1 | Tasks 1-2 | Tasks 3-5 |
| 7 | Phase 1 | Task 6 | Tasks 3-5 |
| 8 | Phase 1 | — | Tasks 1-7 |
| 9 | Phase 1 | — | Tasks 1-7 |
| 10 | Phase 1 | Task 9 | Tasks 1-8 |
| 11 | Stream A | Phase 1 | Streams B, C |
| 12 | Stream A | Task 11 | Tasks 13-17, Streams B, C |
| 13 | Stream A | Task 11 | Tasks 12, 14-17, Streams B, C |
| 14 | Stream A | Task 11 | Tasks 12-13, 15-17, Streams B, C |
| 15 | Stream A | Task 11 | Tasks 12-14, 16-17, Streams B, C |
| 16 | Stream A | Task 11 | Tasks 12-15, 17, Streams B, C |
| 17 | Stream A | Task 11 | Tasks 12-16, Streams B, C |
| 18 | Stream A | Tasks 12-17 | Streams B, C |
| 19 | Stream B | — | Streams A, C |
| 20 | Stream B | — | Tasks 19, 21-25, Streams A, C |
| 21 | Stream B | — | Tasks 19-20, 22-25, Streams A, C |
| 22 | Stream B | — | Tasks 19-21, 23-25, Streams A, C |
| 23 | Stream B | — | Tasks 19-22, 24-25, Streams A, C |
| 24 | Stream B | — | Tasks 19-23, 25, Streams A, C |
| 25 | Stream B | Stream A | Task 24, Streams A, C |
| 26 | Stream C | — | Streams A, B |
| 27 | Stream C | — | Task 26, Streams A, B |
| 28 | Stream C | — | Tasks 26-27, Streams A, B |
| 29 | Stream C | — | Tasks 26-28, Streams A, B |
| 30 | Stream C | Tasks 26-27 | Tasks 28-29, Streams A, B |
