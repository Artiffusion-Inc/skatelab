package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.models.SessionUpdateRequest
import ru.skatelab.shared.utils.expectSuccess

@Serializable
data class BulkDeleteRequest(@SerialName("session_ids") val ids: List<String>)

class SessionsApi(private val client: HttpClient) {
    suspend fun get(id: String): SessionResponse =
        client.get("sessions/$id").expectSuccess().body()

    suspend fun list(
        limit: Int = 20,
        cursor: String? = null,
        elementType: String? = null,
    ): SessionListResponse =
        client.get("sessions") {
            parameter("limit", limit)
            if (cursor != null) parameter("cursor", cursor)
            if (elementType != null) parameter("element_type", elementType)
        }.expectSuccess().body()

    suspend fun create(
        elementType: String,
        videoKey: String? = null,
        imuLeftKey: String? = null,
        imuRightKey: String? = null,
    ): SessionResponse =
        client.post("sessions") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                put("element_type", elementType)
                videoKey?.let { put("video_key", it) }
                imuLeftKey?.let { put("imu_left_key", it) }
                imuRightKey?.let { put("imu_right_key", it) }
            })
        }.expectSuccess().body()

    suspend fun delete(id: String) {
        client.delete("sessions/$id").expectSuccess()
    }

    suspend fun update(id: String, request: SessionUpdateRequest): SessionResponse =
        client.patch("sessions/$id") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun bulkDelete(ids: List<String>) {
        client.delete("sessions/bulk") {
            contentType(ContentType.Application.Json)
            setBody(BulkDeleteRequest(ids))
        }.expectSuccess()
    }
}