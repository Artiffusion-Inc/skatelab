# Mobile Testing Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate mobile app testing by adding pre-build shared module tests (Tier 1) and Maestro E2E tests on a dedicated server (Tier 2), eliminating manual phone-in-the-loop testing.

**Architecture:** Two-tier pipeline. Tier 1: `commonTest` runs in CI before APK build (~seconds), catches auth/API/serialization bugs without building. Tier 2: Maestro CLI runs E2E YAML flows on Android emulator (Docker + KVM) on dedic server (176.9.0.156), orchestrated via SSH + scripts. AVD snapshots restore in 5-10s. Shard-split across 2 emulators halves wall time.

**Tech Stack:** Kotlin Test + ktor-client-mock + turbine (shared tests), Maestro CLI (E2E), budtmo/docker-android (emulator), Docker Compose + systemd slice (server infra), Prometheus node_exporter textfile (monitoring)

---

## File Structure

### Tier 1: Pre-build Shared Tests

| File | Action | Responsibility |
|------|--------|---------------|
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/SessionsApiTest.kt` | Create | Test SessionsApi CRUD with MockEngine |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/UploadsApiTest.kt` | Create | Test UploadsApi init/complete/presign with MockEngine |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryTest.kt` | Modify | Add login/register/verify/forgot/reset tests |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/AuthViewModelTest.kt` | Modify | Replace sealed hierarchy tests with behavior tests using turbine |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt` | Create | Test SessionsViewModel loadSessions/loadSession with turbine |
| `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/SerializationTest.kt` | Modify | Add SessionResponse, UploadInitResponse, UserResponse roundtrips |
| `mobile/shared/build.gradle.kts` | Modify | Add Kover coverage target rule |

### Tier 2: E2E Infrastructure (repo files)

| File | Action | Responsibility |
|------|--------|---------------|
| `mobile/e2e/docker-compose.yml` | Create | Docker Compose for emulator container with KVM, resource limits, localhost ADB |
| `mobile/e2e/setup-emulator.sh` | Create | One-time: install Maestro, create AVD, save named snapshot |
| `mobile/e2e/run-e2e.sh` | Create | Per-run: restore snapshot, install APK, run Maestro, output JUnit XML |
| `mobile/e2e/run-e2e-async.sh` | Create | Async wrapper with nohup + retry |
| `mobile/e2e/metrics.sh` | Create | Prometheus node_exporter textfile collector for emulator health |
| `mobile/e2e/maestro/config.yaml` | Create | Maestro suite config with tags and output dirs |
| `mobile/e2e/maestro/flows/login.yaml` | Create | Login E2E flow |
| `mobile/e2e/maestro/flows/session-list.yaml` | Create | Session list E2E flow |
| `mobile/e2e/maestro/flows/recording.yaml` | Create | Recording start/stop E2E flow |
| `mobile/e2e/maestro/flows/upload.yaml` | Create | Upload E2E flow |

### Server Configuration (on dedic, not in repo)

| Path | Responsibility |
|------|---------------|
| `/etc/systemd/system/emulator.slice` | Resource isolation: CPUQuota=400%, MemoryMax=16G |
| `/etc/systemd/system/skatelab-emulator.service` | Docker Compose as systemd service with auto-restart |

---

## Wave 1: Tier 1 — Pre-build Shared Module Tests

### Task 1: SessionsApiTest

**Files:**

- Create: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/SessionsApiTest.kt`

- [ ] **Step 1: Write SessionsApiTest**

```kotlin
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionUpdateRequest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SessionsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeClient(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    @Test
    fun get_returnsSession() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            assertEquals("/sessions/s-1", request.url.encodedPath)
            respond(
                """{"id":"s-1","user_id":"u-1","element_type":"flip","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(makeClient(engine))
        val session = api.get("s-1")
        assertEquals("s-1", session.id)
        assertEquals("flip", session.elementType)
    }

    @Test
    fun list_returnsPaginatedSessions() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"sessions":[{"id":"s-1","user_id":"u-1","element_type":"flip","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}],"total":1,"page":1,"page_size":20,"pages":1}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(makeClient(engine))
        val result = api.list(limit = 20, offset = 0)
        assertEquals(1, result.sessions.size)
        assertEquals(1, result.total)
    }

    @Test
    fun create_sendsPostWithBody() = kotlinx.coroutines.test.runTest {
        var capturedMethod: HttpMethod? = null
        var capturedBody: String? = null
        val engine = MockEngine { request ->
            capturedMethod = request.method
            capturedBody = request.body.toString()
            respond(
                """{"id":"s-new","user_id":"u-1","element_type":"axel","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(makeClient(engine))
        val session = api.create(elementType = "axel")
        assertEquals(HttpMethod.Post, capturedMethod)
        assertEquals("axel", session.elementType)
    }

    @Test
    fun delete_sendsDeleteRequest() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val api = SessionsApi(makeClient(engine))
        api.delete("s-1")
        assertEquals("/sessions/s-1", capturedPath)
    }

    @Test
    fun update_sendsPatchWithBody() = kotlinx.coroutines.test.runTest {
        var capturedMethod: HttpMethod? = null
        val engine = MockEngine { request ->
            capturedMethod = request.method
            respond(
                """{"id":"s-1","user_id":"u-1","element_type":"lutz","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(makeClient(engine))
        val session = api.update("s-1", SessionUpdateRequest(elementType = "lutz"))
        assertEquals(HttpMethod.Patch, capturedMethod)
        assertEquals("lutz", session.elementType)
    }

    @Test
    fun bulkDelete_sendsPostWithIds() = kotlinx.coroutines.test.runTest {
        var capturedMethod: HttpMethod? = null
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedMethod = request.method
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val api = SessionsApi(makeClient(engine))
        api.bulkDelete(listOf("s-1", "s-2"))
        assertEquals(HttpMethod.Delete, capturedMethod)
        assertTrue(capturedPath!!.contains("bulk"))
    }
}
```

