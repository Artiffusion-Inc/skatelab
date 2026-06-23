package ru.skatelab.shared.auth

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
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.models.TokenResponse
import kotlin.test.Test
import kotlin.test.assertEquals

class AuthWireTest {
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
        return client
    }

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
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
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
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
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
        val client = newClient(backend, tokenStorage)
        val repo = AuthRepository(AuthApi(client), tokenStorage)
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
        client.close()
    }
}