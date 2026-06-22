package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import ru.skatelab.shared.models.TokenResponse

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
    @SerialName("new_password") val newPassword: String,
)

class AuthApi(
    private val client: HttpClient,
) {
    suspend fun login(
        email: String,
        password: String,
    ): TokenResponse {
        val response =
            client.post("auth/login") {
                contentType(ContentType.Application.Json)
                setBody(LoginRequest(email, password))
            }
        if (!response.status.isSuccess()) {
            throw ResponseException(response, response.status.description)
        }
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
        if (!response.status.isSuccess()) {
            throw ResponseException(response, response.status.description)
        }
        return response.body()
    }

    suspend fun logout(refreshToken: String) {
        client.post("auth/logout") {
            contentType(ContentType.Application.Json)
            setBody(LogoutRequest(refreshToken))
        }
    }

    suspend fun verifyEmail(token: String) {
        client.post("auth/verify-email") {
            contentType(ContentType.Application.Json)
            setBody(VerifyEmailRequest(token))
        }
    }

    suspend fun resendVerification(email: String) {
        client.post("auth/resend-verification") {
            contentType(ContentType.Application.Json)
            setBody(ResendVerificationRequest(email))
        }
    }

    suspend fun forgotPassword(email: String) {
        client.post("auth/forgot-password") {
            contentType(ContentType.Application.Json)
            setBody(ForgotPasswordRequest(email))
        }
    }

    suspend fun resetPassword(
        token: String,
        newPassword: String,
    ) {
        client.post("auth/reset-password") {
            contentType(ContentType.Application.Json)
            setBody(ResetPasswordRequest(token, newPassword))
        }
    }
}
