package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.auth.providers.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import ru.skatelab.shared.models.TokenResponse

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    @SerialName("display_name") val displayName: String? = null,
)

class AuthApi(private val client: HttpClient, private val baseUrl: String) {
    suspend fun login(email: String, password: String): TokenResponse =
        client.post("$baseUrl/auth/login") {
            contentType(ContentType.Application.Json)
            setBody(LoginRequest(email, password))
        }.body()

    suspend fun register(email: String, password: String, displayName: String? = null): TokenResponse =
        client.post("$baseUrl/auth/register") {
            contentType(ContentType.Application.Json)
            setBody(RegisterRequest(email, password, displayName))
        }.body()

    suspend fun refresh(refreshToken: String): TokenResponse =
        client.post("$baseUrl/auth/refresh") {
            markAsRefreshTokenRequest()
            contentType(ContentType.Application.Json)
            setBody(mapOf("refresh_token" to refreshToken))
        }.body()

    suspend fun logout(refreshToken: String) {
        client.post("$baseUrl/auth/logout") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("refresh_token" to refreshToken))
        }
    }

    suspend fun verifyEmail(token: String) {
        client.post("$baseUrl/auth/verify-email") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("token" to token))
        }
    }

    suspend fun resendVerification(email: String) {
        client.post("$baseUrl/auth/resend-verification") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("email" to email))
        }
    }

    suspend fun forgotPassword(email: String) {
        client.post("$baseUrl/auth/forgot-password") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("email" to email))
        }
    }

    suspend fun resetPassword(token: String, newPassword: String) {
        client.post("$baseUrl/auth/reset-password") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("token" to token, "new_password" to newPassword))
        }
    }
}
