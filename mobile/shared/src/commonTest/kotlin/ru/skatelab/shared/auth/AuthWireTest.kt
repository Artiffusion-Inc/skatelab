package ru.skatelab.shared.auth

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.AuthConfig
import io.ktor.client.plugins.auth.providers.BearerAuthProvider
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.ContentConvertException
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.models.TokenResponse
import kotlin.test.Test
import kotlin.test.assertEquals

class AuthWireTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    /**
     * Builds the test HttpClient with the real Ktor `Auth` plugin (mirrors
     * `SkateLabClient`) and returns a [clearCache] callback that flushes the
     * plugin's in-memory bearer cache — the same wiring production uses via
     * `SkateLabClient.clearAuthCache()` / the `AuthRepository` callback. The
     * public Ktor API exposes the bearer providers only through the
     * `AuthConfig` install-receiver, so it is captured here.
     */
    private fun newClient(backend: FakeAuthBackend, tokenStorage: TokenStorage): Pair<HttpClient, () -> Unit> {
        lateinit var authConfig: AuthConfig
        val client = HttpClient(backend.engine()) {
            install(ContentNegotiation) { json(json) }
            install(Auth) {
                authConfig = this
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
        val clearCache: () -> Unit = {
            authConfig.providers.filterIsInstance<BearerAuthProvider>().forEach { it.clearToken() }
        }
        return client to clearCache
    }

    @Test
    fun logoutThenLoginAsDifferentUser_getMeReturnsNewUser() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        // Login A
        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)

        // Logout (clears persistent storage only, NOT the Auth plugin cache -> bug)
        repo.logout()

        // Login B
        repo.login("b@skatelab.ru", "pw")
        val profile = users.getMe()
        // This is the repro from issue #314. Bug: returns "a". After the (separate) fix: "b".
        assertEquals("b", profile.id)
        client.close()
    }

    @Test
    fun logoutThenLoginSameUser_getMeSucceeds() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        repo.logout()
        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        client.close()
    }

    @Test
    fun logout_clearsInMemoryTokenCache() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        repo.logout()
        // After logout, users/me must NOT succeed with the stale cached token.
        // Bug: Auth plugin reuses cached acc -> returns "a" instead of 401.
        try {
            val me = users.getMe()
            org.junit.Assert.fail("expected unauthorized after logout, got profile id=${me.id}")
        } catch (e: io.ktor.client.plugins.ResponseException) {
            // expected: 401
        }
        client.close()
    }

    @Test
    fun registerAfterLogout_getMeReturnsNewUser() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        repo.register("a@skatelab.ru", "pw", "A")
        assertEquals("a", users.getMe().id)
        repo.logout()
        repo.register("b@skatelab.ru", "pw", "B")
        // Bug: register path shares the auth-cache leak. Returns "a".
        assertEquals("b", users.getMe().id)
        client.close()
    }

    @Test
    fun switchAccountTwice_getMeMatchesLatestLogin() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
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
        client.close()
    }

    // -- Task 3: refresh-token flow scenarios (#6–#10) --

    @Test
    fun expiredAccess_liveRefresh_getMeRetriesWithNewToken() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        // First getMe populates the Auth cache with acc-a-1; now expire it.
        assertEquals("a", users.getMe().id)
        backend.expireAccessToken("a")
        // Next getMe: 401 on access → refresh → retry with new access. Should return "a".
        val me = users.getMe()
        assertEquals("a", me.id)
        assertEquals(1, backend.refreshCallCount(), "refresh should have been called exactly once")
        client.close()
    }

    @Test
    fun expiredAccessAndRefresh_onAuthFailureTriggersLogout() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val usersApi = UsersApi(client)
        val sharedVm = ru.skatelab.shared.state.AuthViewModel(
            AuthRepository(AuthApi(client), tokenStorage, clearCache),
            usersApi,
        )

        sharedVm.login("a@skatelab.ru", "pw")
        // Both tokens dead: access 401, refresh 401.
        backend.expireAccessToken("a")
        backend.revokeRefreshToken("a")

        try {
            usersApi.getMe()
            org.junit.Assert.fail("expected unauthorized")
        } catch (e: io.ktor.serialization.ContentConvertException) {
            // After a dead refresh the Auth plugin returns the original 401 to getMe().body(),
            // which fails deserializing the error body into UserResponse — matches production's
            // MissingFieldException on a 401 error body with required UserResponse fields.
        }
        // After a dead refresh, the refreshTokens block cleared tokenStorage.
        // NOTE: the harness wires the HttpClient directly (not via SkateLabClient),
        // so the onAuthFailure → AuthViewModel.onAuthFailure() callback chain is NOT
        // exercised here — that wiring lives in SkateLabClient/AppModule and is a
        // separate concern. We assert on the observable effect: storage cleared.
        assertEquals(null, tokenStorage.getAccessToken())
        assertEquals(null, tokenStorage.getRefreshToken())
        assertEquals(1, backend.refreshCallCount())
        client.close()
    }

    @Test
    fun concurrentRequestsOnExpiringToken_refreshCalledOnce() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        backend.expireAccessToken("a")

        coroutineScope {
            val deferred1 = async { users.getMe() }
            val deferred2 = async { users.getMe() }
            val r1 = deferred1.await()
            val r2 = deferred2.await()
            assertEquals("a", r1.id)
            assertEquals("a", r2.id)
        }
        assertEquals(
            1,
            backend.refreshCallCount(),
            "two concurrent requests must trigger only one refresh",
        )
        client.close()
    }

    @Test
    fun refreshReturnsNewRefreshToken_storageUpdated() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
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
        client.close()
    }

    @Test
    fun refreshFailureThenSuccess_doesNotLeakStaleState() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A")
        val tokenStorage = TokenStorage(MapSettings())
        val (client, clearCache) = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage, clearCache)
        val users = UsersApi(client)

        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)

        // First: refresh is dead → getMe fails, storage cleared.
        backend.expireAccessToken("a")
        backend.revokeRefreshToken("a")
        try {
            users.getMe()
            org.junit.Assert.fail("expected unauthorized")
        } catch (e: io.ktor.serialization.ContentConvertException) {
            // After a dead refresh the Auth plugin returns the original 401 to getMe().body(),
            // which fails deserializing the error body into UserResponse — matches production's
            // MissingFieldException on a 401 error body with required UserResponse fields.
        }
        assertEquals(1, backend.refreshCallCount())

        // Then: user re-logs in (fresh tokens). getMe must succeed — no "I already gave up" state.
        backend.revokeRefreshToken("a") // reset not needed: login re-issues
        repo.login("a@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)
        client.close()
    }
}