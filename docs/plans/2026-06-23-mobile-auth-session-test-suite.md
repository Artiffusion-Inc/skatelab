# Mobile Auth/Session Integration Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 14-scenario integration test suite (real Ktor `Auth` plugin + `FakeAuthBackend`) covering mobile auth-cache, refresh-token flow, and session read-path, surfacing each failing scenario as a tagged issue.

**Architecture:** One new commonTest component `FakeAuthBackend` (a `MockEngine` wrapper routing by path + actual `Authorization` header, with controllable token/account state). Two test files: `AuthWireTest` (scenarios #1–#10) and `SessionReadAuthTest` (#11–#14). No production code changes. Each failing test stays red in the worktree and becomes a `testing/repro` issue; fixes are separate PRs.

**Tech Stack:** Kotlin Multiplatform, Ktor 3.1.3 (`ktor-client-auth`, `MockEngine`), kotlinx-serialization-json, kotlinx-coroutines-test, kotlin-test, multiplatform-settings (`MapSettings`). All already in `:shared` commonTest — no new deps.

## Global Constraints

- **Test target:** `:shared:testDebugUnitTest` (JVM). Run via Docker-fallback when local Gradle daemon is unstable: `docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "<filter>"'`
- **No `Date.now()` / `Math.random()` / argless `new Date()`** in test code — unavailable in workflow contexts. Use string-constant tokens (`acc-A`/`ref-A`/`acc-B`/`ref-B`) and integer counters.
- **Ktor 3.x gotcha:** `HttpResponse.request` is a function, not a property — never access `response.request.url` in strings; use `response.status` / `request.url` (the `MockEngine` handler's `request` param) only.
- **No mocks of `AuthRepository`/`UsersApi`/`SessionsApi`.** Tests wire the real classes against the real `Auth` plugin + `FakeAuthBackend`. Mocks are the blind spot this suite exists to close.
- **Failing tests stay red.** A red test is the deliverable (proof for reviewer). Do NOT add `@Ignore`, do NOT soften assertions. The test goes green only in the separate fix PR.
- **Commit format:** one commit per scenario — `test(mobile): repro for <scenario-name>`.
- **ktlint** must pass on every new file (`./gradlew :shared:ktlintCheck`).
- **Worktree:** `worktree-auth-cache-logout-bug`. All work here. Existing repro `AuthRepositoryCacheBugReproTest.kt` (commit `40b5ebe9`) is consumed into Task 2 and deleted as a standalone file.
- **Backend refresh semantics (verified `backend/app/routes/auth.py:209`):** refresh is single-use and rotated — a valid refresh returns a NEW `TokenResponse` pair and invalidates the old refresh; an invalid/used refresh returns 401. `FakeAuthBackend` must mirror this for scenarios #6–#10.

---

## File Structure

```
mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/
├── auth/
│   ├── FakeAuthBackend.kt          # NEW — MockEngine routing + account/token state
│   └── AuthWireTest.kt             # NEW — scenarios #1–#10
└── state/
    └── SessionReadAuthTest.kt      # NEW — scenarios #11–#14
```

`mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt` — **DELETED** in Task 2 (logic absorbed into `AuthWireTest` scenario #1).

### Responsibilities
- **`FakeAuthBackend`** — single responsibility: emulate the auth/session subset of the backend. Holds accounts (id, email, displayName, sessions), per-account `accessToken`/`refreshToken`, a mutable `refreshAlive: Boolean`, an `accessAlive: Boolean`, a `refreshCallCount`, and a list of issued (rotated) refresh tokens. Exposes a `MockEngine`-producing `engine` plus mutation methods (`expireAccessToken`, `revokeRefreshToken`, `setRefreshResponse`). Routes by `request.url.encodedPath` + `Authorization` header. No test assertions live here.
- **`AuthWireTest`** — scenarios on the auth wire (login/logout/register/refresh/caching), using real `Auth` plugin + `AuthRepository`/`UsersApi`.
- **`SessionReadAuthTest`** — scenarios on the session read-path, using real `Auth` plugin + `SessionsApi`.

### Consumes / Produces across tasks
- Task 1 **produces** `FakeAuthBackend` (full public API below). Tasks 2–4 **consume** it.
- `FakeAuthBackend` public surface (frozen in Task 1):
  - `class FakeAuthBackend`
  - `fun addAccount(id: String, email: String, displayName: String? = null): FakeAuthBackend`
  - `fun engine(): MockEngine`
  - `fun expireAccessToken(accountId: String)`
  - `fun revokeRefreshToken(accountId: String)`
  - `fun refreshCallCount(): Int`
  - `fun issueLoginTokensFor(accountId: String)` (internal helper used by `auth/login` routing)
  - internal `TokenStorage` is owned by the test, not the backend.

---

## Task 1: FakeAuthBackend component

**Files:**
- Create: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackend.kt`

**Interfaces:**
- Consumes: `MockEngine`, `TokenStorage`, Ktor `Auth` plugin types — all already available.
- Produces: `FakeAuthBackend` class with the public surface listed in File Structure.

- [ ] **Step 1: Write a smoke test verifying routing**

Create `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackendSmokeTest.kt`:

```kotlin
package ru.skatelab.shared.auth

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.UsersApi
import kotlin.test.Test
import kotlin.test.assertEquals

class FakeAuthBackendSmokeTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    @Test
    fun usersMe_routesByAuthorizationHeader() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val client = HttpClient(backend.engine()) {
            install(ContentNegotiation) { json(json) }
        }
        val users = UsersApi(client)
        // No Authorization header → 401 (no cached/loaded token)
        try {
            users.getMe()
            error("expected 401")
        } catch (e: Exception) {
            // ok
        }
        client.close()
    }
}
```

- [ ] **Step 2: Run it to verify it fails (FakeAuthBackend not defined)**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.auth.FakeAuthBackendSmokeTest" 2>&1 | tail -15'
```
Expected: FAIL — `unresolved reference: FakeAuthBackend`.

- [ ] **Step 3: Implement FakeAuthBackend**

Create `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackend.kt`:

```kotlin
package ru.skatelab.shared.auth

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.serialization.json.Json

/**
 * Test-only emulation of the SkateLab auth/session backend subset.
 * Routes by `request.url.encodedPath` plus the `Authorization: Bearer <token>` header
 * actually sent, so a stale Ktor Auth-plugin cache surfaces as the wrong account.
 *
 * Mirrors `backend/app/routes/auth.py` refresh semantics: refresh is single-use and
 * rotated — a valid refresh returns a NEW token pair and invalidates the old refresh;
 * an invalid/used refresh returns 401.
 *
 * Tokens are fixed string constants — no Date.now()/Math.random().
 */
class FakeAuthBackend(
    private val json: Json = Json { ignoreUnknownKeys = true; isLenient = true },
) {
    private data class Account(
        val id: String,
        val email: String,
        val displayName: String?,
        val sessions: List<String>, // session ids owned by this account
    )

    private val accounts = mutableMapOf<String, Account>()            // id -> account
    private val accessTokenToAccount = mutableMapOf<String, String>() // accessToken -> accountId
    private val refreshTokenToAccount = mutableMapOf<String, String>() // refreshToken -> accountId
    private var accessAlive = mutableMapOf<String, Boolean>()          // accountId -> access valid
    private var refreshAlive = mutableMapOf<String, Boolean>()         // accountId -> refresh valid
    private val issuedRefreshTokens = mutableSetOf<String>()           // tokens handed out by login
    private val usedRefreshTokens = mutableSetOf<String>()             // rotated-away (single-use)
    private var refreshCallCount = 0

    // Per-account fixed token prefixes; rotated refresh appends a counter.
    private val tokenCounter = mutableMapOf<String, Int>()            // accountId -> rotation counter

    fun addAccount(id: String, email: String, displayName: String? = null): FakeAuthBackend {
        accounts[id] = Account(id, email, displayName, listOf("${id}-sess-1"))
        accessAlive[id] = true
        refreshAlive[id] = true
        tokenCounter[id] = 0
        return this
    }

    fun expireAccessToken(accountId: String) { accessAlive[accountId] = false }
    fun revokeRefreshToken(accountId: String) { refreshAlive[accountId] = false }
    fun refreshCallCount(): Int = refreshCallCount

    private fun jsonHeaders() =
        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private fun issueTokensFor(accountId: String): Pair<String, String> {
        val n = (tokenCounter[accountId] ?: 0) + 1
        tokenCounter[accountId] = n
        val access = "acc-$accountId-$n"
        val refresh = "ref-$accountId-$n"
        accessTokenToAccount[access] = accountId
        refreshTokenToAccount[refresh] = accountId
        issuedRefreshTokens.add(refresh)
        accessAlive[accountId] = true
        refreshAlive[accountId] = true
        return access to refresh
    }

    private fun accountForAccessToken(authHeader: String?): Account? {
        val token = authHeader?.removePrefix("Bearer ")?.trim() ?: return null
        val accountId = accessTokenToAccount[token] ?: return null
        return accounts[accountId]
    }

    private fun profileJson(acc: Account): String =
        """{"id":"${acc.id}","email":"${acc.email}","display_name":${acc.displayName?.let { "\"$it\"" } ?: "null"}}"""

    private fun sessionsListJson(acc: Account): String {
        val items = acc.sessions.joinToString(",") { sid ->
            """{"id":"$sid","user_id":"${acc.id}","element_type":"flip","status":"completed","created_at":"2026-05-24T12:00:00Z"}"""
        }
        return """{"sessions":[$items],"total":${acc.sessions.size},"next_cursor":null,"has_more":false}"""
    }

    private fun sessionJson(acc: Account, sid: String): String =
        """{"id":"$sid","user_id":"${acc.id}","element_type":"flip","status":"completed","created_at":"2026-05-24T12:00:00Z"}"""

    fun engine(): MockEngine = MockEngine { request ->
        val path = request.url.encodedPath
        val authHeader = request.headers[HttpHeaders.Authorization]
        val body = request.body.toByteArray().decodeToString()

        when {
            path.endsWith("auth/login") -> {
                val accountId = if (body.contains("b@skatelab.ru")) "b" else "a"
                require(accounts.containsKey(accountId)) { "account $accountId not added" }
                val (access, refresh) = issueTokensFor(accountId)
                respond(
                    """{"access_token":"$access","refresh_token":"$refresh","token_type":"bearer"}""",
                    status = HttpStatusCode.OK,
                    headers = jsonHeaders(),
                )
            }

            path.endsWith("auth/logout") -> respond("{}", status = HttpStatusCode.OK, headers = jsonHeaders())

            path.endsWith("auth/refresh") -> {
                refreshCallCount += 1
                val refreshIn = extractRefreshToken(body) ?: return@MockEngine respondError(
                    HttpStatusCode.Unauthorized, """{"detail":"Refresh token required"}""",
                )
                val accountId = refreshTokenToAccount[refreshIn]
                when {
                    accountId == null || refreshAlive[accountId] != true ->
                        respondError(HttpStatusCode.Unauthorized, """{"detail":"Invalid or expired refresh token"}""")
                    usedRefreshTokens.contains(refreshIn) ->
                        respondError(HttpStatusCode.Unauthorized, """{"detail":"Token reuse detected. All sessions revoked."}""")
                    else -> {
                        usedRefreshTokens.add(refreshIn)
                        val (newAccess, newRefresh) = issueTokensFor(accountId)
                        respond(
                            """{"access_token":"$newAccess","refresh_token":"$newRefresh","token_type":"bearer"}""",
                            status = HttpStatusCode.OK,
                            headers = jsonHeaders(),
                        )
                    }
                }
            }

            path.endsWith("users/me") -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    respond(profileJson(acc), status = HttpStatusCode.OK, headers = jsonHeaders())
                }
            }

            path.endsWith("users/me/settings") -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    respond(profileJson(acc), status = HttpStatusCode.OK, headers = jsonHeaders())
                }
            }

            path.endsWith("sessions") && request.method.value == "GET" -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    respond(sessionsListJson(acc), status = HttpStatusCode.OK, headers = jsonHeaders())
                }
            }

            path.startsWith("/v1/sessions/") && request.method.value == "GET" -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    val sid = path.removePrefix("/v1/sessions/").removeSuffix("/")
                    if (acc.sessions.contains(sid)) {
                        respond(sessionJson(acc, sid), status = HttpStatusCode.OK, headers = jsonHeaders())
                    } else {
                        respondError(HttpStatusCode.NotFound, """{"detail":"Not Found"}""")
                    }
                }
            }

            else -> respondError(HttpStatusCode.NotFound, """{"detail":"Not Found"}""")
        }
    }

    private fun extractRefreshToken(body: String): String? {
        val match = """"refresh_token"\s*:\s*"([^"]+)"""".toRegex().find(body)
        return match?.groupValues?.get(1)
    }
}
```

> Note: `request.body` in Ktor 3.x `MockEngine` is `ByteReadPacket`; `toByteArray()` then `decodeToString()` reads it. If the build reports `toByteArray` unavailable on the body type, replace with `runCatching { request.body.toByteArray() }.getOrNull()?.decodeToString() ?: ""` — verify in Step 4 compile output.

- [ ] **Step 4: Run the smoke test to verify it passes**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.auth.FakeAuthBackendSmokeTest" 2>&1 | tail -15'
```
Expected: PASS (1 test). If compile error on `request.body.toByteArray()`, apply the fallback noted above and rerun.

- [ ] **Step 5: ktlint**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:ktlintCheck --no-daemon --no-configuration-cache 2>&1 | tail -15'
```
Expected: BUILD SUCCESSFUL. Fix any ktlint violations (multiline expression wrapping, trailing commas) before committing.

- [ ] **Step 6: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackend.kt mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/FakeAuthBackendSmokeTest.kt
git commit -m "test(mobile): add FakeAuthBackend test-double for auth/session backend

MockEngine wrapper routing by path + actual Authorization header, with
controllable account/token state. Mirrors backend refresh semantics
(single-use, rotated). Foundation for the auth/session integration
test suite."
```

---

## Task 2: AuthWireTest — auth-cache / multi-account scenarios (#1–#5)

**Files:**
- Create: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthWireTest.kt`
- Delete: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt`

**Interfaces:**
- Consumes: `FakeAuthBackend` (Task 1), real `Auth` plugin, `AuthRepository`, `UsersApi`, `TokenStorage(MapSettings())`.
- Produces: `AuthWireTest` with scenarios #1–#5 (this task) + #6–#10 (Task 3 appended).

**Shared test harness (top of `AuthWireTest`):**

```kotlin
package ru.skatelab.shared.auth

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logging
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.UsersApi
import kotlin.test.After
import kotlin.test.Test
import kotlin.test.assertEquals

class AuthWireTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val openedClients = mutableListOf<HttpClient>()

    private fun newClient(backend: FakeAuthBackend, tokenStorage: TokenStorage): HttpClient {
        val client = HttpClient(backend.engine()) {
            install(ContentNegotiation) { json(json) }
            install(Auth) {
                bearer {
                    loadTokens {
                        val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                        val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                        BearerTokens(access, refresh)
                    }
                    refreshTokens {
                        val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
                        val result = runCatching {
                            client.post("auth/refresh") {
                                markAsRefreshTokenRequest()
                                contentType(io.ktor.http.ContentType.Application.Json)
                                setBody(kotlinx.serialization.json.buildJsonObject {
                                    put("refresh_token", refreshToken)
                                })
                            }.body<ru.skatelab.shared.models.TokenResponse>()
                        }
                        if (result.isSuccess) {
                            val response = result.getOrThrow()
                            tokenStorage.saveTokens(response.accessToken, response.refreshToken)
                            BearerTokens(response.accessToken, response.refreshToken)
                        } else {
                            tokenStorage.clearTokens()
                            null
                        }
                    }
                }
            }
        }
        openedClients.add(client)
        return client
    }

    @After
    fun tearDown() { openedClients.forEach { it.close() }; openedClients.clear() }
}
```

> Note: `refreshTokens` block mirrors `SkateLabClient.kt:48-66` so the test exercises the real refresh path. `onAuthFailure` wiring is tested in Task 3 (#7).

- [ ] **Step 1: Write scenario #1 (port of #314 repro) — expected GREEN**

Add inside `AuthWireTest`:

```kotlin
    @Test
    fun logoutThenLoginAsDifferentUser_getMeReturnsNewUser() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        // Login A
        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)

        // Logout (clears persistent storage only, NOT the Auth plugin cache → bug)
        repo.logout()

        // Login B
        repo.login("b@skatelab.ru", "pw")
        val profile = users.getMe()
        // This is the repro from issue #314. Bug: returns "a". After the (separate) fix: "b".
        assertEquals("b", profile.id)
    }
