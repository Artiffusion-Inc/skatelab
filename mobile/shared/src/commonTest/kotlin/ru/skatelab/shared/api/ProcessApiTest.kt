package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.ByteArrayContent
import io.ktor.http.content.OutgoingContent
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.flow.toList
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

private fun bodyText(content: OutgoingContent): String = when (content) {
    is TextContent -> content.text
    is ByteArrayContent -> content.bytes().decodeToString()
    else -> ""
}

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
    fun queue_withoutPersonClick_omitsPersonClick() = kotlinx.coroutines.test.runTest {
        var requestBody = ""
        val engine = MockEngine { request ->
            requestBody = bodyText(request.body)
            respond(
                """{"task_id":"task-auto","status":"pending"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }

        ProcessApi(client).queue("video-key")

        assertFalse(requestBody.contains("person_click"))
    }

    @Test
    fun queue_convertsPixelCoordinatesToBackendIntegers() = kotlinx.coroutines.test.runTest {
        var requestBody = ""
        val engine = MockEngine { request ->
            requestBody = bodyText(request.body)
            respond(
                """{"task_id":"task-xy","status":"pending"}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }

        ProcessApi(client).queue(
            videoKey = "video-key",
            personClickX = 12.6f,
            personClickY = 40.4f,
        )

        assertTrue(requestBody.contains("\"x\":13"))
        assertTrue(requestBody.contains("\"y\":40"))
        assertFalse(requestBody.contains("12.6"))
    }

    @Test
    fun stream_stopsAfterCancelledTerminalEvent() = kotlinx.coroutines.test.runTest {
        var requestCount = 0
        val engine = MockEngine {
            requestCount++
            respond(
                "data: {\"status\":\"cancelled\",\"message\":\"Cancelled\"}\n\n",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Text.EventStream.toString()),
            )
        }
        val client = HttpClient(engine)

        val events = ProcessApi(client).stream("task-cancelled").toList()

        assertEquals(1, events.size)
        assertEquals("cancelled", events.single().status)
        assertEquals(1, requestCount)
    }

    @Test
    fun stream_doesNotRetryMalformedEvent() = kotlinx.coroutines.test.runTest {
        var requestCount = 0
        val engine = MockEngine {
            requestCount++
            respond(
                "data: {not-json}\n\n",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Text.EventStream.toString()),
            )
        }
        val client = HttpClient(engine)

        assertFailsWith<SerializationException> {
            ProcessApi(client).stream("task-malformed").toList()
        }
        assertEquals(1, requestCount)
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