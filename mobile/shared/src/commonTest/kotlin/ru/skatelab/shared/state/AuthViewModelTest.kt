package ru.skatelab.shared.state

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
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
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.auth.TokenStorage
import kotlin.test.Test
import kotlin.test.assertEquals

class AuthViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private val userResponse = """{
        "id":"user-1",
        "email":"alice@example.com",
        "display_name":"Alice",
        "avatar_url":null,
        "bio":null,
        "height_cm":null,
        "weight_kg":null,
        "language":"ru",
        "timezone":"UTC",
        "theme":"dark",
        "onboarding_role":null,
        "angular_unit":"deg_per_sec"
    }"""

    private val loginResponse = """{"access_token":"acc123","refresh_token":"ref456","token_type":"bearer"}"""

    private fun jsonHeaders() = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString(),
    )

    private fun makeClient(engine: MockEngine): HttpClient =
        HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }

    @Test
    fun checkLogin_whenLoggedIn_transitionsToLoggedIn() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/users/me" -> respond(userResponse, HttpStatusCode.OK, jsonHeaders())
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.checkLogin()

        assertEquals(AuthUiState.LoggedIn("user-1", "Alice"), viewModel.uiState.value)
    }

    @Test
    fun checkLogin_whenLoggedIn_getMeFails_fallsBackToCached() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/users/me" -> respondError(HttpStatusCode.InternalServerError)
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.checkLogin()

        assertEquals(AuthUiState.LoggedIn("cached", null), viewModel.uiState.value)
    }

    @Test
    fun checkLogin_whenNotLoggedIn_transitionsToLoggedOut() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { respondError(HttpStatusCode.NotFound) }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.checkLogin()

        assertEquals(AuthUiState.LoggedOut, viewModel.uiState.value)
    }

    @Test
    fun login_success_transitionsToLoggedIn() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/login" -> respond(loginResponse, HttpStatusCode.OK, jsonHeaders())
                "/users/me" -> respond(userResponse, HttpStatusCode.OK, jsonHeaders())
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.login("alice@example.com", "password123")

        assertEquals(AuthUiState.LoggedIn("user-1", "Alice"), viewModel.uiState.value)
    }

    @Test
    fun login_success_getMeFails_fallsBackToNew() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/login" -> respond(loginResponse, HttpStatusCode.OK, jsonHeaders())
                "/users/me" -> respondError(HttpStatusCode.InternalServerError)
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.login("alice@example.com", "password123")

        assertEquals(AuthUiState.LoggedIn("new", null), viewModel.uiState.value)
    }

    @Test
    fun login_failure_transitionsToError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/login" -> respondError(HttpStatusCode.Unauthorized)
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.login("alice@example.com", "wrong")

        val state = viewModel.uiState.value
        assert(state is AuthUiState.Error) { "Expected Error state, got $state" }
    }

    @Test
    fun register_success_transitionsToLoggedIn() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(loginResponse, HttpStatusCode.OK, jsonHeaders())
                "/users/me" -> respond(userResponse, HttpStatusCode.OK, jsonHeaders())
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.register("alice@example.com", "password123", "Alice")

        assertEquals(AuthUiState.LoggedIn("user-1", "Alice"), viewModel.uiState.value)
    }

    @Test
    fun register_success_getMeFails_usesDisplayNameFallback() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(loginResponse, HttpStatusCode.OK, jsonHeaders())
                "/users/me" -> respondError(HttpStatusCode.InternalServerError)
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.register("alice@example.com", "password123", "Alice")

        assertEquals(AuthUiState.LoggedIn("new", "Alice"), viewModel.uiState.value)
    }

    @Test
    fun register_failure_transitionsToError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respondError(HttpStatusCode.Conflict)
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.register("existing@example.com", "pass", "Name")

        val state = viewModel.uiState.value
        assert(state is AuthUiState.Error) { "Expected Error state, got $state" }
    }

    @Test
    fun logout_transitionsToLoggedOut() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/logout" -> respond("{}", HttpStatusCode.OK, jsonHeaders())
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())
        tokenStorage.saveTokens("access", "refresh")

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        // Start from a logged-in state
        viewModel.checkLogin()
        viewModel.logout()

        assertEquals(AuthUiState.LoggedOut, viewModel.uiState.value)
    }

    @Test
    fun login_initialStateIsLoading() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { respondError(HttpStatusCode.NotFound) }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        assertEquals(AuthUiState.Loading, viewModel.uiState.value)
    }

    @Test
    fun login_failure_resetsToLoadingThenError() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/login" -> respondError(HttpStatusCode.Unauthorized)
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val client = makeClient(engine)
        val tokenStorage = TokenStorage(MapSettings())

        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        // Initial state is Loading
        assertEquals(AuthUiState.Loading, viewModel.uiState.value)

        viewModel.login("alice@example.com", "wrong")

        // After login failure, state is Error
        val state = viewModel.uiState.value
        assert(state is AuthUiState.Error) { "Expected Error state, got $state" }
    }
}
