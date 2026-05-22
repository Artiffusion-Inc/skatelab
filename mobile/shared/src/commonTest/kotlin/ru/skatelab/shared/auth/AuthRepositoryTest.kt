package ru.skatelab.shared.auth

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
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

    private fun makeClient(handler: MockRequestHandler): HttpClient =
        HttpClient(MockEngine(handler)) {
            install(ContentNegotiation) { json(json) }
        }

    @Test
    fun logout_sendsRefreshTokenAndClearsProvider() = kotlinx.coroutines.test.runTest {
        var requestUrl: String? = null
        var requestContentType: ContentType? = null
        val client = makeClient { request ->
            requestUrl = request.url.toString()
            requestContentType = request.contentType()
            respond(
                "{}",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)
        tokenStorage.saveTokens("access123", "refresh456")

        var clearProviderCalled = false
        val repo = AuthRepository(
            AuthApi(client, "https://api.test"),
            tokenStorage,
        ) { clearProviderCalled = true }

        repo.logout()

        assertTrue(clearProviderCalled, "clearAuthProvider should be called after logout")
        assertTrue(requestUrl!!.contains("/auth/logout"), "logout should POST to /auth/logout, got $requestUrl")
        assertEquals(ContentType.Application.Json, requestContentType, "request should use JSON content type")
    }

    @Test
    fun logout_clearsTokensEvenWhenApiFails() = kotlinx.coroutines.test.runTest {
        val client = makeClient { _ ->
            respondError(HttpStatusCode.InternalServerError)
        }
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)
        tokenStorage.saveTokens("access", "refresh")

        var clearProviderCalled = false
        val repo = AuthRepository(
            AuthApi(client, "https://api.test"),
            tokenStorage,
        ) { clearProviderCalled = true }

        repo.logout()

        // Tokens should be cleared even though API failed
        assertEquals(null, tokenStorage.getAccessToken())
        assertEquals(null, tokenStorage.getRefreshToken())
        assertTrue(clearProviderCalled, "clearAuthProvider should be called even on API failure")
    }

    @Test
    fun isLoggedIn_returnsTrueWhenAccessTokenPresent() = kotlinx.coroutines.test.runTest {
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)
        tokenStorage.saveTokens("access", "refresh")

        val client = makeClient { respond("{}") }
        val repo = AuthRepository(AuthApi(client, "https://api.test"), tokenStorage) {}

        assertTrue(repo.isLoggedIn())
    }

    @Test
    fun isLoggedIn_returnsFalseWhenNoAccessToken() = kotlinx.coroutines.test.runTest {
        val settings = com.russhwolf.settings.Settings()
        val tokenStorage = TokenStorage(settings)

        val client = makeClient { respond("{}") }
        val repo = AuthRepository(AuthApi(client, "https://api.test"), tokenStorage) {}

        assertFalse(repo.isLoggedIn())
    }
}
