package ru.skatelab.shared.auth

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.engine.mock.respondOk
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
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class AuthRepositoryTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeEngine(response: String = "{}", status: HttpStatusCode = HttpStatusCode.OK): MockEngine =
        MockEngine { _ ->
            respond(
                response,
                status = status,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }

    @Test
    fun logout_clearsTokens() = kotlinx.coroutines.test.runTest {
        val client = HttpClient(makeEngine()) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access123", "refresh456")

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        repo.logout()

        assertEquals(null, tokenStorage.getAccessToken())
        assertEquals(null, tokenStorage.getRefreshToken())
    }

    @Test
    fun logout_sendsRequestToAuthLogout() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        repo.logout()

        assertNotNull(capturedPath, "MockEngine should have captured a request")
        assertTrue(capturedPath!!.contains("auth/logout"), "Expected path to contain 'auth/logout', got: $capturedPath")
    }

    @Test
    fun logout_clearsTokensEvenWhenApiFails() = kotlinx.coroutines.test.runTest {
        val client = HttpClient(makeEngine(status = HttpStatusCode.InternalServerError)) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        repo.logout()

        assertEquals(null, tokenStorage.getAccessToken())
        assertEquals(null, tokenStorage.getRefreshToken())
    }

    @Test
    fun isLoggedIn_returnsTrueWhenAccessTokenPresent() = kotlinx.coroutines.test.runTest {
        val client = HttpClient(makeEngine()) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        assertTrue(repo.isLoggedIn())
    }

    @Test
    fun isLoggedIn_returnsFalseWhenNoAccessToken() = kotlinx.coroutines.test.runTest {
        val client = HttpClient(makeEngine()) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        assertFalse(repo.isLoggedIn())
    }

    @Test
    fun login_savesTokensOnSuccess() = kotlinx.coroutines.test.runTest {
        val response = """{"access_token":"acc123","refresh_token":"ref456","token_type":"bearer"}"""
        val client = HttpClient(makeEngine(response)) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.login("user@example.com", "password123")

        assertTrue(result.isSuccess)
        assertEquals("acc123", tokenStorage.getAccessToken())
        assertEquals("ref456", tokenStorage.getRefreshToken())
    }

    @Test
    fun login_returnsFailureOnHttpError() = kotlinx.coroutines.test.runTest {
        val client = HttpClient(makeEngine(status = HttpStatusCode.Unauthorized)) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.login("user@example.com", "wrong")

        assertTrue(result.isFailure)
        assertEquals(null, tokenStorage.getAccessToken())
    }

    @Test
    fun register_savesTokensOnSuccess() = kotlinx.coroutines.test.runTest {
        val response = """{"access_token":"acc-reg","refresh_token":"ref-reg","token_type":"bearer"}"""
        val client = HttpClient(makeEngine(response)) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.register("new@example.com", "pass123", "Skater")

        assertTrue(result.isSuccess)
        assertEquals("acc-reg", tokenStorage.getAccessToken())
        assertEquals("ref-reg", tokenStorage.getRefreshToken())
    }

    @Test
    fun register_returnsFailureOnDuplicateEmail() = kotlinx.coroutines.test.runTest {
        val client = HttpClient(makeEngine(status = HttpStatusCode.Conflict)) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.register("existing@example.com", "pass", "Name")

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
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.verifyEmail("verify-token-abc")

        assertTrue(result.isSuccess)
        assertNotNull(capturedPath, "MockEngine should have captured a request")
        assertTrue(capturedPath!!.contains("auth/verify-email"), "Expected path to contain 'auth/verify-email', got: $capturedPath")
    }

    @Test
    fun forgotPassword_sendsEmail() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.forgotPassword("user@example.com")

        assertTrue(result.isSuccess)
        assertNotNull(capturedPath, "MockEngine should have captured a request")
        assertTrue(capturedPath!!.contains("auth/forgot-password"), "Expected path to contain 'auth/forgot-password', got: $capturedPath")
    }

    @Test
    fun resetPassword_sendsTokenAndNewPassword() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())

        val repo = AuthRepository(AuthApi(client), tokenStorage)
        val result = repo.resetPassword("reset-token-xyz", "newSecurePass123")

        assertTrue(result.isSuccess)
        assertNotNull(capturedPath, "MockEngine should have captured a request")
        assertTrue(capturedPath!!.contains("auth/reset-password"), "Expected path to contain 'auth/reset-password', got: $capturedPath")
    }
}
