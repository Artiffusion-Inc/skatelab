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
import io.ktor.http.content.ByteArrayContent
import io.ktor.http.content.OutgoingContent
import io.ktor.http.content.TextContent
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import ru.skatelab.shared.models.CreateWorkspaceRequest
import ru.skatelab.shared.models.InviteMemberRequest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class WorkspacesApiTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private val workspaceJson = """{
        "id":"workspace-1",
        "name":"Ice Academy",
        "slug":"ice-academy",
        "description":"Training group",
        "avatar_url":null,
        "is_active":true,
        "created_at":"2026-07-04T12:00:00Z",
        "updated_at":"2026-07-04T12:00:00Z"
    }"""

    private val memberJson = """{
        "id":"member-1",
        "workspace_id":"workspace-1",
        "user_id":"user-2",
        "role":"coach",
        "joined_at":"2026-07-04T12:01:00Z",
        "invited_by":"user-1",
        "user_name":"Coach",
        "user_email":"coach@example.com"
    }"""

    @Test
    fun create_sendsExactBackendRequestAndParsesWorkspace() = runTest {
        var requestMethod: HttpMethod? = null
        var requestPath: String? = null
        var requestBody: String? = null
        val engine = MockEngine { request ->
            requestMethod = request.method
            requestPath = request.url.encodedPath
            requestBody = bodyText(request.body)
            respond(workspaceJson, HttpStatusCode.Created, jsonHeaders)
        }

        val response = WorkspacesApi(client(engine)).create(
            CreateWorkspaceRequest("Ice Academy", "ice-academy", "Training group"),
        )

        assertEquals(HttpMethod.Post, requestMethod)
        assertEquals("/workspaces", requestPath)
        assertEquals(
            """{"name":"Ice Academy","slug":"ice-academy","description":"Training group"}""",
            requestBody,
        )
        assertEquals("workspace-1", response.id)
        assertEquals("ice-academy", response.slug)
        assertTrue(response.isActive)
    }

    @Test
    fun listAndGet_useWorkspaceRoutes() = runTest {
        val requests = mutableListOf<Pair<HttpMethod, String>>()
        val engine = MockEngine { request ->
            requests += request.method to request.url.encodedPath
            if (request.url.encodedPath == "/workspaces") {
                respond("[$workspaceJson]", HttpStatusCode.OK, jsonHeaders)
            } else {
                respond(workspaceJson, HttpStatusCode.OK, jsonHeaders)
            }
        }
        val api = WorkspacesApi(client(engine))

        assertEquals(1, api.list().size)
        assertEquals("workspace-1", api.get("workspace-1").id)

        assertEquals(
            listOf(
                HttpMethod.Get to "/workspaces",
                HttpMethod.Get to "/workspaces/workspace-1",
            ),
            requests,
        )
    }

    @Test
    fun memberOperations_preserveBackendWireShape() = runTest {
        val requests = mutableListOf<Pair<HttpMethod, String>>()
        val bodies = mutableListOf<String>()
        val engine = MockEngine { request ->
            requests += request.method to request.url.encodedPath
            bodies += bodyText(request.body)
            when (request.method) {
                HttpMethod.Get -> respond("[$memberJson]", HttpStatusCode.OK, jsonHeaders)
                HttpMethod.Delete -> respondOk()
                else -> respond(memberJson, HttpStatusCode.Created, jsonHeaders)
            }
        }
        val api = WorkspacesApi(client(engine))
        val invite = InviteMemberRequest("coach@example.com", "coach")

        assertEquals("user-2", api.invite("workspace-1", invite).userId)
        assertEquals(1, api.listMembers("workspace-1").size)
        api.removeMember("workspace-1", "user-2")
        assertEquals("coach", api.updateRole("workspace-1", "user-2", invite).role)

        assertEquals(
            listOf(
                HttpMethod.Post to "/workspaces/workspace-1/invite",
                HttpMethod.Get to "/workspaces/workspace-1/members",
                HttpMethod.Delete to "/workspaces/workspace-1/members/user-2",
                HttpMethod.Patch to "/workspaces/workspace-1/members/user-2/role",
            ),
            requests,
        )
        assertEquals(
            listOf(
                """{"email":"coach@example.com","role":"coach"}""",
                "",
                "",
                """{"email":"coach@example.com","role":"coach"}""",
            ),
            bodies,
        )
    }

    @Test
    fun nonSuccess_isNotReturnedAsSuccess() = runTest {
        val engine = MockEngine {
            respond("{\"detail\":\"Forbidden\"}", HttpStatusCode.Forbidden, jsonHeaders)
        }

        val error = runCatching { WorkspacesApi(client(engine)).list() }.exceptionOrNull()

        assertTrue(error is io.ktor.client.plugins.ResponseException)
    }

    private fun bodyText(content: OutgoingContent): String = when (content) {
        is TextContent -> content.text
        is ByteArrayContent -> content.bytes().decodeToString()
        else -> ""
    }
}
