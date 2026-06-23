package ru.skatelab.shared.state

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.auth.FakeAuthBackend
import ru.skatelab.shared.auth.TokenStorage
import ru.skatelab.shared.models.TokenResponse
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Session read-path integration scenarios (#11–#14).
 *
 * Each test wires the real Ktor `Auth` plugin against `FakeAuthBackend` (a `MockEngine`
 * routing by path + actual `Authorization` header) and exercises `SessionsApi`. The
 * `newClient` harness is duplicated locally from `AuthWireTest` to keep this file
 * self-contained, matching the existing commonTest convention (see
 * `SessionsViewModelTest`). The `refreshTokens` block mirrors
 * `SkateLabClient.kt:48-66` so the real refresh path is exercised.
 */
class SessionReadAuthTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

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
                                contentType(ContentType.Application.Json)
                                setBody(buildJsonObject { put("refresh_token", refreshToken) })
                            }.body<TokenResponse>()
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
        return client
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
        client.close()
    }

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
        client.close()
    }

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
        client.close()
    }

    /**
     * After logout, requesting `sessions.list()` must NOT return another user's sessions and
     * must surface as a clean auth error (not silent success with stale data, not a foreign
     * profile).
     *
     * OBSERVED BEHAVIOR (this run): the call does NOT throw and does NOT return empty — it
     * silently returns account A's sessions (`a-sess-1`). `AuthRepository.logout()` clears
     * persistent `TokenStorage` but never invalidates the Ktor `Auth` plugin's in-memory
     * `BearerAuthProvider` cache, so the plugin keeps attaching the still-valid access token
     * `acc-a-1` to the next request. The backend honours it and returns A's session list.
     * This is the same auth-cache leak class as #314 / scenario #11, surfacing on the session
     * read-path. The test is therefore RED at the first assertion: a failure is expected
     * (logout must revoke access), but the call succeeds with stale credentials.
     *
     * After the cache-leak fix, the Auth plugin will have no token to load and the request
     * will go out unauthenticated → backend 401 with `{"detail":"Unauthorized"}`. Deserializing
     * that 401 error body into `SessionListResponse` will then fail (missing required fields)
     * → `ContentConvertException` (NOT `ResponseException`), and `toAppError()` maps that to
     * `AppError.Unknown` — a SECOND, separate mapping gap (the 401 status is buried inside the
     * convert exception and not inspected by `ExceptionMapping.kt`). That mapping gap is noted
     * in the linked issue as the follow-on fix; the cache leak is the root cause fixed first.
     */
    @Test
    fun sessionsList_afterLogout_failsCleanly() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val sessions = SessionsApi(client)

        repo.login("a@skatelab.ru", "pw")
        repo.logout()

        // After logout the session read-path must FAIL (throw), surfacing as a clean auth
        // error. It must NOT silently return the previous account's sessions. Bug: the Auth
        // plugin's cached bearer token survives logout, so this succeeds with a-sess-1.
        val err = runCatching { sessions.list() }.exceptionOrNull()
        org.junit.Assert.assertNotNull(
            "expected sessions.list() to FAIL after logout, but it silently returned a list " +
                "(Auth plugin reused the cached token for account A — auth-cache leak class #314)",
            err,
        )
        client.close()
    }
}