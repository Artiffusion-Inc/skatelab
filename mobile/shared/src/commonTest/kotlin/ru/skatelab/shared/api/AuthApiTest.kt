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
}
