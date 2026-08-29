package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.*
import io.ktor.client.request.*
import io.ktor.client.statement.HttpResponse
import io.ktor.http.*
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import ru.skatelab.shared.models.TokenResponse
import ru.skatelab.shared.state.AuthRecoveryApi
import ru.skatelab.shared.utils.expectSuccess

/**
 * Minimal shape of the backend error body: `{"error":"...","message":"...",...}`.
 * `details` and other fields are ignored (the backend's actionable text is `error`/`message`).
 */
@Serializable
private data class ErrorBody(
    val error: String? = null,
    val message: String? = null,
)

/**
 * Read the backend's actionable detail from a non-2xx response body.
 *
 * The backend returns `{"error":"Email already registered","message":"Email already registered",
 * "details":null,...}`. We surface `error` (falling back to `message`) so the caller sees the
 * backend's precise conflict/validation text instead of the generic HTTP reason-phrase
 * ("Conflict"). On any parse failure we fall back to [reasonPhrase] so behavior never regresses
 * below the previous "reason-phrase-only" path.
 */
private suspend fun parseErrorDetail(response: HttpResponse, reasonPhrase: String): String {
    return runCatching {
        val body: ErrorBody = response.body()
        body.error?.takeIf { it.isNotBlank() } ?: body.message?.takeIf { it.isNotBlank() } ?: reasonPhrase
    }.getOrDefault(reasonPhrase)
}

/**
 * Throw on a non-2xx response, carrying the backend's response-body detail (the actionable
 * "Email already registered"-style text) as the exception message — NOT the HTTP reason-phrase.
 * `ExceptionMapping.toAppError()` reads this message when mapping a 409 → `AppError.Conflict`.
 */
private suspend fun ensureSuccess(response: HttpResponse) {
    if (!response.status.isSuccess()) {
        throw ResponseException(response, parseErrorDetail(response, response.status.description))
    }
}

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    @SerialName("display_name") val displayName: String? = null,
)

@Serializable
data class LogoutRequest(
    @SerialName("refresh_token") val refreshToken: String,
)

@Serializable
data class VerifyEmailRequest(
    val token: String,
)

@Serializable
data class ResendVerificationRequest(
    val email: String,
)

@Serializable
data class ForgotPasswordRequest(
    val email: String,
)

@Serializable
data class ResetPasswordRequest(
    val token: String,
    @SerialName("password") val newPassword: String,
)

class AuthApi(
    private val client: HttpClient,
) : AuthRecoveryApi {
    suspend fun login(
        email: String,
        password: String,
    ): TokenResponse {
        val response =
            client.post("auth/login") {
                contentType(ContentType.Application.Json)
                setBody(LoginRequest(email, password))
            }
        ensureSuccess(response)
        return response.body()
    }

    suspend fun register(
        email: String,
        password: String,
        displayName: String? = null,
    ): TokenResponse {
        val response =
            client.post("auth/register") {
                contentType(ContentType.Application.Json)
                setBody(RegisterRequest(email, password, displayName))
            }
        ensureSuccess(response)
        return response.body()
    }

    suspend fun logout(refreshToken: String) {
        client.post("auth/logout") {
            contentType(ContentType.Application.Json)
            setBody(LogoutRequest(refreshToken))
        }.expectSuccess()
    }

    suspend fun verifyEmail(token: String) {
        client.post("auth/verify-email") {
            contentType(ContentType.Application.Json)
            setBody(VerifyEmailRequest(token))
        }.expectSuccess()
    }

    suspend fun resendVerification(email: String) {
        client.post("auth/resend-verification") {
            contentType(ContentType.Application.Json)
            setBody(ResendVerificationRequest(email))
        }.expectSuccess()
    }

    override suspend fun forgotPassword(email: String) {
        client.post("auth/forgot-password") {
            contentType(ContentType.Application.Json)
            setBody(ForgotPasswordRequest(email))
        }.expectSuccess()
    }

    suspend fun resetPassword(
        token: String,
        newPassword: String,
    ) {
        client.post("auth/reset-password") {
            contentType(ContentType.Application.Json)
            setBody(ResetPasswordRequest(token, newPassword))
        }.expectSuccess()
    }
}
