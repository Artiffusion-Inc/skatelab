package ru.skatelab.shared.state

import app.cash.turbine.test
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.ConnectionsApi
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ConnectionsViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private fun connection(id: String, status: String) = """{
        "id":"$id",
        "from_user_id":"coach-1",
        "to_user_id":"skater-1",
        "connection_type":"coaching",
        "status":"$status",
        "initiated_by":"coach-1",
        "created_at":"2026-07-04T12:00:00Z",
        "ended_at":${if (status == "ended") "\"2026-07-04T13:00:00Z\"" else "null"}
    }"""

    @Test
    fun loadInviteAcceptAndEnd_updateTypedState() = runTest {
        val engine = MockEngine { request ->
            val response = when (request.url.encodedPath) {
                "/connections" -> """{"total":1,"connections":[${connection("c1", "active") }]}"""
                "/connections/pending" -> """{"total":1,"connections":[${connection("c2", "invited") }]}"""
                "/connections/invite" -> connection("c3", "invited")
                "/connections/c2/accept" -> connection("c2", "active")
                "/connections/c1/end" -> connection("c1", "ended")
                else -> error("unexpected path: ${request.url.encodedPath}")
            }
            respond(response, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val viewModel = ConnectionsViewModel(ConnectionsApi(client(engine)))

        viewModel.uiState.test {
            assertEquals(ConnectionsState.Loading, awaitItem())
            viewModel.loadConnections()
            val loaded = assertIs<ConnectionsState.Loaded>(awaitItem())
            assertEquals(listOf("c1"), loaded.connections.map { it.id })
            assertEquals(listOf("c2"), loaded.pendingInvites.map { it.id })

            viewModel.invite("new@example.com", "coaching")
            val invited = assertIs<ConnectionsState.Loaded>(awaitItem())
            assertEquals(listOf("c1", "c3"), invited.connections.map { it.id })

            viewModel.acceptInvite("c2")
            val accepted = assertIs<ConnectionsState.Loaded>(awaitItem())
            assertEquals(listOf("c1", "c3", "c2"), accepted.connections.map { it.id })
            assertEquals(emptyList(), accepted.pendingInvites)

            viewModel.endConnection("c1")
            val ended = assertIs<ConnectionsState.Loaded>(awaitItem())
            assertEquals("ended", ended.connections.first { it.id == "c1" }.status)
        }
    }
}
