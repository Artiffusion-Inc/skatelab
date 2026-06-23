package ru.skatelab.shared.auth

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.UsersApi
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Repro for: after logout + login as a different user, `users/me` returns the *previous* user's
 * profile because the Ktor `Auth` plugin caches the bearer token in memory
 * (`AuthTokenHolder.value`) and `AuthRepository.logout/login` only touch persistent storage,
 * never invalidating that cache.
 *
 * Expected (post-fix): the second `getMe()` returns user B.
 * Actual (bug): returns user A — the cached token of the first session is reused.
 */
class AuthRepositoryCacheBugReproTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    private val userA = """{"id":"a","email":"test@skatelab.ru","display_name":"A"}"""
    private val userB = """{"id":"b","email":"e2e_1781976772@skatelab.ru","display_name":"B"}"""

    private val tokensA = """{"access_token":"acc-A","refresh_token":"ref-A","token_type":"bearer"}"""
    private val tokensB = """{"access_token":"acc-B","refresh_token":"ref-B","token_type":"bearer"}"""

    private fun jsonHeaders() =
        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    @Test
    fun logout_thenLoginAsDifferentUser_getMeReturnsNewUser() = runTest {
        val tokenStorage = TokenStorage(MapSettings())

        // First login → tokensA (user A); every subsequent login → tokensB (user B).
        // We don't need to parse the body — the repro only cares that a *second* login
        // produces a *different* token, exactly as a real backend would for a different account.
        var loginCount = 0

        // MockEngine routes by path; for `users/me` it answers a profile keyed off the
        // bearer token actually sent — so if the Auth plugin reuses a stale cached token,
        // we get the wrong profile back.
        val engine = MockEngine { request ->
            val path = request.url.encodedPath
            val authHeader = request.headers[HttpHeaders.Authorization] ?: ""
            when {
                path.endsWith("auth/login") -> {
                    loginCount += 1
                    respond(if (loginCount == 1) tokensA else tokensB, headers = jsonHeaders())
                }

                path.endsWith("auth/logout") -> respond("{}", headers = jsonHeaders())

                path.endsWith("users/me") -> {
                    val profile = when {
                        authHeader.contains("acc-A") -> userA
                        authHeader.contains("acc-B") -> userB
                        else -> userA // stale/unknown token → falls back to A (mirrors the bug)
                    }
                    respond(profile, headers = jsonHeaders())
                }

                else -> respond("{}", status = HttpStatusCode.NotFound, headers = jsonHeaders())
            }
        }

        val client =
            HttpClient(engine) {
                install(ContentNegotiation) { json(json) }
                install(Auth) {
                    bearer {
                        loadTokens {
                            val access = tokenStorage.getAccessToken() ?: return@loadTokens null
                            val refresh = tokenStorage.getRefreshToken() ?: return@loadTokens null
                            BearerTokens(access, refresh)
                        }
                        refreshTokens {
                            // Not exercised in this repro: `users/me` always 200, so no 401 → no refresh.
                            null
                        }
                    }
                }
            }

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val users = UsersApi(client)

        // 1) Login as user A, fetch profile → A
        repo.login("test@skatelab.ru", "pw")
        assertEquals("a", users.getMe().id)

        // 2) Logout (clears persistent storage only, NOT the Auth plugin's in-memory cache)
        repo.logout()

        // 3) Login as user B, fetch profile → SHOULD be B
        repo.login("e2e_1781976772@skatelab.ru", "pw")
        val profileAfterRelogin = users.getMe()
        assertEquals(
            "b",
            profileAfterRelogin.id,
            "Expected profile of newly logged-in user B, but got '${profileAfterRelogin.id}' " +
                "(email=${profileAfterRelogin.email}). The Ktor Auth plugin reused the stale " +
                "cached token from the previous session.",
        )

        client.close()
    }
}