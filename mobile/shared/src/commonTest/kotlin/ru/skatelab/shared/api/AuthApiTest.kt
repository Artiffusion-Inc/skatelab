package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AuthApiTest {
    @Test
    fun loginRequestSerialization() {
        val req = LoginRequest(email = "test@example.com", password = "secret123")
        val json = Json.encodeToString(req)
        assertTrue(json.contains("test@example.com"))
        assertTrue(json.contains("secret123"))
    }

    @Test
    fun login_resolvesUnderV1BaseUrl() = kotlinx.coroutines.test.runTest {
        // Regression: AuthApi paths used a leading "/" (e.g. "/auth/login"), which Ktor
        // treats as absolute — replacing the whole base path. With baseUrl
        // "https://api.skatelab.ru/v1/" the request went to /auth/login (no /v1) → 404,
        // and deserializing the error body as TokenResponse crashed with
        // "Fields [access_token, refresh_token] are required ... but they were missing".
        // Relative paths ("auth/login") must resolve to /v1/auth/login.
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respond(
                """{"access_token":"at","refresh_token":"rt","token_type":"bearer"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation { json(Json { ignoreUnknownKeys = true }) })
            defaultRequest { url("https://api.skatelab.ru/v1/") }
        }
        val api = AuthApi(client)
        val tokens = api.login("test@example.com", "secret123")
        assertEquals("/v1/auth/login", capturedPath)
        assertEquals("at", tokens.accessToken)
        assertEquals("rt", tokens.refreshToken)
    }

    @Test
    fun registerRequestSerialization() {
        val req = RegisterRequest(email = "test@example.com", password = "secret123", displayName = "Test User")
        val json = Json.encodeToString(req)
        assertTrue(json.contains("display_name"))
        assertTrue(json.contains("Test User"))
    }

    @Test
    fun registerRequestWithoutDisplayName() {
        val req = RegisterRequest(email = "test@example.com", password = "secret123")
        val json = Json.encodeToString(req)
        assertTrue(json.contains("test@example.com"))
        assertTrue(!json.contains("display_name"))
    }

    @Test
    fun logoutRequestSerialization() {
        val req = LogoutRequest(refreshToken = "rt-123")
        val json = Json.encodeToString(req)
        assertTrue(json.contains("refresh_token"))
        assertTrue(json.contains("rt-123"))
    }

    @Test
    fun verifyEmailRequestSerialization() {
        val req = VerifyEmailRequest(token = "tok-abc")
        val json = Json.encodeToString(req)
        assertTrue(json.contains("tok-abc"))
    }

    @Test
    fun resetPasswordRequestSerialization() {
        val req = ResetPasswordRequest(token = "tok-reset", newPassword = "newPass123")
        val json = Json.encodeToString(req)
        assertTrue(json.contains("new_password"))
        assertTrue(json.contains("newPass123"))
    }
}
