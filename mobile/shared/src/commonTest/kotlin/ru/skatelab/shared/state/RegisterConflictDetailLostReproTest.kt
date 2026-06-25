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
import kotlin.test.assertIs

/**
 * Repro for NEW bug — backend validation/conflict detail (409 "Email already registered") is lost
 * in a generic `AppError.Unknown`, so the user sees "unknown error" instead of an actionable message.
 *
 * Confirmed against the REAL backend `api.skatelab.ru` (2026-06-25):
 *
 *   POST /v1/auth/register  {"email":"test@skatelab.ru","password":"..."}
 *     → HTTP 409
 *     → body: {"error":"Email already registered","message":"Email already registered",...}
 *
 * The backend returns a precise, actionable conflict message. The mobile client throws it away.
 *
 * Root cause (two layers):
 *   1. `AuthApi.register()` (AuthApi.kt:74-78) on non-2xx throws
 *      `ResponseException(response, response.status.description)` — it uses the HTTP reason-phrase
 *      ("Conflict"), NOT the response body. The JSON `{"error":"Email already registered"}` body is
 *      never read, so the detail is lost at the HTTP layer.
 *   2. `ExceptionMapping.toAppError()` (ExceptionMapping.kt:28-35) maps status codes:
 *      400/422/401/403 → Auth; 404 → NotFound; 5xx → Server; **else → Unknown**. 409 falls into
 *      `else` → `AppError.Unknown(detail = "<ResponseException message>")`. The "detail" is the
 *      Ktor reason-phrase text ("Client request(...) invalid: 409 Conflict"), NOT the backend's
 *      "Email already registered".
 *
 * Net: a user registering with an already-taken email sees the generic localized "unknown error"
 * (`error_unknown`) — they do NOT learn the email is taken and get no actionable guidance ("try
 * another email" / "log in instead"). The actionable backend detail is discarded.
 *
 * Contrast: the backend clearly distinguishes 409 (conflict) from 400 (validation) from 401
 * (auth). `AppError` has no Conflict/Validation variant — only Auth/NotFound/Server/Unknown — so
 * 409 collapses into Unknown.
 *
 * This repro pins the contract: on a 409 register conflict (with the backend body carrying
 * "Email already registered"), the surfaced `AppError` must NOT be the generic `Unknown` — it must
 * carry conflict/validation semantics (e.g. a new `AppError.Conflict` / `AppError.Validation`, or
 * at minimum surface the backend `error` field as actionable text). RED now: `register` yields
 * `Error(AppError.Unknown)`. After the fix → GREEN.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class RegisterConflictDetailLostReproTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun jsonHeaders() = headersOf(
        HttpHeaders.ContentType, ContentType.Application.Json.toString(),
    )

    @Test
    fun register_409Conflict_mustNotCollapseToUnknown_repro() = runTest {
        // Mirror the REAL backend 409 response for a duplicate-email registration.
        val conflictBody = """{"error":"Email already registered","message":"Email already registered","details":null,"path":"/v1/auth/register"}"""
        val engine = MockEngine { request ->
            when (request.url.encodedPath) {
                "/auth/register" -> respond(conflictBody, HttpStatusCode.Conflict, jsonHeaders())
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

        viewModel.register("alice@example.com", "Password123", "Alice")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        // Register failed (did not become LoggedIn) — confirm we are in the Error branch.
        val errorState = assertIs<AuthUiState.Error>(state)

        // CONTRACT: a 409 conflict ("Email already registered") must surface a conflict/validation
        // signal, NOT a generic Unknown. RED now: error is AppError.Unknown (409 → else branch in
        // toAppError). After the fix (Conflict/Validation variant, or surfacing backend detail) →
        // this assertion passes.
        assertFalse(
            actual = errorState.error is AppError.Unknown,
            message = "BUG: register 409 (\"Email already registered\") collapses to AppError.Unknown " +
                "— the actionable backend conflict detail is lost and the user sees a generic " +
                "\"unknown error\". A 409 must surface conflict/validation semantics. " +
                "Actual error class: ${errorState.error::class.simpleName}",
        )
    }
}
