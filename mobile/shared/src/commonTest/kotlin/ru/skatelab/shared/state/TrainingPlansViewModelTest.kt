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
import ru.skatelab.shared.api.TrainingPlansApi
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class TrainingPlansViewModelTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun client(engine: MockEngine) = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
    }

    private val jsonHeaders = headersOf(
        HttpHeaders.ContentType,
        ContentType.Application.Json.toString(),
    )

    private fun plan(id: String) = """{
        "id":"$id",
        "user_id":"user-1",
        "session_id":"session-1",
        "items":[],
        "generated_at":"2026-07-04T12:00:00Z",
        "completed":false,
        "focus_subscore":"landing_control",
        "created_at":"2026-07-04T12:00:00Z",
        "updated_at":"2026-07-04T12:00:00Z"
    }"""

    @Test
    fun loadAndGenerate_updateTypedState() = runTest {
        val engine = MockEngine { request ->
            val response = when (request.url.encodedPath) {
                "/training-plans/plan-1" -> plan("plan-1")
                "/training-plans/generate" -> plan("generated-1")
                else -> error("unexpected path: ${request.url.encodedPath}")
            }
            respond(response, status = HttpStatusCode.OK, headers = jsonHeaders)
        }
        val viewModel = TrainingPlansViewModel(TrainingPlansApi(client(engine)))

        viewModel.uiState.test {
            assertEquals(TrainingPlansState.Loading, awaitItem())
            viewModel.loadPlan("plan-1")
            assertEquals("plan-1", assertIs<TrainingPlansState.Loaded>(awaitItem()).plan.id)

            viewModel.generatePlan("session-1")
            assertEquals(TrainingPlansState.Loading, awaitItem())
            assertEquals(
                "generated-1",
                assertIs<TrainingPlansState.Loaded>(awaitItem()).plan.id,
            )
        }
    }
}
