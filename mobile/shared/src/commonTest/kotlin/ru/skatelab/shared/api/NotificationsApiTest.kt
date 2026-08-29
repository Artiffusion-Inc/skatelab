package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class NotificationsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private val notificationJson = """{
        "id": "notification-1",
        "user_id": "user-1",
        "event_type": "analysis.completed",
        "title": "Анализ готов",
        "body": "Ваш анализ завершён",
        "deep_link": "skatelab://session/session-1",
        "payload": {"session_id": "session-1", "score": 8.5},
        "is_read": false,
        "read_at": null,
        "created_at": "2026-07-04T12:00:00Z"
    }"""

    @Test
    fun list_sendsBackendPaginationParameters() = runTest {
        var method: HttpMethod? = null
        var path: String? = null
        var query: String? = null
        val engine = MockEngine { request ->
            method = request.method
            path = request.url.encodedPath
            query = request.url.encodedQuery
            respond(
                """{
                    "notifications": [$notificationJson],
                    "total": 1,
                    "unread_count": 1,
                    "page": 2,
                    "page_size": 5,
                    "pages": 3,
                    "has_next": true,
                    "has_prev": true
                }""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders,
            )
        }

        val response = NotificationsApi(client(engine)).list(page = 2, pageSize = 5, unreadOnly = true)

        assertEquals(HttpMethod.Get, method)
        assertEquals("/notifications", path)
        assertTrue(query!!.contains("page=2"))
        assertTrue(query!!.contains("page_size=5"))
        assertTrue(query!!.contains("unread_only=true"))
        assertEquals(1, response.notifications.size)
        assertEquals("notification-1", response.notifications[0].id)
        assertEquals("analysis.completed", response.notifications[0].eventType)
        assertEquals("session-1", response.notifications[0].payload!!["session_id"]?.toString()?.trim('"'))
        assertEquals(2, response.page)
        assertEquals(3, response.pages)
        assertTrue(response.hasNext)
    }

    @Test
    fun unreadCount_returnsCount() = runTest {
        var path: String? = null
        val engine = MockEngine { request ->
            path = request.url.encodedPath
            respond("""{"unread_count": 7}""", status = HttpStatusCode.OK, headers = jsonHeaders)
        }

        val response = NotificationsApi(client(engine)).getUnreadCount()

        assertEquals("/notifications/unread-count", path)
        assertEquals(7, response.unreadCount)
    }

    @Test
    fun markRead_supportsPostAndPatchAliases() = runTest {
        val methods = mutableListOf<HttpMethod>()
        val paths = mutableListOf<String>()
        val engine = MockEngine { request ->
            methods += request.method
            paths += request.url.encodedPath
            respond(notificationJson.replace("false", "true"), status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val api = NotificationsApi(client(engine))

        api.markRead("notification-1")
        api.markReadPatch("notification-1")

        assertEquals(listOf(HttpMethod.Post, HttpMethod.Patch), methods)
        assertEquals(listOf("/notifications/notification-1/read", "/notifications/notification-1/read"), paths)
    }

    @Test
    fun markAllRead_supportsPostAndPatchAliases() = runTest {
        val methods = mutableListOf<HttpMethod>()
        val engine = MockEngine { request ->
            methods += request.method
            respond("""{"marked_read": 2}""", status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val api = NotificationsApi(client(engine))

        assertEquals(2, api.markAllRead().markedRead)
        assertEquals(2, api.markAllReadPatch().markedRead)
        assertEquals(listOf(HttpMethod.Post, HttpMethod.Patch), methods)
    }
}
