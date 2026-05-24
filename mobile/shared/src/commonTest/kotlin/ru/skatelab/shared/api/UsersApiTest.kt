package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.UserResponse
import kotlin.test.Test
import kotlin.test.assertEquals

class UsersApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val sampleUserJson = """{
        "id": "u1",
        "email": "skater@example.com",
        "display_name": "Alice",
        "avatar_url": null,
        "bio": "Figure skater",
        "height_cm": 165.0,
        "weight_kg": 52.0,
        "language": "ru",
        "timezone": "Europe/Moscow",
        "theme": "dark",
        "onboarding_role": "athlete",
        "angular_unit": "deg_per_sec"
    }"""

    @Test
    fun getMe_returnsUserProfile() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respond(
                sampleUserJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = UsersApi(client(engine))
        val response = api.getMe()
        assertEquals(HttpMethod.Get, requestMethod)
        assertEquals("/users/me", requestPath)
        assertEquals("u1", response.id)
        assertEquals("skater@example.com", response.email)
        assertEquals("Alice", response.displayName)
        assertEquals("athlete", response.onboardingRole)
    }

    @Test
    fun updateProfile_sendsPatchAndReturnsUpdatedUser() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val updatedJson = """{
            "id": "u1",
            "email": "skater@example.com",
            "display_name": "Alice Updated",
            "avatar_url": null,
            "bio": "Updated bio",
            "height_cm": 167.0,
            "weight_kg": 53.0,
            "language": "ru",
            "timezone": "Europe/Moscow",
            "theme": "dark",
            "onboarding_role": "athlete",
            "angular_unit": "deg_per_sec"
        }"""
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respond(
                updatedJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = UsersApi(client(engine))
        val response = api.updateProfile(displayName = "Alice Updated", bio = "Updated bio")
        assertEquals(HttpMethod.Patch, requestMethod)
        assertEquals("/users/me", requestPath)
        assertEquals("Alice Updated", response.displayName)
    }

    @Test
    fun updateSettings_sendsPatchAndReturnsUpdatedUser() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val updatedJson = """{
            "id": "u1",
            "email": "skater@example.com",
            "display_name": "Alice",
            "avatar_url": null,
            "bio": "Figure skater",
            "height_cm": 165.0,
            "weight_kg": 52.0,
            "language": "en",
            "timezone": "America/New_York",
            "theme": "light",
            "onboarding_role": "athlete",
            "angular_unit": "rad_per_sec"
        }"""
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respond(
                updatedJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = UsersApi(client(engine))
        val response = api.updateSettings(language = "en", theme = "light")
        assertEquals(HttpMethod.Patch, requestMethod)
        assertEquals("/users/me/settings", requestPath)
        assertEquals("en", response.language)
        assertEquals("light", response.theme)
    }
}