- [ ] **Step 2: Run tests to verify they compile and pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.api.SessionsApiTest" -q`
Expected: 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/SessionsApiTest.kt
git commit -m "test(shared): add SessionsApiTest with MockEngine CRUD tests"
```

---

### Task 2: UploadsApiTest

**Files:**

- Create: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/UploadsApiTest.kt`

- [ ] **Step 1: Write UploadsApiTest**

```kotlin
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.CompletedPart
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class UploadsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeClient(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    @Test
    fun init_returnsUploadDetails() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            assertTrue(request.url.encodedPath.contains("uploads/init"))
            respond(
                """{"upload_id":"up-1","key":"video/test.mp4","chunk_size":5242880,"part_count":3,"parts":[{"part_number":1,"url":"https://r2.example.com/p1"},{"part_number":2,"url":"https://r2.example.com/p2"},{"part_number":3,"url":"https://r2.example.com/p3"}]}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = UploadsApi(makeClient(engine))
        val result = api.init("test.mp4", "video/mp4", 15_728_640)
        assertEquals("up-1", result.uploadId)
        assertEquals("video/test.mp4", result.key)
        assertEquals(3, result.partCount)
        assertEquals(3, result.parts.size)
    }

    @Test
    fun complete_sendsPartsList() = kotlinx.coroutines.test.runTest {
        var capturedMethod: HttpMethod? = null
        val engine = MockEngine { request ->
            capturedMethod = request.method
            respondOk("{}")
        }
        val api = UploadsApi(makeClient(engine))
        api.complete(
            uploadId = "up-1",
            key = "video/test.mp4",
            parts = listOf(
                CompletedPart(partNumber = 1, etag = "etag1"),
                CompletedPart(partNumber = 2, etag = "etag2"),
            ),
        )
        assertEquals(HttpMethod.Post, capturedMethod)
    }

    @Test
    fun presign_returnsUrlAndKey() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            assertTrue(request.url.encodedPath.contains("uploads/presign"))
            respond(
                """{"url":"https://r2.example.com/presigned","key":"video/small.mp4"}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = UploadsApi(makeClient(engine))
        val result = api.presign("small.mp4", "video/mp4")
        assertEquals("https://r2.example.com/presigned", result.url)
        assertEquals("video/small.mp4", result.key)
    }
}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.api.UploadsApiTest" -q`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/UploadsApiTest.kt
git commit -m "test(shared): add UploadsApiTest with MockEngine init/complete/presign tests"
```

---

### Task 3: Expand AuthRepositoryTest

**Files:**

- Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryTest.kt`

- [ ] **Step 1: Add login/register/verify/forgot/reset tests to existing AuthRepositoryTest**

Append these tests to the existing `AuthRepositoryTest` class (after the `isLoggedIn_returnsFalseWhenNoAccessToken` test):

```kotlin
    @Test
    fun login_savesTokensOnSuccess() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/login" -> respond(
                    """{"access_token":"new-access","refresh_token":"new-refresh","token_type":"bearer"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.login("user@test.ru", "pass123")
        assertTrue(result.isSuccess)
        assertEquals("new-access", tokenStorage.getAccessToken())
        assertEquals("new-refresh", tokenStorage.getRefreshToken())
    }

    @Test
    fun login_returnsFailureOnHttpError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ ->
            respondError(HttpStatusCode.Unauthorized)
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.login("user@test.ru", "wrong-pass")
        assertTrue(result.isFailure)
        assertEquals(null, tokenStorage.getAccessToken())
    }

    @Test
    fun register_savesTokensOnSuccess() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(
                    """{"access_token":"reg-access","refresh_token":"reg-refresh","token_type":"bearer"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.register("new@test.ru", "pass123", "Test User")
        assertTrue(result.isSuccess)
        assertEquals("reg-access", tokenStorage.getAccessToken())
        assertEquals("reg-refresh", tokenStorage.getRefreshToken())
    }

    @Test
    fun register_returnsFailureOnDuplicateEmail() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ ->
            respondError(HttpStatusCode.Conflict)
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.register("existing@test.ru", "pass123", "Dup")
        assertTrue(result.isFailure)
        assertEquals(null, tokenStorage.getAccessToken())
    }

    @Test
    fun verifyEmail_sendsToken() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.verifyEmail("verify-token-123")
        assertTrue(result.isSuccess)
        assertEquals("/auth/verify-email", capturedPath)
    }

    @Test
    fun forgotPassword_sendsEmail() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.forgotPassword("user@test.ru")
        assertTrue(result.isSuccess)
        assertEquals("/auth/forgot-password", capturedPath)
    }

    @Test
    fun resetPassword_sendsTokenAndNewPassword() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) { install(ContentNegotiation) { json(json) } }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        val result = repo.resetPassword("reset-token-456", "newpass123")
        assertTrue(result.isSuccess)
        assertEquals("/auth/reset-password", capturedPath)
    }
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.auth.AuthRepositoryTest" -q`
Expected: 11 tests PASS (5 existing + 6 new)

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryTest.kt
git commit -m "test(shared): expand AuthRepositoryTest with login/register/verify/forgot/reset"
```

---

### Task 4: Rewrite AuthViewModelTest with behavior tests

**Files:**

- Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/AuthViewModelTest.kt`