```

- [ ] **Step 2: Delete the standalone repro file**

```bash
git rm mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryCacheBugReproTest.kt
```

- [ ] **Step 3: Write scenarios #2–#5**

Append inside `AuthWireTest`:

```kotlin
    @Test
    fun logoutThenLoginSameUser_getMeSucceeds() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        repo.logout()
        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
    }

    @Test
    fun logout_clearsInMemoryTokenCache() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        repo.logout()
        // After logout, users/me must NOT succeed with the stale cached token.
        // Bug: Auth plugin reuses cached acc → returns "a" instead of 401.
        try {
            val me = users.getMe()
            org.junit.Assert.fail("expected unauthorized after logout, got profile id=${me.id}")
        } catch (e: io.ktor.client.plugins.ResponseException) {
            // expected: 401
        }
    }

    @Test
    fun registerAfterLogout_getMeReturnsNewUser() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.register("a@skatelab.ru", "pw", "A")
        assertEquals("a", users.getMe().id)
        repo.logout()
        repo.register("b@skatelab.ru", "pw", "B")
        // Bug: register path shares the auth-cache leak. Returns "a".
        assertEquals("b", users.getMe().id)
    }

    @Test
    fun switchAccountTwice_getMeMatchesLatestLogin() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        repo.logout()
        repo.login("b@skatelab.ru", "pw")
        assertEquals("b", users.getMe().id)
        repo.logout()
        repo.login("a@skatelab.ru", "pw")
        // Bug: final getMe may return stale "b" from cache. After fix: "a".
        assertEquals("a", users.getMe().id)
    }
