package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.HttpRequestData
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals

class ProcessApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun makeClient(engine: MockEngine): HttpClient =
        HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }

    @Test
    fun queue_returnsTaskId() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request: HttpRequestData ->
            when (request.url.encodedPath) {
                "/process/queue" -> respond(
                    """{"task_id": "task-123", "status": "pending"}""",
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val api = ProcessApi(makeClient(engine))
        val response = api.queue("video-key")
        assertEquals("task-123", response.taskId)
        assertEquals("pending", response.status)
    }

    @Test
    fun status_returnsProgress() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request: HttpRequestData ->
            when (request.url.encodedPath) {
                "/process/task-123/status" -> respond(
                    """{"task_id": "task-123", "status": "running", "progress": 0.5, "message": "Processing"}""",
                    status = HttpStatusCode.OK,
                    headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                )
                else -> respondError(HttpStatusCode.NotFound)
            }
        }
        val api = ProcessApi(makeClient(engine))
        val response = api.status("task-123")
        assertEquals("task-123", response.taskId)
        assertEquals("running", response.status)
        assertEquals(0.5f, response.progress)
    }

    @Test
    fun cancel_postsToCancelEndpoint() = kotlinx.coroutines.test.runTest {
        var requestPath: String? = null
        val engine = MockEngine { request: HttpRequestData ->
            requestPath = request.url.encodedPath
            respond(
                "{}",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = ProcessApi(makeClient(engine))
        api.cancel("task-456")
        assertEquals("/process/task-456/cancel", requestPath)
    }
}