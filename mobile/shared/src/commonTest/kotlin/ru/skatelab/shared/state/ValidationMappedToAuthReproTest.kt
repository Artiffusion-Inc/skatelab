package ru.skatelab.shared.state

import com.russhwolf.settings.MapSettings
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.auth.TokenStorage
import ru.skatelab.shared.models.AppError
import kotlin.test.Test
import kotlin.test.assertFalse

/**
 * Repro for bugs M3/M4/M5 — backend Pydantic validation failures (HTTP 400/422 from a short
 * password / invalid email / over-long display_name) are mapped to `AppError.Auth`, so the mobile
 * auth screens render `stringResource(R.string.error_auth)` = "Authentication error. Please log
 * in again." This is misleading: the user did NOT fail authentication, their INPUT was invalid. The
 * actionable Pydantic validation detail ("password: field too short" / "value is not a valid
 * email") — which the backend returns in the response body and `AuthApi.ensureSuccess` faithfully
 * carries as the `ResponseException.message` — is discarded by the mapping layer.
 *
 * Confirmed root cause:
 *   `ExceptionMapping.kt:37` — `400, 422 -> AppError.Auth()` lumps validation failures into the
 *   same `Auth` variant as real 401/403 auth failures. There is no `Validation` / input-error
 *   branch, and unlike the 409 branch (which added `AppError.Conflict(detail = ...)` to surface the
 *   backend text), the 400/422 branch ignores its `detail` argument entirely and constructs
 *   `AppError.Auth()` with no detail. `RegisterScreen.kt:125` renders `AppError.Auth -> error_auth`
 *   = "Authentication error. Please log in again." (`strings.xml:134`, `values-ru` similar).
 *
 * User impact:
 *   A user registering with "short" as password (M3), or "notanemail" as email (M4), or a 200-char
 *   display_name (M5) is told to "log in again" — nonsense guidance for an input-validation
 *   failure. They never learn which field was invalid or why; the precise Pydantic detail
 *   ("password: field too short") is thrown away. The user re-tries blindly with no actionable
 *   signal, and may assume their session/account is broken.
 *
 * Bug-class: same "detail lost in status→AppError mapping" family as #442 (409 → Unknown, fixed by
 * adding `AppError.Conflict`) and #363 (which added the `Conflict` variant but missed a `Validation`
 * variant for 400/422). One issue covers M3 (short password) + M4 (invalid email) + M5
 * (display_name>100, same 400/422 → Auth mapping).
 *
 * Contract pinned by this repro: on a 400/422 validation failure (backend body carrying the
 * Pydantic detail), the surfaced `AppError` must NOT be `AppError.Auth` — a validation/input error
 * is not an authentication failure. RED now: `register` yields `Error(AppError.Auth)` (400/422 →
 * Auth in `toAppError`). After a hypothetical fix (add `AppError.Validation` carrying the backend
 * detail, or map 400/422 to a distinct non-Auth variant) → GREEN.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ValidationMappedToAuthReproTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun jsonHeaders() = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString(),
    )

    @Test
    fun register_shortPassword_400_mustNotMapToAuth_repro() = runTest {
        // Mirror the REAL backend 400 response for a short-password registration
        // (backend/tests/test_auth_routes.py:48 test_register_short_password asserts 400).
        val validationBody = """{"error":"password: field too short","message":"password: field too short","details":null,"path":"/v1/auth/register"}"""
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(validationBody, HttpStatusCode.BadRequest, jsonHeaders())
                // users/me should not be reached on register failure, but keep a sane default.
                "/users/me" -> respond("""{"id":"u","email":"e","display_name":"x"}""", HttpStatusCode.OK, jsonHeaders())
                else -> respond("""{"error":"not found"}""", HttpStatusCode.NotFound, jsonHeaders())
            }
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())
        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.register("alice@example.com", "short", "Alice")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        val errorState = state as AuthUiState.Error

        // CONTRACT: a 400 validation failure ("password: field too short") is an INPUT error, NOT
        // an authentication failure. It must surface validation semantics (a future
        // AppError.Validation, or at minimum a non-Auth variant), NOT AppError.Auth. RED now: error
        // is AppError.Auth (400 → Auth mapping in ExceptionMapping.kt:37). After the fix → GREEN.
        assertFalse(
            actual = errorState.error is AppError.Auth,
            message = "BUG: register 400 (\"password: field too short\") maps to AppError.Auth — " +
                "the user sees misleading \"Authentication error. Please log in again.\" instead " +
                "of the Pydantic validation detail. A 400/422 input-validation failure is not an " +
                "authentication failure. Actual error class: ${errorState.error::class.simpleName}",
        )
    }

    @Test
    fun register_invalidEmail_400_mustNotMapToAuth_repro() = runTest {
        // Mirror the REAL backend 400 response for an invalid-email registration
        // (Pydantic EmailStr validation rejects "notanemail" → 400).
        val validationBody = """{"error":"value is not a valid email","message":"value is not a valid email","details":null,"path":"/v1/auth/register"}"""
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(validationBody, HttpStatusCode.BadRequest, jsonHeaders())
                "/users/me" -> respond("""{"id":"u","email":"e","display_name":"x"}""", HttpStatusCode.OK, jsonHeaders())
                else -> respond("""{"error":"not found"}""", HttpStatusCode.NotFound, jsonHeaders())
            }
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val tokenStorage = TokenStorage(MapSettings())
        val viewModel = AuthViewModel(
            authRepo = AuthRepository(AuthApi(client), tokenStorage),
            usersApi = UsersApi(client),
        )

        viewModel.register("notanemail", "Password123", "Alice")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        val errorState = state as AuthUiState.Error

        // CONTRACT: a 400 validation failure ("value is not a valid email") is an INPUT error, NOT
        // an authentication failure. RED now: error is AppError.Auth. After the fix → GREEN.
        assertFalse(
            actual = errorState.error is AppError.Auth,
            message = "BUG: register 400 (\"value is not a valid email\") maps to AppError.Auth — " +
                "the user sees misleading \"Authentication error. Please log in again.\" instead " +
                "of the Pydantic validation detail. A 400/422 input-validation failure is not an " +
                "authentication failure. Actual error class: ${errorState.error::class.simpleName}",
        )
    }
}