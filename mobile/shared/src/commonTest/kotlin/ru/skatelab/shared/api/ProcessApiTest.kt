package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlin.math.roundToInt
import kotlin.test.Test
import kotlin.test.assertEquals

class ProcessApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun queue_returnsTaskId() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"task_id": "task-123", "status": "pending"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = ProcessApi(client)
        val response = api.queue("video-key")
        assertEquals("task-123", response.taskId)
        assertEquals("pending", response.status)
    }

    @Test
    fun queue_convertsPixelCoordinatesToBackendIntegers() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine {
            respond(
                """{"task_id":"task-xy","status":"pending"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }

        val encoded = Json.encodeToString(
            QueueProcessRequest(
                videoKey = "video-key",
                personClick = PersonClick(12.6f.roundToInt(), 40.4f.roundToInt()),
            ),
        )
        assertEquals(true, encoded.contains("\"x\":13"))
        assertEquals(true, encoded.contains("\"y\":40"))
    }

    @Test
    fun status_returnsProgress() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                """{"task_id": "task-123", "status": "running", "progress": 0.5, "message": "Processing"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = ProcessApi(client)
        val response = api.status("task-123")
        assertEquals("task-123", response.taskId)
        assertEquals("running", response.status)
        assertEquals(0.5f, response.progress)
    }

    @Test
    fun cancel_postsToCancelEndpoint() = kotlinx.coroutines.test.runTest {
        var requestPath: String? = null
        val engine = MockEngine { request ->
            requestPath = request.url.encodedPath
            respondOk("{}")
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = ProcessApi(client)
        api.cancel("task-456")
        assertEquals("/process/task-456/cancel", requestPath)
    }

    @Test
    fun queue_withSessionId_sendsBody() = kotlinx.coroutines.test.runTest {
        var capturedBody: String? = null
        val engine = MockEngine { request ->
            capturedBody = request.body.toString()
            respond(
                """{"task_id": "task-789", "status": "pending"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val api = ProcessApi(client)
        val response = api.queue("video-key", sessionId = "sess-1", frameSkip = 2)
        assertEquals("task-789", response.taskId)
    }
}