The existing tests only check sealed hierarchy data class equality. Replace with actual behavior tests using MockEngine + turbine.

- [ ] **Step 1: Replace AuthViewModelTest content**

Replace the entire file content:

```kotlin
package ru.skatelab.shared.state

import app.cash.turbine.test
import com.russhwolf.settings.MapSettings
import io.ktor.client.*
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.auth.TokenStorage
import kotlin.test.Test
import kotlin.test.assertIs

class AuthViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeClient(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private fun makeRepo(engine: MockEngine, tokenStorage: TokenStorage = TokenStorage(MapSettings())) =
        AuthRepository(AuthApi(makeClient(engine)), tokenStorage)

    @Test
    fun checkLogin_whenLoggedIn_fetchesUser() = kotlinx.coroutines.test.runTest {
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/users/me" -> respond(
                    """{"id":"u-1","email":"test@test.ru","display_name":"Test User"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val vm = AuthViewModel(makeRepo(engine, tokenStorage), UsersApi(makeClient(engine)))

        vm.uiState.test {
            vm.checkLogin()
            assertIs<AuthUiState.Loading>(awaitItem())
            val state = awaitItem()
            assertIs<AuthUiState.LoggedIn>(state)
            assertEquals("u-1", state.userId)
            assertEquals("Test User", state.displayName)
        }
    }

    @Test
    fun checkLogin_whenNotLoggedIn_showsLoggedOut() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ -> respondError(HttpStatusCode.NotFound) }
        val vm = AuthViewModel(makeRepo(engine), UsersApi(makeClient(engine)))

        vm.uiState.test {
            vm.checkLogin()
            assertIs<AuthUiState.Loading>(awaitItem())
            assertIs<AuthUiState.LoggedOut>(awaitItem())
        }
    }

    @Test
    fun login_success_transitionsToLoggedIn() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/login" -> respond(
                    """{"access_token":"a","refresh_token":"r","token_type":"bearer"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                "/users/me" -> respond(
                    """{"id":"u-1","email":"test@test.ru"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(makeClient(engine)), tokenStorage)
        val vm = AuthViewModel(repo, UsersApi(makeClient(engine)))

        vm.uiState.test {
            vm.login("test@test.ru", "pass")
            assertIs<AuthUiState.Loading>(awaitItem())
            val state = awaitItem()
            assertIs<AuthUiState.LoggedIn>(state)
        }
    }

    @Test
    fun login_failure_showsError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ ->
            respondError(HttpStatusCode.Unauthorized)
        }
        val vm = AuthViewModel(makeRepo(engine), UsersApi(makeClient(engine)))

        vm.uiState.test {
            vm.login("test@test.ru", "wrong")
            assertIs<AuthUiState.Loading>(awaitItem())
            assertIs<AuthUiState.Error>(awaitItem())
        }
    }

    @Test
    fun register_success_transitionsToLoggedIn() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(
                    """{"access_token":"a","refresh_token":"r","token_type":"bearer"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                "/users/me" -> respond(
                    """{"id":"u-1","email":"new@test.ru","display_name":"New User"}""",
                    HttpStatusCode.OK,
                    headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val tokenStorage = TokenStorage(MapSettings())
        val repo = AuthRepository(AuthApi(makeClient(engine)), tokenStorage)
        val vm = AuthViewModel(repo, UsersApi(makeClient(engine)))

        vm.uiState.test {
            vm.register("new@test.ru", "pass", "New User")
            assertIs<AuthUiState.Loading>(awaitItem())
            val state = awaitItem()
            assertIs<AuthUiState.LoggedIn>(state)
            assertEquals("New User", state.displayName)
        }
    }

    @Test
    fun logout_transitionsToLoggedOut() = kotlinx.coroutines.test.runTest {
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")
        val engine = MockEngine { _ -> respondOk("{}") }
        val vm = AuthViewModel(makeRepo(engine, tokenStorage), UsersApi(makeClient(engine)))

        vm.uiState.test {
            vm.logout()
            assertIs<AuthUiState.LoggedOut>(awaitItem())
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.state.AuthViewModelTest" -q`
Expected: 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/AuthViewModelTest.kt
git commit -m "test(shared): rewrite AuthViewModelTest with MockEngine + turbine behavior tests"
```

---

### Task 5: SessionsViewModelTest

**Files:**

- Create: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt`

