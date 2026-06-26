package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Repro — `AuthApi.verifyEmail` / `resetPassword` / `resendVerification` /
 * `forgotPassword` do NOT check `response.status.isSuccess()` and therefore
 * NEVER throw on a non-2xx response. `AuthRepository` wraps each in
 * `runCatching { authApi.<method>(...) }` (AuthRepository.kt:35-41), and since
 * no exception is thrown on backend rejection, the `Result` is ALWAYS
 * `success(Unit)` — even for HTTP 400/404/409. The UI then treats a failed
 * verify-email / reset-password as SUCCEEDED.
 *
 * Compare `login` (AuthApi.kt:63-64) and `register` (AuthApi.kt:79-80) which DO
 * guard `if (!response.status.isSuccess()) throw ResponseException(...)`. The
 * verify/reset/resend/forgot methods were written without that guard — a clear
 * oversight, not a deliberate silent-success design.
 *
 * Real impact:
 *   - `verifyEmail(invalidToken)` → backend 400 "Invalid or expired verification
 *     token" → AuthApi returns normally → `AuthRepository.verifyEmail` returns
 *     `Result.success(Unit)` → UI shows "email verified" though it was NOT.
 *   - `resetPassword(expiredToken, ...)` → backend 400 → `Result.success(Unit)`
 *     → UI tells the user "password reset" though it was NOT (the old password
 *     still works; the user believes their account is secured).
 *
 * The existing `AuthApiTest` only checks request SERIALIZATION for these
 * methods (verifyEmailRequestSerialization, resetPasswordRequestSerialization)
 * — it never exercises the FAILURE path, so the missing guard never surfaces.
 *
 * Repro: MockEngine responds 400 to `/auth/verify-email`; assert
 * `AuthRepository.verifyEmail(token).isFailure`. RED now: `isSuccess` (the call
 * returned normally with no exception). After the fix (add the same
 * `if (!response.status.isSuccess()) throw ResponseException(...)` guard as
 * login/register) → `isFailure`.
 */

class AuthApiNonSuccessNotThrownReproTest {
    private fun failureClient(): HttpClient {
        val engine = MockEngine { request ->
            // Every auth mutation endpoint returns 400 (backend rejection).
            respond(
                """{"message":"Invalid or expired token"}""",
                status = HttpStatusCode.BadRequest,
                headers = headersOf(
                    io.ktor.http.HttpHeaders.ContentType,
                    ContentType.Application.Json.toString(),
                ),
            )
        }
        return HttpClient(engine) {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            defaultRequest { url("https://api.skatelab.ru/v1/") }
        }
    }

    @Test
    fun verifyEmail_nonSuccess_mustThrow_notSilentSuccess_repro() = runTest {
        val api = AuthApi(failureClient())

        // CONTRACT: a 400 from /auth/verify-email must surface as a failure.
        // RED now: no status check → no throw → completes normally. After the fix
        // (add the login/register guard) → throws ResponseException.
        var threw = false
        try {
            api.verifyEmail("bad-token")
        } catch (e: Exception) {
            threw = true
        }
        assertTrue(
            threw,
            "BUG: AuthApi.verifyEmail did NOT throw on a 400 response — the UI will " +
                "treat a rejected email-verification as SUCCEEDED. login/register " +
                "guard response.status.isSuccess(); verifyEmail does not.",
        )
    }

    @Test
    fun resetPassword_nonSuccess_mustThrow_notSilentSuccess_repro() = runTest {
        val api = AuthApi(failureClient())

        var threw = false
        try {
            api.resetPassword("expired-token", "newPass123")
        } catch (e: Exception) {
            threw = true
        }
        assertTrue(
            threw,
            "BUG: AuthApi.resetPassword did NOT throw on a 400 response — the UI will " +
                "tell the user 'password reset successfully' though the backend " +
                "rejected the token and the OLD password still works.",
        )
    }
}