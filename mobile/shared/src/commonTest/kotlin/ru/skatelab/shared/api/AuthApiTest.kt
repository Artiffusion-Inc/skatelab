package ru.skatelab.shared.api

import kotlinx.serialization.json.Json
import kotlin.test.Test
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
