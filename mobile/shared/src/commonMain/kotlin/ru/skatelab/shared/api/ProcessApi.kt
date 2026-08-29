package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.utils.io.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.io.IOException
import kotlin.math.roundToInt
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.ProcessEvent
import ru.skatelab.shared.models.ProcessStatus
import ru.skatelab.shared.utils.expectSuccess

private val sseJson = Json { ignoreUnknownKeys = true }

class ProcessApi(private val client: HttpClient) : IProcessApi {
    override suspend fun queue(
        videoKey: String,
        sessionId: String?,
        personClickX: Float?,
        personClickY: Float?,
        frameSkip: Int,
        tracking: String,
    ): QueueProcessResponse =
        client.post("process/queue") {
            contentType(ContentType.Application.Json)
            setBody(QueueProcessRequest(
                videoKey = videoKey,
                frameSkip = frameSkip,
                tracking = tracking,
                sessionId = sessionId,
                personClick = if (personClickX != null && personClickY != null)
                    PersonClick(personClickX.roundToInt(), personClickY.roundToInt()) else null,
            ))
        }.expectSuccess().body()

    override suspend fun status(taskId: String): TaskStatusResponse =
        client.get("process/$taskId/status").expectSuccess().body()

    override suspend fun cancel(taskId: String) {
        client.post("process/$taskId/cancel").expectSuccess()
    }

    override fun stream(taskId: String): Flow<ProcessEvent> = flow {
        var retries = 0
        val maxRetries = 3
        while (retries <= maxRetries) {
            try {
                val response: HttpResponse = client.get("process/$taskId/stream")
                val channel: ByteReadChannel = response.expectSuccess().body()
                val buffer = StringBuilder()
                var receivedEvent = false
                while (!channel.isClosedForRead) {
                    val line = channel.readUTF8Line() ?: continue
                    when {
                        line.startsWith("data: ") -> {
                            val data = line.removePrefix("data: ").trim()
                            if (data.isNotEmpty()) {
                                val event = sseJson.decodeFromString<ProcessEvent>(data)
                                emit(event)
                                receivedEvent = true
                                if (event.parsedStatus == ProcessStatus.COMPLETED ||
                                    event.parsedStatus == ProcessStatus.FAILED ||
                                    event.parsedStatus == ProcessStatus.CANCELLED
                                ) {
                                    return@flow
                                }
                            }
                        }
                        line.isEmpty() -> buffer.clear()
                        else -> buffer.appendLine(line)
                    }
                }
                // Stream ended without terminal event — reconnect
                if (!receivedEvent || retries < maxRetries) {
                    retries++
                    kotlinx.coroutines.delay(1000L * retries)
                    continue
                }
                return@flow
            } catch (e: CancellationException) {
                throw e
            } catch (e: io.ktor.client.plugins.ResponseException) {
                throw e
            } catch (e: Exception) {
                if (e !is IOException && e !is SocketTimeoutException && e !is HttpRequestTimeoutException) {
                    throw e
                }
                retries++
                if (retries > maxRetries) return@flow
                kotlinx.coroutines.delay(1000L * retries)
            }
        }
    }
}

@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class QueueProcessRequest(
    @SerialName("video_key") val videoKey: String,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("frame_skip") val frameSkip: Int = 1,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) val tracking: String = "auto",
    @SerialName("session_id") val sessionId: String? = null,
    @SerialName("person_click") val personClick: PersonClick? = null,
)

@Serializable
data class PersonClick(val x: Int, val y: Int)

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