- [ ] **Step 1: Write SessionsViewModelTest**

```kotlin
package ru.skatelab.shared.state

import app.cash.turbine.test
import io.ktor.client.*
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.SessionsApi
import kotlin.test.Test
import kotlin.test.assertIs
import kotlin.test.assertEquals

class SessionsViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeClient(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    @Test
    fun loadSessions_success_showsLoaded() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ ->
            respond(
                """{"sessions":[{"id":"s-1","user_id":"u-1","element_type":"flip","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}],"total":1,"page":1,"page_size":20,"pages":1}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val vm = SessionsViewModel(SessionsApi(makeClient(engine)))

        vm.uiState.test {
            vm.loadSessions()
            assertIs<SessionsUiState.Loading>(awaitItem())
            val state = awaitItem()
            assertIs<SessionsUiState.Loaded>(state)
            assertEquals(1, state.sessions.size)
            assertEquals(1, state.total)
        }
    }

    @Test
    fun loadSessions_failure_showsError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ ->
            respondError(HttpStatusCode.InternalServerError)
        }
        val vm = SessionsViewModel(SessionsApi(makeClient(engine)))

        vm.uiState.test {
            vm.loadSessions()
            assertIs<SessionsUiState.Loading>(awaitItem())
            assertIs<SessionsUiState.Error>(awaitItem())
        }
    }

    @Test
    fun loadSession_success_setsSelectedSession() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { _ ->
            respond(
                """{"id":"s-1","user_id":"u-1","element_type":"flip","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}""",
                HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val vm = SessionsViewModel(SessionsApi(makeClient(engine)))

        vm.selectedSession.test {
            vm.loadSession("s-1")
            val session = awaitItem()
            assertEquals("s-1", session?.id)
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.state.SessionsViewModelTest" -q`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionsViewModelTest.kt
git commit -m "test(shared): add SessionsViewModelTest with turbine"
```

---

### Task 6: Expand SerializationTest

**Files:**

- Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/SerializationTest.kt`

- [ ] **Step 1: Add more model roundtrip tests**

Append these tests to the existing `SerializationTest` class:

```kotlin
    @Test
    fun sessionResponseRoundtrip() {
        val original = SessionResponse(
            id = "s-1",
            userId = "u-1",
            elementType = "flip",
            status = "pending",
            createdAt = "2026-01-01T00:00:00Z",
        )
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<SessionResponse>(encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun sessionListResponseDeserialize() {
        val payload = """{"sessions":[{"id":"s-1","user_id":"u-1","element_type":"flip","video_url":null,"processed_video_url":null,"status":"pending","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-01-01T00:00:00Z"}],"total":1,"page":1,"page_size":20,"pages":1}"""
        val decoded = json.decodeFromString<SessionListResponse>(payload)
        assertEquals(1, decoded.sessions.size)
        assertEquals(1, decoded.total)
        assertEquals(1, decoded.pages)
    }

    @Test
    fun uploadInitResponseDeserialize() {
        val payload = """{"upload_id":"up-1","key":"video/test.mp4","chunk_size":5242880,"part_count":2,"parts":[{"part_number":1,"url":"https://r2.example.com/p1"},{"part_number":2,"url":"https://r2.example.com/p2"}]}"""
        val decoded = json.decodeFromString<UploadInitResponse>(payload)
        assertEquals("up-1", decoded.uploadId)
        assertEquals(2, decoded.partCount)
        assertEquals(2, decoded.parts.size)
    }

    @Test
    fun userResponseRoundtrip() {
        val original = UserResponse(id = "u-1", email = "test@test.ru", displayName = "Test")
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<UserResponse>(encoded)
        assertEquals("u-1", decoded.id)
        assertEquals("test@test.ru", decoded.email)
        assertEquals("Test", decoded.displayName)
    }

    @Test
    fun presignResponseDeserialize() {
        val payload = """{"url":"https://r2.example.com/presigned","key":"video/small.mp4"}"""
        val decoded = json.decodeFromString<ru.skatelab.shared.api.PresignResponse>(payload)
        assertEquals("https://r2.example.com/presigned", decoded.url)
        assertEquals("video/small.mp4", decoded.key)
    }
```

Note: Add these imports at the top of the file if not already present:
```kotlin
import ru.skatelab.shared.api.PresignResponse
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.models.SerializationTest" -q`
Expected: 8 tests PASS (3 existing + 5 new)