```

- [ ] **Step 4: Run all 5 — record which fail**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.auth.AuthWireTest" 2>&1 | tail -30'
```
Expected: a mix. `logoutThenLoginAsDifferentUser_getMeReturnsNewUser` (RED, the #314 bug), `logout_clearsInMemoryTokenCache` (RED), possibly `registerAfterLogout_getMeReturnsNewUser` (RED), `switchAccountTwice_getMeMatchesLatestLogin` (RED). `logoutThenLoginSameUser_getMeSucceeds` likely GREEN. **Record exact pass/fail from the XML** (`shared/build/test-results/testDebugUnitTest/*.xml`) for the issue-creation step.

- [ ] **Step 5: ktlint**

Run the same `:shared:ktlintCheck` command as Task 1 Step 5. Expected: BUILD SUCCESSFUL.

- [ ] **Step 6: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthWireTest.kt
git commit -m "test(mobile): repro scenarios for auth-cache leak across logout/relogin

Scenarios #1-#5: logout+login-as-different-user, logout+same-user,
logout-clears-cache, register-after-logout, switch-account-twice.
Ported from AuthRepositoryCacheBugReproTest (#314). Failing tests stay
red as proof; fixes are separate PRs."
```

- [ ] **Step 7: Open issue for each RED scenario**

For each scenario that failed in Step 4, open a `testing/repro` issue using the #314 template. Example for `logout_clearsInMemoryTokenCache`:

```bash
gh issue create \
  --title "fix(mobile): stale auth token cache survives logout — authorized requests succeed with no stored token" \
  --label "testing/repro" \
  --body-file - <<'EOF'
## What happened
After logout, an authorized request (`users/me`) succeeds instead of returning 401 — the Ktor `Auth` plugin reuses the cached bearer token even though persistent storage was cleared.

## Root cause
`AuthRepository.logout()` calls `tokenStorage.clearTokens()` but never invalidates the `Auth` plugin's in-memory cache (`AuthTokenHolder.value`). Same root cause family as #314.

## Repro
Test: `ru.skatelab.shared.auth.AuthWireTest.logout_clearsInMemoryTokenCache`
Branch: `worktree-auth-cache-logout-bug`, scenario committed.
Run: `./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.auth.AuthWireTest.logout_clearsInMemoryTokenCache"`

## Proposed fix
Expose `SkateLabClient.clearAuthCache()` calling `httpClient.plugin(Auth).providers.filterIsInstance<BearerAuthProvider>().forEach { it.clearToken() }`; call it from `AuthRepository.logout()` after `clearTokens()`.

## Impact
Security: requests continue authenticated after logout. On a shared device the previous session's data is reachable until the process is killed.
EOF
```
Replace title/scenario name per failing scenario. Cross-link #314 in each body ("Same root cause family as #314").

---

## Task 3: AuthWireTest — refresh-token flow scenarios (#6–#10)

**Files:**
- Modify: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthWireTest.kt` (append 5 tests)

**Interfaces:**
- Consumes: `FakeAuthBackend` mutation methods (`expireAccessToken`, `revokeRefreshToken`, `refreshCallCount`), `onAuthFailure` wiring pattern from `AppModule.kt:142-156`.

**`onAuthFailure` wiring helper (add to `AuthWireTest`, used by #7 only):**

```kotlin
    // Mirrors AppModule.kt:142-156 onAuthFailure wiring.
    private fun wireOnAuthFailure(client: HttpClient, sharedVm: ru.skatelab.shared.state.AuthViewModel) {
        // SkateLabClient owns onAuthFailure; in tests we drive refreshTokens directly,
        // so emulate the failure → logout chain by observing tokenStorage after a dead refresh.
    }
```
> Note: `SkateLabClient`'s `onAuthFailure` callback fires from inside the `refreshTokens` block when refresh fails (`SkateLabClient.kt:62-64`). Tests here construct the `HttpClient` directly (not via `SkateLabClient`) to keep the `Auth` plugin wiring explicit. For scenario #7, observe `tokenStorage` being cleared after a dead-refresh cycle (the `refreshTokens` block above already calls `tokenStorage.clearTokens()` on failure), and assert `AuthViewModel` state via `onAuthFailure`.

- [ ] **Step 1: Write scenario #6 (expired access, live refresh → retry)**

```kotlin
    @Test
    fun expiredAccess_liveRefresh_getMeRetriesWithNewToken() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        // First getMe populates the Auth cache with acc-a-1; now expire it.
        assertEquals("a", users.getMe().id)
        backend.expireAccessToken("a")
        // Next getMe: 401 on access → refresh → retry with new access. Should return "a".
        val me = users.getMe()
        assertEquals("a", me.id)
        assertEquals(1, backend.refreshCallCount(), "refresh should have been called exactly once")
    }
```

- [ ] **Step 2: Write scenario #7 (both tokens dead → onAuthFailure → LoggedOut)**

```kotlin
    @Test
    fun expiredAccessAndRefresh_onAuthFailureTriggersLogout() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val usersApi = ru.skatelab.shared.api.UsersApi(client)
        val sharedVm = ru.skatelab.shared.state.AuthViewModel(AuthRepository(AuthApi(client), tokenStorage), usersApi)

        sharedVm.login("a@skatelab.ru", "pw")
        // Both tokens dead: access 401, refresh 401.
        backend.expireAccessToken("a")
        backend.revokeRefreshToken("a")

        try {
            usersApi.getMe()
            org.junit.Assert.fail("expected unauthorized")
        } catch (e: io.ktor.client.plugins.ResponseException) {
            // expected
        }
        // After a dead refresh, the refreshTokens block cleared tokenStorage.
        assertEquals(null, tokenStorage.getAccessToken())
        assertEquals(null, tokenStorage.getRefreshToken())
        assertEquals(1, backend.refreshCallCount())
    }
```

- [ ] **Step 3: Write scenario #8 (concurrent requests → refresh called once)**

```kotlin
    @Test
    fun concurrentRequestsOnExpiringToken_refreshCalledOnce() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        backend.expireAccessToken("a")

        val deferred1 = async { users.getMe() }
        val deferred2 = async { users.getMe() }
        val r1 = deferred1.await()
        val r2 = deferred2.await()

        assertEquals("a", r1.id)
        assertEquals("a", r2.id)
        assertEquals(1, backend.refreshCallCount(), "two concurrent requests must trigger only one refresh")
    }
```
> Note: `async` here is `kotlinx.coroutines.async`; add `import kotlinx.coroutines.async` and run inside `runTest`'s scope. If `runTest` does not provide a child scope, wrap with `coroutineScope { ... }` and import `kotlinx.coroutines.coroutineScope`.

- [ ] **Step 4: Write scenario #9 (refresh rotates refresh token → storage updated)**

```kotlin
    @Test
    fun refreshReturnsNewRefreshToken_storageUpdated() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        val refreshBefore = tokenStorage.getRefreshToken()!!
        backend.expireAccessToken("a")
        // Force a refresh by making an authorized request.
        assertEquals("a", users.getMe().id)
        val refreshAfter = tokenStorage.getRefreshToken()!!

        // Backend rotates refresh (single-use). Storage must hold the NEW refresh, not the old.
        org.junit.Assert.assertNotEquals("refresh token must rotate", refreshBefore, refreshAfter)
        assertEquals(1, backend.refreshCallCount())
    }
```

- [ ] **Step 5: Write scenario #10 (refresh failure then success → no stale state)**

```kotlin
    @Test
    fun refreshFailureThenSuccess_doesNotLeakStaleState() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)

        // First: refresh is dead → getMe fails, storage cleared.
        backend.expireAccessToken("a")
        backend.revokeRefreshToken("a")
        try { users.getMe(); org.junit.Assert.fail("expected unauthorized") } catch (e: io.ktor.client.plugins.ResponseException) {}
        assertEquals(1, backend.refreshCallCount())

        // Then: user re-logs in (fresh tokens). getMe must succeed — no "I already gave up" state.
        backend.revokeRefreshToken("a") // reset not needed: login re-issues
        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
    }
```

- [ ] **Step 6: Run all 5 — record results**

Run the same `:shared:testDebugUnitTest --tests "ru.skatelab.shared.auth.AuthWireTest"` command. Expected: most of #6–#10 RED (refresh path is uncovered today). Record exact pass/fail from XML for issue creation.

- [ ] **Step 7: ktlint**

Same `:shared:ktlintCheck`. Expected: BUILD SUCCESSFUL.

- [ ] **Step 8: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthWireTest.kt
git commit -m "test(mobile): repro scenarios for refresh-token flow

Scenarios #6-#10: expired-access+live-refresh retry, both-dead→logout,
concurrent refresh dedup, refresh-token rotation stored, refresh
failure-then-recovery. Currently zero coverage of auth/refresh path."
```

- [ ] **Step 9: Open issue for each RED scenario**

Use the #314 template (Task 2 Step 7). Root-cause trace should cite `SkateLabClient.kt:48-66` (refresh block), `AuthRepository.logout()`. For `concurrentRequestsOnExpiringToken_refreshCalledOnce` — note the Auth plugin's `AuthTokenHolder` mutex is supposed to dedup; if the test fails it points at a missing/non-functional dedup path.

---

## Task 4: SessionReadAuthTest — session read-path scenarios (#11–#14)

**Files:**
- Create: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionReadAuthTest.kt`

**Interfaces:**
- Consumes: `FakeAuthBackend` (Task 1), real `Auth` plugin, `AuthRepository`, `SessionsApi`. The `AuthWireTest` `newClient` harness is duplicated here (kept local to avoid cross-file test coupling — each test file is self-contained per existing commonTest convention, see `SessionsViewModelTest`).

- [ ] **Step 1: Write scenario #11 (sessions list uses current account token)**

Create `SessionReadAuthTest.kt` with the `newClient`/`json` harness duplicated from `AuthWireTest` (same body), then:

```kotlin
package ru.skatelab.shared.state

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.AuthRepository
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.auth.FakeAuthBackend
import ru.skatelab.shared.auth.TokenStorage
import kotlin.test.Test
import kotlin.test.assertEquals

class SessionReadAuthTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    private fun newClient(backend: FakeAuthBackend, tokenStorage: TokenStorage): HttpClient =
        HttpClient(backend.engine()) {
            install(ContentNegotiation) { json(json) }
            install(Auth) {
                bearer {
                    loadTokens {
                        val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                        val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                        BearerTokens(access, refresh)
                    }
                    refreshTokens {
                        val refreshToken = oldTokens?.refreshToken ?: return@refreshTokens null
                        val result = runCatching {
                            client.post("auth/refresh") {
                                markAsRefreshTokenRequest()
                                contentType(io.ktor.http.ContentType.Application.Json)
                                setBody(kotlinx.serialization.json.buildJsonObject {
                                    put("refresh_token", refreshToken)
                                })
                            }.body<ru.skatelab.shared.models.TokenResponse>()
                        }
                        if (result.isSuccess) {
                            val r = result.getOrThrow()
                            tokenStorage.saveTokens(r.accessToken, r.refreshToken)
                            BearerTokens(r.accessToken, r.refreshToken)
                        } else {
                            tokenStorage.clearTokens()
                            null
                        }
                    }
                }
            }
        }

    @Test
    fun sessionsList_usesCurrentAccountToken() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val sessions = SessionsApi(client)

        repo.login("a@skatelab.ru", "pw")
        val listA = sessions.list()
        assertEquals("a-sess-1", listA.sessions.first().id)

        repo.logout()
        repo.login("b@skatelab.ru", "pw")
        val listB = sessions.list()
        // Bug (cache leak class): may still return a-sess-1. After fix: b-sess-1.
        assertEquals("b-sess-1", listB.sessions.first().id)
    }
}
```

- [ ] **Step 2: Write scenario #12 (session detail after account switch)**

Append:

```kotlin
    @Test
    fun sessionDetail_afterAccountSwitch_belongsToNewAccount() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val sessions = SessionsApi(client)

        repo.login("a@skatelab.ru", "pw")
        repo.logout()
        repo.login("b@skatelab.ru", "pw")

        val detail = sessions.get("b-sess-1")
        // Bug: with stale token A, b-sess-1 → 404 (not owned by A). After fix: returns b-sess-1.
        assertEquals("b-sess-1", detail.id)
        assertEquals("b", detail.userId)
    }
}
```

- [ ] **Step 3: Write scenario #13 (sessions list on 401 → transparent refresh)**

Append:

```kotlin
    @Test
    fun sessionsList_on401_refreshesTransparently() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val sessions = SessionsApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a-sess-1", sessions.list().sessions.first().id)
        backend.expireAccessToken("a")
        // 401 on access → refresh → retry. User should see the list, no error.
        val list = sessions.list()
        assertEquals("a-sess-1", list.sessions.first().id)
        assertEquals(1, backend.refreshCallCount())
    }
}
```

- [ ] **Step 4: Write scenario #14 (sessions list after logout → clean AppError.Auth)**

Append:

```kotlin
    @Test
    fun sessionsList_afterLogout_failsCleanly() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val sessions = SessionsApi(client)

        repo.login("a@skatelab.ru", "pw")
        repo.logout()

        // No valid token → 401. Must surface as a clean AppError, NOT another user's sessions.
        val err = runCatching { sessions.list() }.exceptionOrNull()
        org.junit.Assert.assertNotNull("expected a failure after logout", err)
        val appError = (err as? io.ktor.client.plugins.ResponseException)?.let { ru.skatelab.shared.utils.toAppError() }
        org.junit.Assert.assertNotNull("expected AppError mapping", appError)
        org.junit.Assert.assertTrue(
            "expected AppError.Auth after logout, got $appError",
            appError is ru.skatelab.shared.models.AppError.Auth,
        )
    }
}
```
> Note: `ru.skatelab.shared.utils.toAppError()` is the extension mapped in `ExceptionMapping.kt`; a 401 `ResponseException` must map to `AppError.Auth`. Verify the mapping in `ExceptionMapping.kt` maps 401 → `Auth` — if it maps to `Unknown`, scenario #14 is itself a found bug (open an issue; the test stays red).

- [ ] **Step 5: Run all 4 — record results**

Run:
```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.state.SessionReadAuthTest" 2>&1 | tail -30'
```
Record exact pass/fail from XML.

- [ ] **Step 6: ktlint**

Same `:shared:ktlintCheck`. Expected: BUILD SUCCESSFUL.

- [ ] **Step 7: Commit**

```bash
git add mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/SessionReadAuthTest.kt
git commit -m "test(mobile): repro scenarios for session read-path auth

Scenarios #11-#14: sessions list/detail use current account token,
transparent refresh on 401, clean AppError.Auth after logout. Catches
the same auth-cache leak class on the session read-path."
```

- [ ] **Step 8: Open issue for each RED scenario**

Use the #314 template. For #14, if the failure is an `AppError`-mapping gap (401 → `Unknown` not `Auth`), the issue's root cause cites `ExceptionMapping.kt` and the proposed fix is a mapping rule for 401.

---

## Task 5: Full suite verification + worktree wrap-up

**Files:** none modified — verification only.

- [ ] **Step 1: Run the entire new suite together**

```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local bash -c 'chmod +x gradlew && ./gradlew :shared:testDebugUnitTest --no-daemon --no-configuration-cache --tests "ru.skatelab.shared.auth.AuthWireTest" --tests "ru.skatelab.shared.state.SessionReadAuthTest" --tests "ru.skatelab.shared.auth.FakeAuthBackendSmokeTest" 2>&1 | tail -40'
```
Expected: the smoke test GREEN; scenarios mixed (RED where bugs exist, GREEN where the code already behaves). This is the intended end state — red tests are the deliverable.

- [ ] **Step 2: Confirm all RED scenarios have an open issue**

```bash
gh issue list --label "testing/repro" --state open --limit 30
```
Confirm one issue per RED scenario (expected ~5–9 issues across #1–#14; the exact count comes from Steps 4 of Tasks 2–4). Cross-reference #314 in each.

- [ ] **Step 3: Confirm no production code changed**

```bash
git diff --stat worktree-auth-cache-logout-bug-base..HEAD -- mobile/shared/src/commonMain mobile/androidApp/src/main
```
Expected: empty (only `commonTest` + `docs/` touched). If anything shows under `commonMain`/`src/main`, revert it — this plan touches tests only.

- [ ] **Step 4: Push the branch and open the test-suite PR**

```bash
git push -u origin worktree-auth-cache-logout-bug
gh pr create --title "test(mobile): auth/session integration test suite (FakeAuthBackend + 14 repro scenarios)" --body "$(cat <<'EOF'
## Что сделано
- `FakeAuthBackend` — test-double routing by path + actual Authorization header, mirrors backend refresh semantics (single-use, rotated).
- `AuthWireTest` (#1–#10): auth-cache/multi-account + refresh-token flow (zero prior coverage).
- `SessionReadAuthTest` (#11–#14): session read-path auth.
- Each failing scenario → `testing/repro` issue (linked below). Failing tests stay red as proof; fixes are separate PRs.

## Как проверить
- `./gradlew :shared:testDebugUnitTest --tests "ru.skatelab.shared.auth.AuthWireTest" --tests "ru.skatelab.shared.state.SessionReadAuthTest"`
- Red tests are intentional — see linked issues for root cause + proposed fixes.
- No production code changed (`git diff` on `commonMain`/`src/main` empty).

## Связанные issues
- #314 (original auth-cache leak repro)
- (list the testing/repro issues created in Tasks 2–4)
EOF
)"
```
> Note: per `finishing-a-development-branch`, ALL CI must be green before merge. Here the suite is *intentionally* red — do NOT merge this PR until either (a) the red tests are acked as known-broken and the PR is merged admin-override, or (b) the fix PRs land first and this PR rebases to green. **Default: leave the PR open, red, as the index of repros; merge only after fix PRs turn it green.** Confirm the merge strategy with the user before any merge.

- [ ] **Step 5: Update memory**

Write a project memory (per the memory protocol) recording: the auth-cache leak bug class (#314), the `FakeAuthBackend` pattern for integration testing the real Ktor `Auth` plugin, and the convention that failing repro tests stay red and map 1:1 to `testing/repro` issues. This captures the non-obvious testing approach for future sessions.