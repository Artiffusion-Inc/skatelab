package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondOk
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.SessionUpdateRequest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SessionsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val sampleSessionJson = """{
        "id": "sess-1",
        "user_id": "user-1",
        "element_type": "flip",
        "video_url": "https://r2.example.com/video.mp4",
        "processed_video_url": null,
        "status": "completed",
        "overall_score": 8.5,
        "recommendations": ["Keep knees bent"],
        "metrics": [],
        "created_at": "2026-05-24T12:00:00Z"
    }"""

    @Test
    fun get_returnsSession() = kotlinx.coroutines.test.runTest {
        val engine = MockEngine { request ->
            respond(
                sampleSessionJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(client(engine))
        val response = api.get("sess-1")
        assertEquals("sess-1", response.id)
        assertEquals("user-1", response.userId)
        assertEquals("flip", response.elementType)
        assertEquals("completed", response.status)
        assertEquals(8.5f, response.overallScore)
        assertEquals(listOf("Keep knees bent"), response.recommendations)
    }

    @Test
    fun list_returnsSessionList() = kotlinx.coroutines.test.runTest {
        val listJson = """{
            "sessions": [$sampleSessionJson],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "pages": 1
        }"""
        val engine = MockEngine { request ->
            respond(
                listJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(client(engine))
        val response = api.list()
        assertEquals(1, response.total)
        assertEquals(1, response.sessions.size)
        assertEquals("sess-1", response.sessions[0].id)
    }

    @Test
    fun list_passesQueryParameters() = kotlinx.coroutines.test.runTest {
        var capturedPath: String? = null
        var capturedQuery: String? = null
        val engine = MockEngine { request ->
            capturedPath = request.url.encodedPath
            capturedQuery = request.url.encodedQuery
            respond(
                """{"sessions":[],"total":0,"page":1,"page_size":20,"pages":0}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(client(engine))
        api.list(limit = 10, offset = 5, elementType = "lutz")
        assertEquals("/sessions", capturedPath)
        assertTrue(capturedQuery!!.contains("limit=10"))
        assertTrue(capturedQuery!!.contains("offset=5"))
        assertTrue(capturedQuery!!.contains("element_type=lutz"))
    }

    @Test
    fun create_returnsNewSession() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respond(
                sampleSessionJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(client(engine))
        val response = api.create(elementType = "flip", videoKey = "video-key-1")
        assertEquals(HttpMethod.Post, requestMethod)
        assertEquals("/sessions", requestPath)
        assertEquals("flip", response.elementType)
    }

    @Test
    fun delete_sendsDeleteRequest() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respondOk()
        }
        val api = SessionsApi(client(engine))
        api.delete("sess-42")
        assertEquals(HttpMethod.Delete, requestMethod)
        assertEquals("/sessions/sess-42", requestPath)
    }

    @Test
    fun update_returnsUpdatedSession() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val updatedJson = """{
            "id": "sess-1",
            "user_id": "user-1",
            "element_type": "lutz",
            "video_url": null,
            "processed_video_url": null,
            "status": "completed",
            "overall_score": null,
            "recommendations": null,
            "metrics": [],
            "created_at": "2026-05-24T12:00:00Z"
        }"""
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respond(
                updatedJson,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
            )
        }
        val api = SessionsApi(client(engine))
        val response = api.update("sess-1", SessionUpdateRequest(elementType = "lutz", notes = "PR attempt"))
        assertEquals(HttpMethod.Patch, requestMethod)
        assertEquals("/sessions/sess-1", requestPath)
        assertEquals("lutz", response.elementType)
    }

    @Test
    fun bulkDelete_sendsDeleteWithIds() = kotlinx.coroutines.test.runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            respondOk()
        }
        val api = SessionsApi(client(engine))
        api.bulkDelete(listOf("sess-1", "sess-2", "sess-3"))
        assertEquals(HttpMethod.Delete, requestMethod)
        assertEquals("/sessions/bulk", requestPath)
    }
}
