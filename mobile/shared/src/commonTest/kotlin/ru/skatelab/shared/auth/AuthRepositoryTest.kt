package ru.skatelab.shared.auth

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockEngineConfig
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AuthRepositoryTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun logout_sendsRefreshTokenAndClearsTokens() = kotlinx.coroutines.test.runTest {
        var requestUrl: String? = null
        var requestContentType: ContentType? = null
        val engine = MockEngine(MockEngineConfig().apply {
            addHandler { request ->
                requestUrl = request.url.toString()
                requestContentType = request.headers[HttpHeaders.ContentType]?.let { ContentType.parse(it) }
                respond(
                    "{}",
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
            }
        })
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)
        tokenStorage.saveTokens("access123", "refresh456")

        val repo = AuthRepository(AuthApi(client), tokenStorage)

        repo.logout()

        assertEquals(null, tokenStorage.getAccessToken(), "access token should be cleared after logout")
        assertEquals(null, tokenStorage.getRefreshToken(), "refresh token should be cleared after logout")
        assertTrue(requestUrl!!.contains("/auth/logout"), "logout should POST to /auth/logout, got $requestUrl")
        assertEquals(ContentType.Application.Json, requestContentType, "request should use JSON content type")
    }

    @Test
    fun logout_clearsTokensEvenWhenApiFails() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine(MockEngineConfig().apply {
            addHandler { _ ->
                respondError(HttpStatusCode.InternalServerError)
            }
        })
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)
        tokenStorage.saveTokens("access", "refresh")

        val repo = AuthRepository(AuthApi(client), tokenStorage)

        repo.logout()

        assertEquals(null, tokenStorage.getAccessToken(), "access token should be cleared even on API failure")
        assertEquals(null, tokenStorage.getRefreshToken(), "refresh token should be cleared even on API failure")
    }

    @Test
    fun isLoggedIn_returnsTrueWhenAccessTokenPresent() = kotlinx.coroutines.test.runTest {
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)
        tokenStorage.saveTokens("access", "refresh")

        val engine = MockEngine(MockEngineConfig().apply {
            addHandler { respond("{}", status = HttpStatusCode.OK) }
        })
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        assertTrue(repo.isLoggedIn())
    }

    @Test
    fun isLoggedIn_returnsFalseWhenNoAccessToken() = kotlinx.coroutines.test.runTest {
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)

        val engine = MockEngine(MockEngineConfig().apply {
            addHandler { respond("{}", status = HttpStatusCode.OK) }
        })
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val repo = AuthRepository(AuthApi(client), tokenStorage)

        assertFalse(repo.isLoggedIn())
    }
}