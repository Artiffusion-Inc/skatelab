package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.utils.io.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.ProcessEvent

private val sseJson = Json { ignoreUnknownKeys = true }

class ProcessApi(private val client: HttpClient) {
    suspend fun queue(
        videoKey: String,
        sessionId: String? = null,
        personClickX: Float? = null,
        personClickY: Float? = null,
        frameSkip: Int = 1,
        tracking: String = "auto",
    ): QueueProcessResponse =
        client.post("/process/queue") {
            contentType(ContentType.Application.Json)
            setBody(buildMap {
                put("video_key", videoKey)
                put("frame_skip", frameSkip)
                put("tracking", tracking)
                if (sessionId != null) put("session_id", sessionId)
                if (personClickX != null && personClickY != null) {
                    put("person_click", mapOf("x" to personClickX, "y" to personClickY))
                }
            })
        }.body()

    suspend fun status(taskId: String): TaskStatusResponse =
        client.get("/process/$taskId/status").body()

    suspend fun cancel(taskId: String) {
        client.post("/process/$taskId/cancel")
    }

    fun stream(taskId: String): Flow<ProcessEvent> = flow {
        val response: HttpResponse = client.get("/process/$taskId/stream")
        val channel: ByteReadChannel = response.body()
        val buffer = StringBuilder()
        while (!channel.isClosedForRead) {
            val line = channel.readUTF8Line() ?: continue
            when {
                line.startsWith("data: ") -> {
                    val data = line.removePrefix("data: ").trim()
                    if (data.isNotEmpty()) {
                        val event = sseJson.decodeFromString<ProcessEvent>(data)
                        emit(event)
                    }
                }
                line.isEmpty() -> buffer.clear()
                else -> buffer.appendLine(line)
            }
        }
    }
}

@Serializable
data class QueueProcessResponse(
    @SerialName("task_id") val taskId: String,
    val status: String = "pending",
)

@Serializable
data class TaskStatusResponse(
    @SerialName("task_id") val taskId: String,
    val status: String,
    val progress: Float,
    val message: String,
    val error: String? = null,
)