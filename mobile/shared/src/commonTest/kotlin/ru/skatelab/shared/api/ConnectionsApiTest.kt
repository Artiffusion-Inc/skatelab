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
import ru.skatelab.shared.models.InviteRequest
import kotlin.test.Test
import kotlin.test.assertEquals

class ConnectionsApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private val connectionJson = """{
        "id":"connection-1",
        "from_user_id":"coach-1",
        "to_user_id":"skater-1",
        "connection_type":"coaching",
        "status":"active",
        "initiated_by":"coach-1",
        "created_at":"2026-07-04T12:00:00Z",
        "ended_at":null,
        "from_user_name":"Coach",
        "to_user_name":"Skater"
    }"""

    @Test
    fun listAndPending_useConnectionRoutesAndParseSchemas() = runTest {
        val paths = mutableListOf<String>()
        val engine = MockEngine { request ->
            paths += request.url.encodedPath
            respond(
                """{"total":1,"connections":[$connectionJson]}""",
                status = HttpStatusCode.OK,
                headers = jsonHeaders,
            )
        }
        val api = ConnectionsApi(client(engine))

        val connections = api.list()
        val pending = api.pending()

        assertEquals(listOf("/connections", "/connections/pending"), paths)
        assertEquals(1, connections.total)
        assertEquals("connection-1", connections.connections.single().id)
        assertEquals("Coach", pending.connections.single().fromUserName)
        assertEquals(1, pending.page)
        assertEquals(20, pending.pageSize)
    }

    @Test
    fun invite_acceptAndEnd_useExpectedMethodsAndPaths() = runTest {
        val methods = mutableListOf<HttpMethod>()
        val paths = mutableListOf<String>()
        val engine = MockEngine { request ->
            methods += request.method
            paths += request.url.encodedPath
            respond(connectionJson, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val api = ConnectionsApi(client(engine))

        val invited = api.invite(InviteRequest("skater@example.com", "coaching"))
        val accepted = api.accept("connection-1")
        val ended = api.end("connection-1")

        assertEquals("connection-1", invited.id)
        assertEquals("connection-1", accepted.id)
        assertEquals("connection-1", ended.id)
        assertEquals(listOf(HttpMethod.Post, HttpMethod.Post, HttpMethod.Post), methods)
        assertEquals(
            listOf(
                "/connections/invite",
                "/connections/connection-1/accept",
                "/connections/connection-1/end",
            ),
            paths,
        )
    }
}
