package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import ru.skatelab.shared.models.UserResponse

class UsersApi(private val client: HttpClient) {
    suspend fun getMe(): UserResponse =
        client.get("/users/me").body()

    suspend fun updateProfile(
        displayName: String? = null,
        bio: String? = null,
        heightCm: Int? = null,
        weightKg: Double? = null,
    ): UserResponse =
        client.patch("/users/me") {
            contentType(ContentType.Application.Json)
            setBody(mapOf(
                "display_name" to displayName,
                "bio" to bio,
                "height_cm" to heightCm,
                "weight_kg" to weightKg,
            ).filterValues { it != null })
        }.body()

    suspend fun updateSettings(
        angularUnit: String? = null,
        language: String? = null,
        timezone: String? = null,
        theme: String? = null,
    ): UserResponse =
        client.patch("/users/me/settings") {
            contentType(ContentType.Application.Json)
            setBody(mapOf(
                "angular_unit" to angularUnit,
                "language" to language,
                "timezone" to timezone,
                "theme" to theme,
            ).filterValues { it != null })
        }.body()
}
