package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionListResponse

class SessionsApi(private val client: HttpClient) {
    suspend fun get(id: String): SessionResponse =
        client.get("/sessions/$id").body()

    suspend fun list(
        limit: Int = 20,
        offset: Int = 0,
        elementType: String? = null,
    ): SessionListResponse =
        client.get("/sessions") {
            parameter("limit", limit)
            parameter("offset", offset)
            if (elementType != null) parameter("element_type", elementType)
        }.body()

    suspend fun create(
        elementType: String,
        videoKey: String? = null,
        imuLeftKey: String? = null,
        imuRightKey: String? = null,
    ): SessionResponse =
        client.post("/sessions") {
            contentType(ContentType.Application.Json)
            setBody(mapOf(
                "element_type" to elementType,
                "video_key" to videoKey,
                "imu_left_key" to imuLeftKey,
                "imu_right_key" to imuRightKey,
            ).filterValues { it != null })
        }.body()

    suspend fun delete(id: String) {
        client.delete("/sessions/$id")
    }
}
