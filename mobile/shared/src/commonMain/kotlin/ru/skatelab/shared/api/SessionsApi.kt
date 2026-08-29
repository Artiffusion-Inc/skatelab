package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.models.SessionUpdateRequest
import ru.skatelab.shared.utils.expectSuccess

private const val MAX_BULK_DELETE_IDS = 100

class SessionsApi(private val client: HttpClient) {
    suspend fun get(id: String): SessionResponse =
        client.get("sessions/$id").expectSuccess().body()

    suspend fun list(
        limit: Int = 20,
        cursor: String? = null,
        elementType: String? = null,
        userId: String? = null,
    ): SessionListResponse =
        client.get("sessions") {
            parameter("limit", limit)
            if (cursor != null) parameter("cursor", cursor)
            if (elementType != null) parameter("element_type", elementType)
            if (userId != null) parameter("user_id", userId)
        }.expectSuccess().body()

    suspend fun create(
        elementType: String? = null,
        videoKey: String? = null,
        imuLeftKey: String? = null,
        imuRightKey: String? = null,
        manifestKey: String? = null,
        isuCode: String? = null,
    ): SessionResponse =
        client.post("sessions") {
            contentType(ContentType.Application.Json)
            setBody(buildJsonObject {
                elementType?.let { put("element_type", it) }
                videoKey?.let { put("video_key", it) }
                imuLeftKey?.let { put("imu_left_key", it) }
                imuRightKey?.let { put("imu_right_key", it) }
                manifestKey?.let { put("manifest_key", it) }
                isuCode?.let { put("isu_code", it) }
            })
        }.expectSuccess().body()

    suspend fun delete(id: String) {
        client.delete("sessions/$id").expectSuccess()
    }

    suspend fun update(id: String, request: SessionUpdateRequest): SessionResponse =
        client.patch("sessions/$id") {
            contentType(ContentType.Application.Json)
            setBody(request.toBackendJson())
        }.expectSuccess().body()

    suspend fun bulkDelete(ids: List<String>) {
        val normalizedIds = ids.map(String::trim).filter(String::isNotEmpty)
        require(normalizedIds.isNotEmpty()) { "ids must not be empty" }
        require(normalizedIds.size <= MAX_BULK_DELETE_IDS) {
            "ids exceeds max length of $MAX_BULK_DELETE_IDS"
        }
        client.delete("sessions/bulk") {
            parameter("ids", normalizedIds.joinToString(","))
        }.expectSuccess()
    }

    private fun SessionUpdateRequest.toBackendJson() = buildJsonObject {
        elementType?.let { put("element_type", it) }
        status?.let { put("status", it) }
        processTaskId?.let { put("process_task_id", it) }
        isuCode?.let { put("isu_code", it) }
    }
}