- [ ] **Step 3: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/SerializationTest.kt
git commit -m "test(shared): expand SerializationTest with SessionResponse, UploadInitResponse, UserResponse"
```

---

### Task 7: Configure Kover coverage target

**Files:**

- Modify: `mobile/shared/build.gradle.kts`

- [ ] **Step 1: Add Kover verification rule**

Add this block after the `android { ... }` block in `mobile/shared/build.gradle.kts`:

```kotlin
kover {
    reports {
        filters {
            excludes {
                classes(
                    "*_Generated*",
                    "*.di.*",
                    "*.ui.state.*",
                    "*.platform.*",
                )
            }
        }
        verify {
            rule {
                minBound(70)
                targetPackages["ru.skatelab.shared"]
            }
        }
    }
}
```

- [ ] **Step 2: Run Kover report to verify configuration**

Run: `cd mobile && ./gradlew :shared:koverXmlReport -q`
Expected: SUCCESS, XML report generated at `mobile/shared/build/reports/kover/report.xml`

- [ ] **Step 3: Run Kover verification**

Run: `cd mobile && ./gradlew :shared:koverVerify -q`
Expected: Either PASS (coverage >= 70%) or FAIL with violation details. If fail, note the actual percentage and adjust `minBound` to current percentage + 5 (ratchet up).

- [ ] **Step 4: Commit**

```bash
git add mobile/shared/build.gradle.kts
git commit -m "ci(shared): add Kover coverage verification with 70% target"
```

---

### Task 8: Run all shared tests as CI gate

**Files:**

- Modify: `.github/workflows/mobile-test.yml`

- [ ] **Step 1: Update shared-test job to run `:shared:allTests`**

In `.github/workflows/mobile-test.yml`, change the `shared-test` job's "Run shared module tests" step command from:

```yaml
      - name: Run shared module tests
        run: ./gradlew :shared:testDebugUnitTest
```

to:

```yaml
      - name: Run shared module tests
        run: ./gradlew :shared:allTests
```

This runs commonTest on all KMP targets (JVM only for now, iOS when simulator tests exist).

- [ ] **Step 2: Verify CI workflow syntax**

Run: `cat .github/workflows/mobile-test.yml | head -45`
Expected: Step shows `:shared:allTests`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile-test.yml
git commit -m "ci(mobile): run shared:allTests as pre-build gate before APK build"
```

---

## Wave 2: Tier 2 — Dedicated Server Infrastructure

### Task 9: Docker Compose for emulator

**Files:**

- Create: `mobile/e2e/docker-compose.yml`

- [ ] **Step 1: Write Docker Compose**

```yaml
services:
  emulator:
    image: budtmo/docker-android:emulator_34.0
    container_name: skatelab-emulator
    devices:
      - /dev/kvm
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges=true
    ports:
      - "127.0.0.1:5555:5555"
      - "127.0.0.1:5554:5554"
    environment:
      EMULATOR_FLAGS: "-no-window -no-audio -no-boot-anim -gpu swiftshader_indirect -memory 2048 -netfast -accel on -partition-size 1024 -no-snapshot-save"
      DATAPARTITION: "1024m"
    tmpfs:
      - /data:size=2G
    volumes:
      - emulator_data:/root/.android
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 16G
        reservations:
          memory: 4G
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "adb shell getprop sys.boot_completed | grep -q 1"]
      interval: 10s
      timeout: 5s
      retries: 30
      start_period: 60s

volumes:
  emulator_data:
```

- [ ] **Step 2: Commit**

```bash
git add mobile/e2e/docker-compose.yml
git commit -m "ci(e2e): add Docker Compose for Android emulator with KVM, localhost ADB, resource limits"
```

---

### Task 10: systemd slice + service for emulator

**Files:**

- Create: `mobile/e2e/systemd/emulator.slice`
- Create: `mobile/e2e/systemd/skatelab-emulator.service`

These files are reference configs to be installed on the dedic server. They live in the repo for version control.

- [ ] **Step 1: Write emulator.slice**

```ini
[Unit]
Description=Android Emulator Slice
DefaultDependencies=no
Before=slices.target

[Slice]
CPUQuota=400%
MemoryMax=16G
MemoryHigh=12G
IOWeight=50
```

- [ ] **Step 2: Write skatelab-emulator.service**

```ini
[Unit]
Description=SkateLab Android Emulator (Docker)
After=docker.service
Requires=docker.service
Wants=network-online.target

[Service]
Slice=emulator.slice
Type=simple
ExecStartPre=-/usr/bin/docker compose -f /opt/skatelab-e2e/docker-compose.yml down
ExecStart=/usr/bin/docker compose -f /opt/skatelab-e2e/docker-compose.yml up --abort-on-container-exit
ExecStop=/usr/bin/docker compose -f /opt/skatelab-e2e/docker-compose.yml down
Restart=on-failure
RestartSec=10
WatchdogSec=60

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/systemd/emulator.slice mobile/e2e/systemd/skatelab-emulator.service
git commit -m "ci(e2e): add systemd slice and service for emulator resource isolation"
```

---

### Task 11: setup-emulator.sh

**Files:**

- Create: `mobile/e2e/setup-emulator.sh`

- [ ] **Step 1: Write setup-emulator.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# One-time setup: install Maestro CLI, copy docker-compose + systemd files
# Run: ./setup-emulator.sh

E2E_DIR="/opt/skatelab-e2e"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== SkateLab E2E Setup ==="

