package ru.skatelab.shared.auth

import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import ru.skatelab.shared.api.LoginRequest
import ru.skatelab.shared.api.RegisterRequest
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.assertEquals

class AuthRepositoryTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun loginRequestSerializesCorrectly() {
        val req = LoginRequest("a@b.com", "pass123")
        val encoded = json.encodeToString(req)
        assertTrue(encoded.contains("a@b.com"))
        assertTrue(encoded.contains("pass123"))
    }

    @Test
    fun registerRequestSerializesCorrectly() {
        val req = RegisterRequest("x@y.com", "secret", "Alice")
        val encoded = json.encodeToString(req)
        assertTrue(encoded.contains("x@y.com"))
        assertTrue(encoded.contains("Alice"))
    }

    @Test
    fun loginRequestRoundtrip() {
        val original = LoginRequest("test@test.com", "pwd")
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<LoginRequest>(encoded)
        assertEquals(original.email, decoded.email)
        assertEquals(original.password, decoded.password)
    }
}
