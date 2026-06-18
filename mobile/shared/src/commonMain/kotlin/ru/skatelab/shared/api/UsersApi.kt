package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.models.UserResponse

class UsersApi(private val client: HttpClient) {
    suspend fun getMe(): UserResponse =
        client.get("users/me").body()

    suspend fun updateProfile(
        displayName: String? = null,
        bio: String? = null,
        heightCm: Int? = null,
        weightKg: Double? = null,
    ): UserResponse =
        client.patch("users/me") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                displayName?.let { put("display_name", it) }
                bio?.let { put("bio", it) }
                heightCm?.let { put("height_cm", it) }
                weightKg?.let { put("weight_kg", it) }
            })
        }.body()

    suspend fun updateSettings(
        angularUnit: String? = null,
        language: String? = null,
        timezone: String? = null,
        theme: String? = null,
    ): UserResponse =
        client.patch("users/me/settings") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                angularUnit?.let { put("angular_unit", it) }
                language?.let { put("language", it) }
                timezone?.let { put("timezone", it) }
                theme?.let { put("theme", it) }
            })
        }.body()
}