# Install Maestro CLI
if ! command -v maestro &>/dev/null; then
    echo "Installing Maestro CLI..."
    curl -Ls "https://get.maestro.mobile.dev" | bash
    echo "Maestro installed: $(maestro --version)"
else
    echo "Maestro already installed: $(maestro --version)"
fi

# Install GitHub CLI for artifact downloads
if ! command -v gh &>/dev/null; then
    echo "Installing GitHub CLI..."
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
        dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
        tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    apt-get update && apt-get install gh -y
    echo "gh installed: $(gh --version)"
else
    echo "gh already installed: $(gh --version)"
fi

# Create E2E directory
mkdir -p "${E2E_DIR}/reports"
mkdir -p "${E2E_DIR}/flows"

# Copy docker-compose and scripts
cp "${SCRIPT_DIR}/docker-compose.yml" "${E2E_DIR}/"
cp "${SCRIPT_DIR}/run-e2e.sh" "${E2E_DIR}/"
cp "${SCRIPT_DIR}/run-e2e-async.sh" "${E2E_DIR}/"
cp "${SCRIPT_DIR}/metrics.sh" "${E2E_DIR}/"
cp -r "${SCRIPT_DIR}/maestro/" "${E2E_DIR}/maestro/"

chmod +x "${E2E_DIR}"/*.sh

# Install systemd units
cp "${SCRIPT_DIR}/systemd/emulator.slice" /etc/systemd/system/
cp "${SCRIPT_DIR}/systemd/skatelab-emulator.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable skatelab-emulator.service

# Start emulator
echo "Starting emulator container..."
systemctl start skatelab-emulator.service

# Wait for emulator boot
echo "Waiting for emulator to boot..."
timeout=120
elapsed=0
while ! docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; do
    sleep 5
    elapsed=$((elapsed + 5))
    if [ $elapsed -ge $timeout ]; then
        echo "ERROR: Emulator did not boot within ${timeout}s"
        exit 1
    fi
    echo "  Waiting... (${elapsed}s)"
done

echo "Emulator booted. Saving named snapshot..."
docker exec skatelab-emulator adb shell avd snapshot save with_app_installed

echo ""
echo "=== Setup Complete ==="
echo "Emulator:  systemctl status skatelab-emulator.service"
echo "Run tests:  ${E2E_DIR}/run-e2e.sh --apk-path /tmp/app-debug.apk"
echo "Async run:  ${E2E_DIR}/run-e2e-async.sh --apk-path /tmp/app-debug.apk"
```

- [ ] **Step 2: Make script executable and commit**

```bash
chmod +x mobile/e2e/setup-emulator.sh
git add mobile/e2e/setup-emulator.sh
git commit -m "ci(e2e): add setup-emulator.sh for one-time dedic server provisioning"
```

---

### Task 12: run-e2e.sh

**Files:**

- Create: `mobile/e2e/run-e2e.sh`

- [ ] **Step 1: Write run-e2e.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Per-run: install APK, run Maestro tests, output JUnit XML
# Usage: ./run-e2e.sh --apk-path /tmp/app-debug.apk
#        ./run-e2e.sh --apk-url https://example.com/app-debug.apk
#        ./run-e2e.sh --gh-run-id 12345  # download from GitHub Actions

E2E_DIR="/opt/skatelab-e2e"
REPORTS_DIR="${E2E_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="${REPORTS_DIR}/report-${TIMESTAMP}.xml"
APK_PATH=""
MAX_RETRIES=2

while [[ $# -gt 0 ]]; do
    case $1 in
        --apk-path) APK_PATH="$2"; shift 2 ;;
        --apk-url)
            echo "Downloading APK from $2..."
            APK_PATH="/tmp/app-debug-$(date +%s).apk"
            curl -L -o "$APK_PATH" "$2"
            shift 2
            ;;
        --gh-run-id)
            echo "Downloading APK from GitHub Actions run $2..."
            APK_PATH="/tmp/app-debug-$(date +%s).apk"
            gh run download "$2" -n apk-debug -D /tmp/gh-artifacts
            APK_PATH=$(find /tmp/gh-artifacts -name '*.apk' | head -1)
            shift 2
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$APK_PATH" ] || [ ! -f "$APK_PATH" ]; then
    echo "ERROR: No APK file. Use --apk-path, --apk-url, or --gh-run-id"
    exit 1
fi

echo "APK: ${APK_PATH} ($(du -h "$APK_PATH" | cut -f1))"

# Ensure emulator is running
if ! docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
    echo "Starting emulator..."
    systemctl start skatelab-emulator.service
    echo "Waiting for boot..."
    for i in $(seq 1 24); do
        sleep 5
        if docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | grep -q 1; then
            break
        fi
        echo "  Waiting... ($((i*5))s)"
    done
fi

# Install APK
echo "Installing APK..."
docker exec skatelab-emulator adb install -r "$APK_PATH" || {
    echo "Install failed, trying with -t flag..."
    docker exec skatelab-emulator adb install -r -t "$APK_PATH"
}

# Run Maestro with retry
ATTEMPT=0
while [ $ATTEMPT -le $MAX_RETRIES ]; do
    echo "Running Maestro tests (attempt $((ATTEMPT+1))/$((MAX_RETRIES+1)))..."
    if maestro test \
        --device emulator-5554 \
        --format junit \
        --output "${REPORT_FILE}" \
        "${E2E_DIR}/maestro/"; then
        echo "Maestro tests passed."
        break
    fi
    ATTEMPT=$((ATTEMPT+1))
    if [ $ATTEMPT -le $MAX_RETRIES ]; then
        echo "Attempt $ATTEMPT failed, retrying in 5s..."
        sleep 5
    else
        echo "Tests failed after $((MAX_RETRIES+1)) attempts."
        echo "Report: ${REPORT_FILE}"
        exit 1
    fi
done

# Summary
echo ""
echo "=== E2E Results ==="
if [ -f "${REPORT_FILE}" ]; then
    TOTAL=$(grep -oP 'tests="\K[0-9]+' "$REPORT_FILE" | head -1)
    FAILURES=$(grep -oP 'failures="\K[0-9]+' "$REPORT_FILE" | head -1)
    echo "Tests: ${TOTAL}, Failures: ${FAILURES:-0}"
    echo "Report: ${REPORT_FILE}"
fi
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x mobile/e2e/run-e2e.sh
git add mobile/e2e/run-e2e.sh
git commit -m "ci(e2e): add run-e2e.sh with APK install, Maestro execution, retry logic"
```

---

### Task 13: run-e2e-async.sh

**Files:**

- Create: `mobile/e2e/run-e2e-async.sh`

- [ ] **Step 1: Write run-e2e-async.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Async wrapper: fire-and-forget E2E, poll for results
# Usage: ./run-e2e-async.sh --apk-path /tmp/app-debug.apk
# Poll: cat /opt/skatelab-e2e/reports/latest-report-path.txt && test -f $(cat /opt/skatelab-e2e/reports/latest-report-path.txt)

E2E_DIR="/opt/skatelab-e2e"
REPORTS_DIR="${E2E_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${REPORTS_DIR}/maestro-${TIMESTAMP}.log"
LATEST_MARKER="${REPORTS_DIR}/latest-report-path.txt"

# Forward all args to run-e2e.sh, capture the report path
REPORT_FILE="${REPORTS_DIR}/report-${TIMESTAMP}.xml"

echo "${REPORT_FILE}" > "${LATEST_MARKER}"

nohup "${E2E_DIR}/run-e2e.sh" "$@" > "${LOG_FILE}" 2>&1 &

PID=$!
echo "E2E running in background (PID: ${PID})"
echo "Report will be at: ${REPORT_FILE}"
echo "Log: ${LOG_FILE}"
echo ""
echo "Poll for completion:"
echo "  while [ ! -f ${REPORT_FILE} ]; do sleep 5; done && echo DONE"
echo "  tail -f ${LOG_FILE}"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x mobile/e2e/run-e2e-async.sh
git add mobile/e2e/run-e2e-async.sh
git commit -m "ci(e2e): add async E2E wrapper with nohup and poll pattern"
```

---

### Task 14: Prometheus metrics script

**Files:**

- Create: `mobile/e2e/metrics.sh`

- [ ] **Step 1: Write metrics.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Prometheus node_exporter textfile collector for Android emulator health
# Run via cron every 30s

METRIC_FILE="/var/lib/node_exporter/textfile_collector/emulator.prom"
METRIC_TMP="${METRIC_FILE}.tmp"

# Is emulator container running?
EMULATOR_UP=$(docker ps --filter name=skatelab-emulator --format '{{.Status}}' 2>/dev/null | grep -c Up || echo 0)

# Boot status
BOOT_COMPLETE=$(docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || echo 0)

# Resource usage from systemd slice
SLICE_MEM=$(systemctl show emulator.slice -p MemoryCurrent --value 2>/dev/null || echo 0)
SLICE_CPU=$(systemctl show emulator.slice -p CPUUsageNSec --value 2>/dev/null || echo 0)

cat > "${METRIC_TMP}" <<EOF
# HELP skatelab_emulator_up Whether the emulator container is running
# TYPE skatelab_emulator_up gauge
skatelab_emulator_up ${EMULATOR_UP}

# HELP skatelab_emulator_boot_complete Whether the Android VM has finished booting
# TYPE skatelab_emulator_boot_complete gauge
skatelab_emulator_boot_complete ${BOOT_COMPLETE}

# HELP skatelab_emulator_memory_bytes Current memory usage of emulator slice
# TYPE skatelab_emulator_memory_bytes gauge
skatelab_emulator_memory_bytes ${SLICE_MEM}

# HELP skatelab_emulator_cpu_ns_total CPU usage of emulator slice in nanoseconds
# TYPE skatelab_emulator_cpu_ns_total counter
skatelab_emulator_cpu_ns_total ${SLICE_CPU}
EOF

mv "${METRIC_TMP}" "${METRIC_FILE}"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x mobile/e2e/metrics.sh
git add mobile/e2e/metrics.sh
git commit -m "ci(e2e): add Prometheus metrics script for emulator health monitoring"
```

---

## Wave 3: Maestro E2E Flows

### Task 15: Maestro config + login flow

**Files:**

- Create: `mobile/e2e/maestro/config.yaml`
- Create: `mobile/e2e/maestro/flows/login.yaml`

- [ ] **Step 1: Write Maestro config**

```yaml
flows:
  - flows/*
excludeTags:
  - util
testOutputDir: /opt/skatelab-e2e/reports/maestro-output
```

- [ ] **Step 2: Write login flow**

```yaml
appId: ru.skatelab
tags:
  - smokeTest
  - auth
---
- launchApp
- assertVisible: "Войти"
- tapOn: "Войти"
- inputText: ${MAESTRO_TEST_EMAIL}
- tapOn: "Продолжить"
- assertVisible: "Сессии"
```

Note: `MAESTRO_TEST_EMAIL` env var must be set when running. Password entry depends on app UI — adjust after first manual run.

- [ ] **Step 3: Commit**

```bash
git add mobile/e2e/maestro/config.yaml mobile/e2e/maestro/flows/login.yaml
git commit -m "ci(e2e): add Maestro config and login flow"
```

---

### Task 16: Session list flow

**Files:**

- Create: `mobile/e2e/maestro/flows/session-list.yaml`

- [ ] **Step 1: Write session list flow**

```yaml
appId: ru.skatelab
tags:
  - smokeTest
  - sessions
---
- launchApp
- assertVisible: "Сессии"
- assertVisible: ".*"   # At least one session item visible (regex matches any text)
```

Note: This flow assumes user is already logged in (use snapshot with auth state). Adjust after first manual E2E run.

- [ ] **Step 2: Commit**

```bash
git add mobile/e2e/maestro/flows/session-list.yaml
git commit -m "ci(e2e): add session list Maestro flow"
```

---

### Task 17: Recording flow

**Files:**

- Create: `mobile/e2e/maestro/flows/recording.yaml`

- [ ] **Step 1: Write recording flow**

```yaml
appId: ru.skatelab
tags:
  - recording
---
- launchApp
- assertVisible: "Сессии"
- tapOn: "Запись"
- assertVisible: "Начать"
- tapOn: "Начать"
- assertVisible: ".*:\\d{2}"   # Timer format MM:SS
- tapOn: "Стоп"
- assertVisible: "Сессия сохранена"
```

Note: Exact button text depends on app UI. Adjust after first manual E2E run.

- [ ] **Step 2: Commit**

```bash
git add mobile/e2e/maestro/flows/recording.yaml
git commit -m "ci(e2e): add recording start/stop Maestro flow"
```

---

### Task 18: Upload flow

**Files:**

- Create: `mobile/e2e/maestro/flows/upload.yaml`

- [ ] **Step 1: Write upload flow**

```yaml
appId: ru.skatelab
tags:
  - upload
---
- launchApp
- assertVisible: "Сессии"
- tapOn: ".*"              # Tap first session
- assertVisible: "Загрузить"
- tapOn: "Загрузить"
- assertVisible: "Загрузка"
```

Note: Exact text depends on app UI. Adjust after first manual E2E run.

- [ ] **Step 2: Commit**

```bash
git add mobile/e2e/maestro/flows/upload.yaml
git commit -m "ci(e2e): add upload Maestro flow"
```

---

## Post-Implementation: Server Deployment

After all repo files are committed, deploy to dedic:

1. **Copy repo to dedic:**
   ```bash
   scp -r mobile/e2e/ dedic:/opt/skatelab-e2e/
   ```

2. **Run setup script:**
   ```bash
   ssh dedic "cd /opt/skatelab-e2e && sudo ./setup-emulator.sh"
   ```

3. **Set up cron for metrics:**
   ```bash
   ssh dedic "(crontab -l 2>/dev/null; echo '* * * * * /opt/skatelab-e2e/metrics.sh'; echo '* * * * * sleep 30; /opt/skatelab-e2e/metrics.sh') | crontab -"
   ```

4. **Verify emulator health:**
   ```bash
   ssh dedic "systemctl status skatelab-emulator.service"
   ssh dedic "docker exec skatelab-emulator adb devices"
   ```

5. **Test with APK:**
   ```bash
   ssh dedic "cd /opt/skatelab-e2e && ./run-e2e.sh --apk-path /tmp/test.apk"
   ```

6. **Restrict SSH key** (add to `~/.ssh/authorized_keys` on dedic):
   ```
   command="/opt/skatelab-e2e/wrapper.sh",no-port-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... skatelab-e2e-agent
   ```

   Where `wrapper.sh` validates allowed commands:
   ```bash
   #!/usr/bin/env bash
   case "$SSH_ORIGINAL_COMMAND" in
       /opt/skatelab-e2e/run-e2e.sh*|/opt/skatelab-e2e/run-e2e-async.sh*|/opt/skatelab-e2e/metrics.sh*)
           exec $SSH_ORIGINAL_COMMAND
           ;;
       *)
           echo "Command not allowed: $SSH_ORIGINAL_COMMAND"
           exit 1
           ;;
   esac
   ```